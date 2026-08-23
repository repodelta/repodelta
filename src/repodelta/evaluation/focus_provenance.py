from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import cast

from repodelta.evaluation.structural_correctness import (
    StructuralCorrectnessLabels,
    StructuralCorrectnessObservation,
    StructuralCorrectnessPacket,
    observe_structural_correctness,
)
from repodelta.model.contracts import (
    ReviewBrief,
    StructuralFocusMembership,
    StructuralFocusMembershipClass,
    StructuralFocusProvenance,
)


PROVENANCE_OBSERVATION_SCHEMA = "structural_focus_provenance_observation.v1"
COUNTERFACTUAL_SCHEMA = "structural_focus_producer_counterfactual.v1"


@dataclass(frozen=True)
class ProvenanceFocus:
    """The exact memberships copied from one canonical verification overlay."""

    subject_id: str
    memberships: tuple[StructuralFocusMembership, ...] = ()

    def __post_init__(self) -> None:
        identities = tuple(
            (item.member_kind, item.member_id) for item in self.memberships
        )
        if len(identities) != len(set(identities)):
            raise ValueError("provenance focus contains duplicate memberships")


@dataclass(frozen=True)
class StructuralFocusProvenanceObservation:
    """Evaluation-side serialization of producer-owned overlay provenance.

    This object copies the canonical membership objects; it does not derive
    membership, infer a path, or consult reference labels while constructing.
    """

    packet_digest: str
    focuses: tuple[ProvenanceFocus, ...]
    schema_version: str = PROVENANCE_OBSERVATION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != PROVENANCE_OBSERVATION_SCHEMA:
            raise ValueError("unsupported provenance observation schema")
        if not self.packet_digest:
            raise ValueError("provenance observation requires packet identity")
        subject_ids = tuple(item.subject_id for item in self.focuses)
        if any(not item.strip() for item in subject_ids):
            raise ValueError("provenance observation requires subject identities")
        if len(subject_ids) != len(set(subject_ids)):
            raise ValueError("provenance observation contains duplicate focuses")


@dataclass(frozen=True)
class ProducerOutcome:
    subject_kind: str
    disabled_producer: str
    focus_count: int
    memberships_removed: int
    node_false_inclusions: int
    node_false_exclusions: int
    relation_false_inclusions: int
    relation_false_exclusions: int


@dataclass(frozen=True)
class ProducerCounterfactualReport:
    packet_digest: str
    disabled_producers: tuple[str, ...]
    outcomes: tuple[ProducerOutcome, ...]
    schema_version: str = COUNTERFACTUAL_SCHEMA


def observe_focus_provenance(
    brief: ReviewBrief,
    packet: StructuralCorrectnessPacket,
) -> StructuralFocusProvenanceObservation:
    """Copy canonical overlay memberships into an evaluation artifact."""

    from repodelta.evaluation.structural_correctness import (
        prepare_structural_correctness_packet,
    )

    current = prepare_structural_correctness_packet(brief)
    if current != packet:
        raise ValueError("structural correctness packet does not match current review")
    inspections = {
        item.subject_id: item
        for item in brief.projection.verification_workspace.inspections
    }
    known_subjects = {item.subject_id for item in packet.subjects}
    if set(inspections) < known_subjects:
        missing = sorted(known_subjects - set(inspections))
        raise ValueError(
            "canonical verification inspections do not cover subjects: "
            + ", ".join(missing)
        )
    result = StructuralFocusProvenanceObservation(
        packet_digest=packet.digest,
        focuses=tuple(
            ProvenanceFocus(
                subject_id=subject.subject_id,
                memberships=tuple(inspections[subject.subject_id].structural_overlay.memberships),
            )
            for subject in packet.subjects
        ),
    )
    _validate_provenance_observation(result, packet)
    _validate_observation_alignment(
        observe_structural_correctness(brief, packet), result
    )
    return result


