from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import cast

from repodelta.evaluation.focus_membership import canonical_focus_membership_digest
from repodelta.evaluation.structural_correctness import (
    OBSERVATION_SCHEMA,
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


PROVENANCE_OBSERVATION_SCHEMA = "structural_focus_provenance_observation.v2"
COUNTERFACTUAL_SCHEMA = "structural_focus_producer_counterfactual.v3"
_MEMBERSHIP_CLASS_ORDER = {
    "asserted": 0,
    "matched": 1,
    "suggested": 2,
    "context": 3,
    "unresolved": 4,
}


@dataclass(frozen=True)
class ProvenanceFocus:
    """The exact memberships copied from one canonical verification overlay."""

    subject_id: str
    memberships: tuple[StructuralFocusMembership, ...] = ()
    canonical_membership_digest: str = ""

    def __post_init__(self) -> None:
        identities = tuple(
            (item.member_kind, item.member_id) for item in self.memberships
        )
        if len(identities) != len(set(identities)):
            raise ValueError("provenance focus contains duplicate memberships")
        digest = canonical_focus_membership_digest(self.memberships)
        if self.canonical_membership_digest:
            if self.canonical_membership_digest != digest:
                raise ValueError("canonical membership digest mismatch")
        else:
            object.__setattr__(self, "canonical_membership_digest", digest)


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
class ProducerDimensionDelta:
    false_inclusions: int
    false_exclusions: int


@dataclass(frozen=True)
class ProducerObservedDimensions:
    selected_nodes: int
    claimed_direct_nodes: int
    suggested_nodes: int
    structural_context_nodes: int
    unresolved_nodes: int
    exact_relations: int


@dataclass(frozen=True)
class ProducerComparisonDimensions:
    selected_nodes: ProducerDimensionDelta | None
    claimed_direct_nodes: ProducerDimensionDelta | None
    suggested_nodes: ProducerDimensionDelta | None
    structural_context_nodes: ProducerDimensionDelta | None
    unresolved_nodes: ProducerDimensionDelta | None
    exact_relations: ProducerDimensionDelta | None


@dataclass(frozen=True)
class ProducerOutcome:
    subject_kind: str
    disabled_producer: str
    focus_count: int
    comparison_focus_count: int
    memberships_removed: int
    baseline_focus_dispositions: dict[str, int]
    observed: ProducerObservedDimensions
    comparison: ProducerComparisonDimensions


@dataclass(frozen=True)
class ProducerCounterfactualReport:
    packet_digest: str
    disabled_producers: tuple[str, ...]
    provider_coverage_state: str
    provider_seed_mapping_state: str
    outcomes: tuple[ProducerOutcome, ...]
    schema_version: str = COUNTERFACTUAL_SCHEMA


def observe_focus_provenance(
    brief: ReviewBrief,
    packet: StructuralCorrectnessPacket,
    observation: StructuralCorrectnessObservation | None = None,
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
    if set(inspections) != known_subjects:
        missing = sorted(known_subjects - set(inspections))
        unexpected = sorted(set(inspections) - known_subjects)
        detail = []
        if missing:
            detail.append("missing: " + ", ".join(missing))
        if unexpected:
            detail.append("unexpected: " + ", ".join(unexpected))
        raise ValueError(
            "canonical verification inspections do not cover subjects: "
            + "; ".join(detail)
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
    current_observation = observation or observe_structural_correctness(brief, packet)
    if current_observation.packet_digest != packet.digest:
        raise ValueError("structural observation does not match packet")
    _validate_observation_alignment(
        current_observation, result
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
    for focus in raw_focuses:
        memberships = focus.get("memberships", [])
        if not isinstance(memberships, list):
            raise ValueError("provenance focus memberships must be a list")
        digest = focus.get("canonical_membership_digest")
        if not isinstance(digest, str) or not digest:
            raise ValueError(
                "provenance focus requires canonical membership digest"
            )
    packet_digest = raw.get("packet_digest")
    if not isinstance(packet_digest, str) or not packet_digest:
        raise ValueError("provenance observation requires packet identity")
    return StructuralFocusProvenanceObservation(
        packet_digest=packet_digest,
        focuses=tuple(
            ProvenanceFocus(
                subject_id=str(focus["subject_id"]),
                memberships=tuple(
                    _membership_from_mapping(item)
                    for item in focus.get("memberships", [])
                ),
                canonical_membership_digest=str(
                    focus.get("canonical_membership_digest", "")
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
    if observation.schema_version != OBSERVATION_SCHEMA:
        raise ValueError(
            "provenance replay requires a provenance-bound structural observation"
        )
    if any(
        not focus.canonical_membership_digest for focus in observation.focuses
    ):
        raise ValueError(
            "provenance replay requires canonical membership digests"
        )
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
    known_producers = {
        key
        for focus in provenance.focuses
        for membership in focus.memberships
        for provenance_item in membership.provenance
        for key in (
            provenance_item.producer,
            f"{provenance_item.producer}:{provenance_item.admission_class}",
        )
    }
    unknown_producers = disabled_set - known_producers
    if unknown_producers:
        raise ValueError(
            "unknown disabled producer(s): "
            + ", ".join(sorted(unknown_producers))
        )
    subject_kinds = {item.subject_id: item.subject_kind for item in packet.subjects}
    outcomes: list[ProducerOutcome] = []
    for subject_kind in sorted(set(subject_kinds.values())):
        focus_ids = [
            subject_id
            for subject_id, kind in subject_kinds.items()
            if kind == subject_kind
        ]
        removed = 0
        selected_observed = direct_observed = suggested_observed = 0
        context_observed = unresolved_observed = relation_observed = 0
        baseline_focus_dispositions: dict[str, int] = {}
        selected_fi = selected_fe = direct_fi = direct_fe = 0
        relation_fi = relation_fe = 0
        comparison_focus_count = 0
        for subject_id in focus_ids:
            ref = expected[subject_id]
            focus = attributed[subject_id]
            disposition = observed[subject_id].disposition_state
            baseline_focus_dispositions[disposition] = (
                baseline_focus_dispositions.get(disposition, 0) + 1
            )
            surviving: dict[tuple[str, str], StructuralFocusMembershipClass] = {}
            for membership in focus.memberships:
                remaining = _surviving_provenance(membership, disabled_set)
                if not remaining:
                    removed += 1
                    continue
                surviving[(membership.member_kind, membership.member_id)] = (
                    _strongest_membership_class(remaining)
                )
            observed_nodes_by_class = {
                "asserted": set(),
                "matched": set(),
                "suggested": set(),
                "context": set(),
                "unresolved": set(),
            }
            for (member_kind, member_id), membership_class in surviving.items():
                if member_kind == "node":
                    observed_nodes_by_class[membership_class].add(member_id)
            observed_direct = (
                observed_nodes_by_class["asserted"]
                | observed_nodes_by_class["matched"]
            )
            observed_suggested = observed_nodes_by_class["suggested"]
            observed_context = observed_nodes_by_class["context"]
            observed_unresolved = observed_nodes_by_class["unresolved"]
            observed_nodes = set().union(*observed_nodes_by_class.values())
            observed_relations = {
                member_id
                for (member_kind, member_id) in surviving
                if member_kind == "relation_group"
            }
            selected_observed += len(observed_nodes)
            direct_observed += len(observed_direct)
            suggested_observed += len(observed_suggested)
            context_observed += len(observed_context)
            unresolved_observed += len(observed_unresolved)
            relation_observed += len(observed_relations)
            expected_nodes = set(ref.direct_node_ids) | set(ref.context_node_ids)
            if not ref.unresolved:
                comparison_focus_count += 1
                selected_fi += len(observed_nodes - expected_nodes)
                selected_fe += len(expected_nodes - observed_nodes)
                expected_direct = set(ref.direct_node_ids)
                direct_fi += len(observed_direct - expected_direct)
                direct_fe += len(expected_direct - observed_direct)
                expected_relations = set(ref.relation_ids)
                relation_fi += len(observed_relations - expected_relations)
                relation_fe += len(expected_relations - observed_relations)
        outcomes.append(
            ProducerOutcome(
                subject_kind=subject_kind,
                disabled_producer=",".join(disabled),
                focus_count=len(focus_ids),
                comparison_focus_count=comparison_focus_count,
                memberships_removed=removed,
                baseline_focus_dispositions=dict(
                    sorted(baseline_focus_dispositions.items())
                ),
                observed=ProducerObservedDimensions(
                    selected_nodes=selected_observed,
                    claimed_direct_nodes=direct_observed,
                    suggested_nodes=suggested_observed,
                    structural_context_nodes=context_observed,
                    unresolved_nodes=unresolved_observed,
                    exact_relations=relation_observed,
                ),
                comparison=(
                    ProducerComparisonDimensions(
                        selected_nodes=ProducerDimensionDelta(selected_fi, selected_fe),
                        claimed_direct_nodes=ProducerDimensionDelta(direct_fi, direct_fe),
                        suggested_nodes=None,
                        structural_context_nodes=None,
                        unresolved_nodes=None,
                        exact_relations=ProducerDimensionDelta(
                            relation_fi, relation_fe
                        ),
                    )
                    if comparison_focus_count
                    else ProducerComparisonDimensions(
                        selected_nodes=None,
                        claimed_direct_nodes=None,
                        suggested_nodes=None,
                        structural_context_nodes=None,
                        unresolved_nodes=None,
                        exact_relations=None,
                    )
                ),
            )
        )
    return ProducerCounterfactualReport(
        packet_digest=packet.digest,
        disabled_producers=disabled,
        provider_coverage_state=packet.coverage.state,
        provider_seed_mapping_state=packet.coverage.seed_mapping_state,
        outcomes=tuple(outcomes),
    )


def _surviving_provenance(
    membership: StructuralFocusMembership,
    disabled: set[str],
) -> tuple[StructuralFocusProvenance, ...]:
    return tuple(
        item
        for item in membership.provenance
        if item.producer not in disabled
        and f"{item.producer}:{item.admission_class}" not in disabled
    )


def _strongest_membership_class(
    provenance: tuple[StructuralFocusProvenance, ...],
) -> StructuralFocusMembershipClass:
    return min(
        (item.admission_class for item in provenance),
        key=_MEMBERSHIP_CLASS_ORDER.__getitem__,
    )


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
        if not current.canonical_membership_digest:
            raise ValueError(
                f"structural observation lacks canonical provenance binding for {subject_id}"
            )
        if (
            current.canonical_membership_digest
            != attributed[subject_id].canonical_membership_digest
        ):
            raise ValueError(
                f"canonical provenance digest differs for {subject_id}"
            )
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
