"""Evaluation-only attribution for R/G association candidates.

The production projection already owns the association relation, its reasons,
and its convergence decision.  This module copies that information into a
separate sidecar so evaluation can inspect why a changed anchor was admitted
without teaching the structural overlay or renderer a second association
algorithm.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Mapping, cast

from repodelta.evaluation.structural_correctness import StructuralCorrectnessPacket
from repodelta.model.contracts import (
    AssociationKind,
    AssociationReason,
    FocusEvidenceRole,
    ProjectionSlot,
    ReviewBrief,
    StructuralFocusMembershipClass,
    VerificationSubjectKind,
)


ASSOCIATION_ATTRIBUTION_SCHEMA = "structural_association_attribution.v1"
AssociationSourceChannel = Literal[
    "statement",
    "evidence",
    "bridge",
    "structural",
    "verification",
]
AssociationCandidateState = Literal["selected", "deferred"]
_SUBJECT_KINDS = frozenset({"requirement", "guardrail"})
_ASSOCIATIONS = frozenset(
    {
        "provided_association",
        "explicit_reference",
        "exact_identifier",
        "distinctive_phrase",
        "claim_bridge",
        "structural_bridge",
        "current_head",
    }
)
_MEMBERSHIP_CLASSES = frozenset(
    {"asserted", "matched", "suggested", "context", "unresolved"}
)


@dataclass(frozen=True)
class AssociationAttributionRow:
    """One R/G changed-anchor candidate and its observed projection join."""

    subject_id: str
    subject_kind: VerificationSubjectKind
    relation_id: str
    slot: ProjectionSlot
    target_type: Literal["statement", "evidence"]
    target_id: str
    association: AssociationKind
    reasons: tuple[AssociationReason, ...]
    matched_terms: tuple[str, ...]
    source_channel: AssociationSourceChannel
    evidence_role: FocusEvidenceRole
    bridge_ids: tuple[str, ...]
    candidate_state: AssociationCandidateState
    structural_member_id: str | None = None
    structural_membership_class: StructuralFocusMembershipClass | None = None

    def __post_init__(self) -> None:
        if self.subject_kind not in _SUBJECT_KINDS:
            raise ValueError("association attribution requires an R/G subject")
        if self.slot != "changed_anchor" or self.target_type != "evidence":
            raise ValueError(
                "association attribution rows must be changed-anchor evidence"
            )
        if not self.relation_id or not self.target_id:
            raise ValueError("association attribution requires canonical identities")
        if self.association not in _ASSOCIATIONS:
            raise ValueError(f"unsupported association kind: {self.association}")
        if not self.reasons or self.reasons[0].kind != self.association:
            raise ValueError(
                "association attribution requires reasons led by its association"
            )
        expected_terms = tuple(
            dict.fromkeys(
                term
                for reason in self.reasons
                for term in reason.matched_terms
            )
        )
        if self.matched_terms != expected_terms:
            raise ValueError("association attribution matched terms are not canonical")
        if self.source_channel != _source_channel_for_association(
            self.association
        ):
            raise ValueError("association attribution source channel is not canonical")
        if self.candidate_state not in {"selected", "deferred"}:
            raise ValueError("association attribution has invalid candidate state")
        if (self.structural_member_id is None) != (
            self.structural_membership_class is None
        ):
            raise ValueError(
                "association attribution member identity and class must be paired"
            )
        if (
            self.structural_membership_class is not None
            and self.structural_membership_class not in _MEMBERSHIP_CLASSES
        ):
            raise ValueError("association attribution has invalid membership class")


@dataclass(frozen=True)
class AssociationAttributionObservation:
    """A reproducible copy of R/G association candidate provenance."""

    packet_digest: str
    rows: tuple[AssociationAttributionRow, ...] = ()
    schema_version: str = ASSOCIATION_ATTRIBUTION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != ASSOCIATION_ATTRIBUTION_SCHEMA:
            raise ValueError("unsupported association attribution schema")
        if not self.packet_digest:
            raise ValueError("association attribution requires packet identity")
        relation_ids = tuple(item.relation_id for item in self.rows)
        if len(relation_ids) != len(set(relation_ids)):
            raise ValueError("association attribution contains duplicate relations")
        if relation_ids != tuple(
            sorted(relation_ids, key=lambda value: value)
        ):
            raise ValueError("association attribution rows must be canonicalized")


def observe_association_attribution(
    brief: ReviewBrief,
    packet: StructuralCorrectnessPacket,
) -> AssociationAttributionObservation:
    """Copy candidate relations and convergence state without re-selection."""

    from repodelta.evaluation.structural_correctness import (
        prepare_structural_correctness_packet,
    )

    current = prepare_structural_correctness_packet(brief)
    if current != packet:
        raise ValueError("structural correctness packet does not match current review")

    subjects = {item.subject_id: item.subject_kind for item in packet.subjects}
    candidate_groups = {
        item.focus_statement_id: item
        for item in brief.projection_candidates.groups
    }
    convergence_groups = {
        item.focus_statement_id: item
        for item in brief.candidate_convergence.groups
    }
    inspections = {
        item.subject_id: item
        for item in brief.projection.verification_workspace.inspections
    }
    relation_by_id = brief.projection_candidates.by_id()
    rows: list[AssociationAttributionRow] = []
    for relation in relation_by_id.values():
        subject_kind = subjects.get(relation.focus_statement_id)
        if subject_kind not in _SUBJECT_KINDS or relation.slot != "changed_anchor":
            continue
        candidate_group = candidate_groups.get(relation.focus_statement_id)
        convergence_group = convergence_groups.get(relation.focus_statement_id)
        if candidate_group is None or convergence_group is None:
            raise ValueError(
                f"missing candidate/convergence group for {relation.focus_statement_id}"
            )
        if relation.id not in candidate_group.relation_ids:
            raise ValueError(
                f"association relation {relation.id} is outside its candidate group"
            )
        if relation.id in convergence_group.selected_relation_ids:
            state: AssociationCandidateState = "selected"
        elif relation.id in convergence_group.deferred_relation_ids:
            state = "deferred"
        else:
            raise ValueError(
                f"association relation {relation.id} is outside convergence"
            )
        membership = _membership_for_relation(
            inspections.get(relation.focus_statement_id),
            relation.id,
        )
        reasons = tuple(relation.reasons)
        rows.append(
            AssociationAttributionRow(
                subject_id=relation.focus_statement_id,
                subject_kind=cast(VerificationSubjectKind, subject_kind),
                relation_id=relation.id,
                slot=relation.slot,
                target_type=relation.target_type,
                target_id=relation.target_id,
                association=relation.association,
                reasons=reasons,
                matched_terms=tuple(
                    dict.fromkeys(
                        term
                        for reason in reasons
                        for term in reason.matched_terms
                    )
                ),
                source_channel=_source_channel_for_association(
                    relation.association
                ),
                evidence_role=relation.evidence_role,
                bridge_ids=tuple(relation.bridge_ids),
                candidate_state=state,
                structural_member_id=(membership.member_id if membership else None),
                structural_membership_class=(
                    membership.membership_class if membership else None
                ),
            )
        )
    result = AssociationAttributionObservation(
        packet_digest=packet.digest,
        rows=tuple(sorted(rows, key=lambda item: item.relation_id)),
    )
    _validate_against_candidates(result, brief)
    return result


def write_association_attribution(
    value: AssociationAttributionObservation,
    output: str | Path,
) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(value), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def load_association_attribution(
    path: str | Path,
) -> AssociationAttributionObservation:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("association attribution must be an object")
    if raw.get("schema_version") != ASSOCIATION_ATTRIBUTION_SCHEMA:
        raise ValueError("unsupported association attribution schema")
    raw_rows = raw.get("rows", [])
    if not isinstance(raw_rows, list) or not all(
        isinstance(item, Mapping) for item in raw_rows
    ):
        raise ValueError("association attribution rows must be objects")
    rows = tuple(_row_from_mapping(item) for item in raw_rows)
    return AssociationAttributionObservation(
        packet_digest=_string(raw, "packet_digest"),
        rows=tuple(sorted(rows, key=lambda item: item.relation_id)),
        schema_version=str(raw["schema_version"]),
    )


def _row_from_mapping(value: Mapping[str, object]) -> AssociationAttributionRow:
    raw_reasons = value.get("reasons", [])
    if not isinstance(raw_reasons, list) or not all(
        isinstance(item, Mapping) for item in raw_reasons
    ):
        raise ValueError("association attribution reasons must be objects")
    reasons = tuple(
        AssociationReason(
            kind=cast(AssociationKind, _string(item, "kind")),
            detail=_string(item, "detail"),
            matched_terms=_strings(item.get("matched_terms", [])),
        )
        for item in raw_reasons
    )
    return AssociationAttributionRow(
        subject_id=_string(value, "subject_id"),
        subject_kind=cast(VerificationSubjectKind, _string(value, "subject_kind")),
        relation_id=_string(value, "relation_id"),
        slot=cast(ProjectionSlot, _string(value, "slot")),
        target_type=cast(
            Literal["statement", "evidence"], _string(value, "target_type")
        ),
        target_id=_string(value, "target_id"),
        association=cast(AssociationKind, _string(value, "association")),
        reasons=reasons,
        matched_terms=_strings(value.get("matched_terms", [])),
        source_channel=cast(AssociationSourceChannel, _string(value, "source_channel")),
        evidence_role=cast(FocusEvidenceRole, _string(value, "evidence_role")),
        bridge_ids=_strings(value.get("bridge_ids", [])),
        candidate_state=cast(
            AssociationCandidateState, _string(value, "candidate_state")
        ),
        structural_member_id=(
            str(value["structural_member_id"])
            if value.get("structural_member_id") is not None
            else None
        ),
        structural_membership_class=(
            cast(
                StructuralFocusMembershipClass,
                str(value["structural_membership_class"]),
            )
            if value.get("structural_membership_class") is not None
            else None
        ),
    )


def _membership_for_relation(inspection, relation_id: str):
    if inspection is None:
        return None
    matches = tuple(
        item
        for item in inspection.structural_overlay.nodes
        if relation_id in item.relation_ids
    )
    if len(matches) > 1:
        raise ValueError(
            f"association relation {relation_id} maps to multiple structural nodes"
        )
    return matches[0] if matches else None


def _validate_against_candidates(
    attribution: AssociationAttributionObservation,
    brief: ReviewBrief,
) -> None:
    relations = {
        item.id: item
        for item in brief.projection_candidates.relations
        if item.slot == "changed_anchor"
        and item.focus_statement_id in {
            focus.id
            for focus in (*brief.requirements, *brief.guardrails)
        }
    }
    if set(relations) != {item.relation_id for item in attribution.rows}:
        raise ValueError(
            "association attribution must cover every R/G changed-anchor candidate"
        )
    for row in attribution.rows:
        relation = relations[row.relation_id]
        if row.target_id != relation.target_id or row.reasons != relation.reasons:
            raise ValueError(
                "association attribution diverges from candidate relation "
                f"{row.relation_id}"
            )


def _source_channel_for_association(
    association: AssociationKind,
) -> AssociationSourceChannel:
    if association == "claim_bridge":
        return "bridge"
    if association == "structural_bridge":
        return "structural"
    if association == "current_head":
        return "verification"
    if association == "explicit_reference":
        return "statement"
    return "evidence"


def _string(value: Mapping[str, object], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError(f"association attribution requires non-empty {key}")
    return result


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("association attribution string fields must be lists")
    return tuple(value)