def write_provenance_json(
    value: StructuralFocusProvenanceObservation | ProducerCounterfactualReport,
    output: str | Path,
) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_focus_provenance(
    path: str | Path,
) -> StructuralFocusProvenanceObservation:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("provenance observation must be a JSON object")
    if raw.get("schema_version") != PROVENANCE_OBSERVATION_SCHEMA:
        raise ValueError("unsupported provenance observation schema")
    raw_focuses = raw.get("focuses", [])
    if not isinstance(raw_focuses, list):
        raise ValueError("provenance observation focuses must be a list")
    if not all(isinstance(focus, Mapping) for focus in raw_focuses):
        raise ValueError("provenance observation focuses must be objects")
    return StructuralFocusProvenanceObservation(
        packet_digest=str(raw["packet_digest"]),
        focuses=tuple(
            ProvenanceFocus(
                subject_id=str(focus["subject_id"]),
                memberships=tuple(
                    _membership_from_mapping(item)
                    for item in focus.get("memberships", [])
                ),
            )
            for focus in raw_focuses
        ),
    )


def replay_producer_counterfactual(
    packet: StructuralCorrectnessPacket,
    observation: StructuralCorrectnessObservation,
    provenance: StructuralFocusProvenanceObservation,
    labels: StructuralCorrectnessLabels,
    *,
    disabled_producers: Iterable[str],
) -> ProducerCounterfactualReport:
    """Replay only recorded producer membership contributions.

    This is deliberately not a prediction of a redesigned selector or
    closure. A membership is removed only when every producer entry recorded
    for that membership is disabled. The report therefore measures observed
    producer contribution and remains non-authoritative.
    """

    if observation.packet_digest != packet.digest:
        raise ValueError("structural observation does not match packet")
    if labels.packet_digest != packet.digest:
        raise ValueError("reference labels do not match packet")
    _validate_provenance_observation(provenance, packet)
    observed = {item.subject_id: item for item in observation.focuses}
    attributed = {item.subject_id: item for item in provenance.focuses}
    expected = {item.subject_id: item for item in labels.focuses}
    if set(observed) != set(attributed) or set(observed) != set(expected):
        raise ValueError("observation, provenance, and reference subjects differ")
    _validate_observation_alignment(observation, provenance)

    disabled = tuple(sorted({item for item in disabled_producers if item}))
    disabled_set = set(disabled)
    subject_kinds = {item.subject_id: item.subject_kind for item in packet.subjects}
    outcomes: list[ProducerOutcome] = []
    for subject_kind in sorted(set(subject_kinds.values())):
        focus_ids = [
            subject_id
            for subject_id, kind in subject_kinds.items()
            if kind == subject_kind
        ]
        removed = 0
        node_fi = node_fe = relation_fi = relation_fe = 0
        for subject_id in focus_ids:
            current = observed[subject_id]
            ref = expected[subject_id]
            focus = attributed[subject_id]
            by_identity = {
                (item.member_kind, item.member_id): item
                for item in focus.memberships
            }
            kept = {
                identity
                for identity, membership in by_identity.items()
                if _membership_survives(membership, disabled_set)
            }
            removed += len(by_identity) - len(kept)
            observed_nodes = {
                item
                for item in (
                    *current.direct_node_ids,
                    *current.suggested_node_ids,
                    *current.context_node_ids,
                    *current.unresolved_node_ids,
                )
                if ("node", item) in kept
            }
            expected_nodes = set(ref.direct_node_ids) | set(ref.context_node_ids)
            if not ref.unresolved:
                node_fi += len(observed_nodes - expected_nodes)
                node_fe += len(expected_nodes - observed_nodes)
            observed_relations = {
                identity[1]
                for identity in kept
                if identity[0] == "relation_group"
                and identity[1] in set(current.exact_relation_ids)
            }
            expected_relations = set(ref.relation_ids)
            if not ref.unresolved:
                relation_fi += len(observed_relations - expected_relations)
                relation_fe += len(expected_relations - observed_relations)
        outcomes.append(
            ProducerOutcome(
                subject_kind=subject_kind,
                disabled_producer=",".join(disabled),
                focus_count=len(focus_ids),
                memberships_removed=removed,
                node_false_inclusions=node_fi,
                node_false_exclusions=node_fe,
                relation_false_inclusions=relation_fi,
                relation_false_exclusions=relation_fe,
            )
        )
    return ProducerCounterfactualReport(
        packet_digest=packet.digest,
        disabled_producers=disabled,
        outcomes=tuple(outcomes),
    )


def _membership_survives(
    membership: StructuralFocusMembership,
    disabled: set[str],
) -> bool:
    return any(item.producer not in disabled for item in membership.provenance)


def _validate_provenance_observation(
    provenance: StructuralFocusProvenanceObservation,
    packet: StructuralCorrectnessPacket,
) -> None:
    if provenance.packet_digest != packet.digest:
        raise ValueError("provenance observation does not match packet")
    expected_subjects = {item.subject_id for item in packet.subjects}
    actual_subjects = {item.subject_id for item in provenance.focuses}
    if actual_subjects != expected_subjects:
        raise ValueError("provenance observation must dispose every subject")
    node_ids = {
        item.file_node_id for item in packet.candidates
    } | {
        item.node_id for item in packet.symbols
    }
    relation_ids = set(packet.relation_ids)
    for focus in provenance.focuses:
        for membership in focus.memberships:
            if membership.member_kind == "node" and membership.member_id not in node_ids:
                raise ValueError("provenance observation contains an unknown node")
            if (
                membership.member_kind == "relation_group"
                and membership.member_id not in relation_ids
            ):
                raise ValueError("provenance observation contains an unknown relation group")
            if not membership.provenance:
                raise ValueError("provenance observation contains empty provenance")


def _validate_observation_alignment(
    observation: StructuralCorrectnessObservation,
    provenance: StructuralFocusProvenanceObservation,
) -> None:
    """Ensure the sidecar copies the observed overlay without reclassifying it."""

    observed = {item.subject_id: item for item in observation.focuses}
    attributed = {item.subject_id: item for item in provenance.focuses}
    if set(observed) != set(attributed):
        raise ValueError("provenance and observation subjects differ")
    for subject_id, current in observed.items():
        memberships = attributed[subject_id].memberships
        by_class: dict[str, set[str]] = {
            "direct": set(),
            "suggested": set(),
            "context": set(),
            "unresolved": set(),
        }
        for membership in memberships:
            if membership.member_kind != "node":
                continue
            bucket = _membership_bucket(membership.membership_class)
            by_class[bucket].add(membership.member_id)
        expected = {
            "direct": set(current.direct_node_ids),
            "suggested": set(current.suggested_node_ids),
            "context": set(current.context_node_ids),
            "unresolved": set(current.unresolved_node_ids),
        }
        if by_class != expected:
            raise ValueError(
                f"provenance node buckets diverge from canonical observation for {subject_id}"
            )
        relation_groups = {
            item.member_id
            for item in memberships
            if item.member_kind == "relation_group"
        }
        if relation_groups != set(current.exact_relation_ids):
            raise ValueError(
                f"provenance relation groups diverge from canonical observation for {subject_id}"
            )


def _membership_bucket(value: StructuralFocusMembershipClass) -> str:
    if value in {"asserted", "matched"}:
        return "direct"
    return value


def _membership_from_mapping(value: Mapping[str, object]) -> StructuralFocusMembership:
    if not isinstance(value, Mapping):
        raise ValueError("provenance membership must be an object")
    raw_provenance = value.get("provenance", [])
    if not isinstance(raw_provenance, list):
        raise ValueError("provenance membership sources must be a list")
    if not all(isinstance(item, Mapping) for item in raw_provenance):
        raise ValueError("provenance membership sources must be objects")
    return StructuralFocusMembership(
        member_kind=cast(str, value["member_kind"]),
        member_id=str(value["member_id"]),
        membership_class=cast(StructuralFocusMembershipClass, value["membership_class"]),
        structural_role=cast(str, value["structural_role"]),
        provenance=tuple(
            _provenance_from_mapping(item)
            for item in raw_provenance
        ),
        relation_ids=tuple(str(item) for item in value.get("relation_ids", [])),
        path_relation_ids=tuple(
            str(item) for item in value.get("path_relation_ids", [])
        ),
    )


def _provenance_from_mapping(value: Mapping[str, object]) -> StructuralFocusProvenance:
    return StructuralFocusProvenance(
        producer=str(value["producer"]),
        admission_class=cast(StructuralFocusMembershipClass, value["admission_class"]),
        source_ids=tuple(str(item) for item in value.get("source_ids", [])),
    )
