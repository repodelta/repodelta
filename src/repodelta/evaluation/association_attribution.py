"""Evaluation-only attribution for R/G association candidates.

The production projection already owns the association relation, its reasons,
and its convergence decision.  This module copies that information into a
separate sidecar so evaluation can inspect why a changed anchor was admitted
without teaching the structural overlay or renderer a second association
algorithm.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, cast

from repodelta.evaluation.structural_correctness import (
    StructuralCorrectnessLabels,
    StructuralCorrectnessObservation,
    StructuralCorrectnessPacket,
)
from repodelta.model.contracts import (
    AssociationKind,
    AssociationReason,
    FocusEvidenceRole,
    ProjectionSlot,
    ReviewBrief,
    StructuralFocusMembershipClass,
    VerificationSubjectKind,
)
from repodelta.model.structural_refs import review_symbol_id


ASSOCIATION_ATTRIBUTION_SCHEMA = "structural_association_attribution.v2"
ASSOCIATION_COMPARISON_SCHEMA = "structural_association_comparison.v1"
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
    candidate_node_id: str | None = None
    structural_member_id: str | None = None
    structural_membership_class: StructuralFocusMembershipClass | None = None
    lineage_node_ids: tuple[str, ...] = ()
    lineage_relation_group_ids: tuple[str, ...] = ()

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
        if self.structural_member_id is not None and self.candidate_node_id not in {
            None,
            self.structural_member_id,
        }:
            raise ValueError(
                "observed structural member must equal the candidate node"
            )
        if self.candidate_node_id is None and (
            self.lineage_node_ids or self.lineage_relation_group_ids
        ):
            raise ValueError(
                "association lineage requires a candidate structural node"
            )
        if len(self.lineage_node_ids) != len(set(self.lineage_node_ids)):
            raise ValueError("association lineage contains duplicate nodes")
        if len(self.lineage_relation_group_ids) != len(
            set(self.lineage_relation_group_ids)
        ):
            raise ValueError("association lineage contains duplicate relations")
        if tuple(sorted(self.lineage_node_ids)) != self.lineage_node_ids:
            raise ValueError("association lineage nodes must be canonicalized")
        if tuple(sorted(self.lineage_relation_group_ids)) != (
            self.lineage_relation_group_ids
        ):
            raise ValueError("association lineage relations must be canonicalized")
        if self.structural_member_id is None and (
            self.lineage_node_ids or self.lineage_relation_group_ids
        ):
            raise ValueError(
                "association lineage requires an observed structural member"
            )


@dataclass(frozen=True)
class AssociationAttributionObservation:
    """A reproducible copy of R/G association candidate provenance."""

    packet_digest: str
    rows: tuple[AssociationAttributionRow, ...] = ()
    subject_kinds: tuple[tuple[str, VerificationSubjectKind], ...] = ()
    schema_version: str = ASSOCIATION_ATTRIBUTION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != ASSOCIATION_ATTRIBUTION_SCHEMA:
            raise ValueError("unsupported association attribution schema")
        if not self.packet_digest:
            raise ValueError("association attribution requires packet identity")
        subject_ids = tuple(item[0] for item in self.subject_kinds)
        if len(subject_ids) != len(set(subject_ids)):
            raise ValueError("association attribution contains duplicate subjects")
        if subject_ids != tuple(sorted(subject_ids)):
            raise ValueError("association attribution subjects must be canonicalized")
        if any(
            subject_kind not in _SUBJECT_KINDS
            for _, subject_kind in self.subject_kinds
        ):
            raise ValueError("association attribution subjects must be R/G")
        relation_ids = tuple(item.relation_id for item in self.rows)
        if len(relation_ids) != len(set(relation_ids)):
            raise ValueError("association attribution contains duplicate relations")
        if relation_ids != tuple(
            sorted(relation_ids, key=lambda value: value)
        ):
            raise ValueError("association attribution rows must be canonicalized")
        if any(
            item.subject_id not in set(subject_ids) for item in self.rows
        ):
            raise ValueError("association attribution row has unknown subject")


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
    rg_subject_kinds = tuple(
        sorted(
            (subject_id, subject_kind)
            for subject_id, subject_kind in subjects.items()
            if subject_kind in _SUBJECT_KINDS
        )
    )
    candidate_groups = {
        item.focus_statement_id: item
        for item in brief.projection_candidates.groups
    }
    convergence_groups = {
        item.focus_statement_id: item
        for item in brief.candidate_convergence.groups
    }
    evidence = brief.evidence_catalog.by_id()
    inspections = {
        item.subject_id: item
        for item in brief.projection.verification_workspace.inspections
    }
    candidate_node_ids_by_review_symbol = _candidate_node_ids_by_review_symbol(
        brief
    )
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
        candidate_fact = evidence.get(relation.target_id)
        candidate_node_id = candidate_node_ids_by_review_symbol.get(
            review_symbol_id(candidate_fact)
            if candidate_fact is not None
            else None
        )
        lineage_nodes, lineage_relations = _observed_lineage(
            brief,
            inspections.get(relation.focus_statement_id),
            membership.member_id if membership is not None else None,
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
                candidate_node_id=candidate_node_id,
                structural_member_id=(membership.member_id if membership else None),
                structural_membership_class=(
                    membership.membership_class if membership else None
                ),
                lineage_node_ids=lineage_nodes,
                lineage_relation_group_ids=lineage_relations,
            )
        )
    result = AssociationAttributionObservation(
        packet_digest=packet.digest,
        rows=tuple(sorted(rows, key=lambda item: item.relation_id)),
        subject_kinds=rg_subject_kinds,
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
        subject_kinds=tuple(
            sorted(
                _subject_kind_pair(item)
                for item in _subject_kind_values(raw.get("subject_kinds", []))
            )
        ),
        schema_version=str(raw["schema_version"]),
    )


def compare_association_attribution(
    attribution: AssociationAttributionObservation,
    observation: StructuralCorrectnessObservation,
    labels: StructuralCorrectnessLabels,
) -> dict[str, Any]:
    """Compare association-linked observed membership with frozen references.

    This is deliberately a diagnostic comparison, not a causal replay. A node
    or relation is assigned to a reason only when a recorded candidate row's
    observed lineage names it; otherwise it is reported as ``unattributed``.
    Suggestions and unresolved memberships remain observed-only because the
    v1.1 reference contract labels semantic direct/context membership, not
    epistemic buckets.
    """

    if attribution.packet_digest != observation.packet_digest:
        raise ValueError("association attribution does not match observation")
    if labels.packet_digest != observation.packet_digest:
        raise ValueError("reference labels do not match observation")
    observed = {item.subject_id: item for item in observation.focuses}
    references = {item.subject_id: item for item in labels.focuses}
    attribution_subject_ids = {
        subject_id for subject_id, _ in attribution.subject_kinds
    }
    if not attribution_subject_ids <= set(observed) or not (
        attribution_subject_ids <= set(references)
    ):
        raise ValueError("association comparison subject is missing")
    rows_by_focus: dict[str, tuple[AssociationAttributionRow, ...]] = {}
    for subject_id in observed:
        rows_by_focus[subject_id] = tuple(
            item for item in attribution.rows if item.subject_id == subject_id
        )

    dimensions = (
        "selected_nodes",
        "claimed_direct_nodes",
        "structural_context_nodes",
        "exact_relations",
    )
    totals = {
        dimension: {"false_inclusions": 0, "false_exclusions": 0}
        for dimension in dimensions
    }
    reason_totals: dict[tuple[str, str], dict[str, dict[str, int]]] = {}
    reason_involvement_totals: dict[
        tuple[str, str], dict[str, dict[str, int]]
    ] = {}
    subject_kind_by_id = dict(attribution.subject_kinds)
    if not set(subject_kind_by_id) <= set(observed):
        raise ValueError("association attribution subject is missing from observation")
    per_focus: list[dict[str, Any]] = []
    for subject_id in sorted(subject_kind_by_id):
        reference = references[subject_id]
        current = observed[subject_id]
        rows = rows_by_focus[subject_id]
        subject_kind = subject_kind_by_id.get(subject_id, "unknown")
        by_node_lineage = _rows_by_lineage(rows, "node")
        by_relation_lineage = _rows_by_lineage(rows, "relation_group")
        by_candidate_node = _rows_by_candidate_node(rows)
        focus_result: dict[str, Any] = {
            "subject_id": subject_id,
            "subject_kind": subject_kind,
            "reference_unresolved": reference.unresolved,
            "candidate_rows": len(rows),
            "dimensions": {},
        }
        if reference.unresolved:
            focus_result["dimensions"]["suggested_nodes"] = {
                "observed": len(current.suggested_node_ids),
                "comparison": "reference_unresolved",
            }
            focus_result["dimensions"]["unresolved_nodes"] = {
                "observed": len(current.unresolved_node_ids),
                "comparison": "reference_unresolved",
            }
            per_focus.append(focus_result)
            continue
        expected_by_dimension = {
            "selected_nodes": set(reference.direct_node_ids)
            | set(reference.context_node_ids),
            "claimed_direct_nodes": set(reference.direct_node_ids),
            "structural_context_nodes": set(reference.context_node_ids),
            "exact_relations": set(reference.relation_ids),
        }
        actual_by_dimension = {
            "selected_nodes": set(current.selected_node_ids),
            "claimed_direct_nodes": set(current.direct_node_ids),
            "structural_context_nodes": set(current.context_node_ids),
            "exact_relations": set(current.exact_relation_ids),
        }
        for dimension in dimensions:
            expected = expected_by_dimension[dimension]
            actual = actual_by_dimension[dimension]
            false_inclusions = actual - expected
            false_exclusions = expected - actual
            result = {
                "false_inclusions": len(false_inclusions),
                "false_exclusions": len(false_exclusions),
                "false_inclusions_by_reason": _bucket_members(
                    false_inclusions,
                    by_node_lineage
                    if dimension != "exact_relations"
                    else by_relation_lineage,
                ),
                "false_exclusions_by_reason": _bucket_members(
                    false_exclusions,
                    by_candidate_node
                    if dimension != "exact_relations"
                    else {},
                ),
                "false_inclusions_by_reason_involved": _bucket_members_involved(
                    false_inclusions,
                    by_node_lineage
                    if dimension != "exact_relations"
                    else by_relation_lineage,
                ),
                "false_exclusions_by_reason_involved": _bucket_members_involved(
                    false_exclusions,
                    by_candidate_node
                    if dimension != "exact_relations"
                    else {},
                ),
            }
            focus_result["dimensions"][dimension] = result
            for key in ("false_inclusions", "false_exclusions"):
                totals[dimension][key] += result[key]
            _accumulate_reason_totals(
                reason_totals,
                subject_kind,
                dimension,
                result["false_inclusions_by_reason"],
                result["false_exclusions_by_reason"],
            )
            _accumulate_reason_totals(
                reason_involvement_totals,
                subject_kind,
                dimension,
                result["false_inclusions_by_reason_involved"],
                result["false_exclusions_by_reason_involved"],
            )
        focus_result["dimensions"]["suggested_nodes"] = {
            "observed": len(current.suggested_node_ids),
            "comparison": "observed_only",
        }
        focus_result["dimensions"]["unresolved_nodes"] = {
            "observed": len(current.unresolved_node_ids),
            "comparison": "observed_only",
        }
        per_focus.append(focus_result)

    return {
        "schema_version": ASSOCIATION_COMPARISON_SCHEMA,
        "packet_digest": attribution.packet_digest,
        "reference_status": labels.authority.status,
        "attribution_mode": "root_linked_observed_lineage",
        "causal_replay": False,
        "overall": totals,
        "reason_breakdown": _reason_breakdown(
            attribution, reason_totals, reason_involvement_totals
        ),
        "per_focus": per_focus,
        "limits": {
            "suggested_nodes": "observed_only; v1.1 has no suggestion reference",
            "unresolved_nodes": "observed_only; v1.1 unresolved is focus-level",
            "unattributed": (
                "membership has no recorded R/G changed-anchor lineage; "
                "no association reason is inferred"
            ),
            "reason_involvement": (
                "comparison_involved is non-exclusive: a member reachable from "
                "multiple recorded roots is counted for each associated reason; "
                "comparison remains the exclusive ambiguity-aware view"
            ),
        },
    }


def write_association_comparison(
    value: Mapping[str, Any],
    output: str | Path,
) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def aggregate_association_comparisons(
    comparisons: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Aggregate per-PR association comparisons without changing their meaning.

    The aggregate is a convenience view over already validated comparison
    artifacts.  It keeps the exclusive ambiguity-aware breakdown and the
    non-exclusive reason-involvement breakdown separate, so totals cannot be
    mistaken for a causal producer replay.
    """

    if not comparisons:
        raise ValueError("association comparison aggregate requires samples")
    for name, comparison in comparisons.items():
        if comparison.get("schema_version") != ASSOCIATION_COMPARISON_SCHEMA:
            raise ValueError(f"unsupported association comparison in {name}")
    dimensions = (
        "selected_nodes",
        "claimed_direct_nodes",
        "structural_context_nodes",
        "exact_relations",
    )
    overall = {
        dimension: {"false_inclusions": 0, "false_exclusions": 0}
        for dimension in dimensions
    }
    observed_only = {"suggested_nodes": 0, "unresolved_nodes": 0}
    by_reason: dict[tuple[str, str], dict[str, Any]] = {}
    for comparison in comparisons.values():
        for dimension in dimensions:
            for field in ("false_inclusions", "false_exclusions"):
                overall[dimension][field] += comparison["overall"][dimension][
                    field
                ]
        for focus in comparison["per_focus"]:
            for dimension in observed_only:
                observed_only[dimension] += focus["dimensions"][dimension][
                    "observed"
                ]
        for item in comparison["reason_breakdown"]:
            key = (item["subject_kind"], item["association"])
            entry = by_reason.setdefault(
                key,
                {
                    "subject_kind": item["subject_kind"],
                    "association": item["association"],
                    "candidate_count": 0,
                    "selected_count": 0,
                    "deferred_count": 0,
                    "observed_anchor_memberships": 0,
                    "observed_membership_classes": {},
                    "comparison": {
                        dimension: {
                            "false_inclusions": 0,
                            "false_exclusions": 0,
                        }
                        for dimension in dimensions
                    },
                    "comparison_involved": {
                        dimension: {
                            "false_inclusions": 0,
                            "false_exclusions": 0,
                        }
                        for dimension in dimensions
                    },
                },
            )
            for field in (
                "candidate_count",
                "selected_count",
                "deferred_count",
                "observed_anchor_memberships",
            ):
                entry[field] += item[field]
            for membership_class, count in item[
                "observed_membership_classes"
            ].items():
                entry["observed_membership_classes"][membership_class] = (
                    entry["observed_membership_classes"].get(membership_class, 0)
                    + count
                )
            for view in ("comparison", "comparison_involved"):
                for dimension in dimensions:
                    for field in ("false_inclusions", "false_exclusions"):
                        entry[view][dimension][field] += item.get(view, {}).get(
                            dimension, {}
                        ).get(field, 0)
    return {
        "schema_version": "structural_association_attribution_summary.v1",
        "sample_count": len(comparisons),
        "samples": sorted(comparisons),
        "overall": overall,
        "observed_only": observed_only,
        "by_reason": [
            {
                **entry,
                "observed_membership_classes": dict(
                    sorted(entry["observed_membership_classes"].items())
                ),
            }
            for _, entry in sorted(by_reason.items())
        ],
        "limits": {
            "causal_replay": False,
            "suggestions_and_unresolved": (
                "observed-only; v1.1 has no per-membership semantic reference"
            ),
            "reason_breakdown": (
                "comparison is exclusive and ambiguity-aware; "
                "comparison_involved is non-exclusive"
            ),
        },
    }


def _rows_by_lineage(
    rows: tuple[AssociationAttributionRow, ...],
    member_kind: Literal["node", "relation_group"],
) -> dict[str, tuple[AssociationAttributionRow, ...]]:
    result: dict[str, list[AssociationAttributionRow]] = defaultdict(list)
    for row in rows:
        identities = (
            row.lineage_node_ids
            if member_kind == "node"
            else row.lineage_relation_group_ids
        )
        for identity in identities:
            result[identity].append(row)
    return {key: tuple(value) for key, value in result.items()}


def _rows_by_candidate_node(
    rows: tuple[AssociationAttributionRow, ...],
) -> dict[str, tuple[AssociationAttributionRow, ...]]:
    result: dict[str, list[AssociationAttributionRow]] = defaultdict(list)
    for row in rows:
        if row.candidate_node_id is not None:
            result[row.candidate_node_id].append(row)
    return {key: tuple(value) for key, value in result.items()}


def _bucket_members(
    members: set[str],
    rows_by_member: Mapping[str, tuple[AssociationAttributionRow, ...]],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for member_id in sorted(members):
        rows = rows_by_member.get(member_id, ())
        associations = sorted({item.association for item in rows})
        bucket = (
            associations[0]
            if len(associations) == 1
            else "multiple"
            if associations
            else "unattributed"
        )
        counts[bucket] = counts.get(bucket, 0) + 1
    return dict(sorted(counts.items()))


def _bucket_members_involved(
    members: set[str],
    rows_by_member: Mapping[str, tuple[AssociationAttributionRow, ...]],
) -> dict[str, int]:
    """Count every recorded reason involved in a member's lineage.

    This view is intentionally non-exclusive.  It makes a statement such as
    "all 38 direct false inclusions involved exact_identifier" machine-checkable
    while retaining the separate ``multiple`` bucket when a member is reachable
    from more than one candidate root.
    """

    counts: dict[str, int] = {}
    for member_id in sorted(members):
        associations = sorted(
            {item.association for item in rows_by_member.get(member_id, ())}
        )
        if not associations:
            associations = ["unattributed"]
        for association in associations:
            counts[association] = counts.get(association, 0) + 1
    return dict(sorted(counts.items()))


def _accumulate_reason_totals(
    totals: dict[tuple[str, str], dict[str, dict[str, int]]],
    subject_kind: str,
    dimension: str,
    false_inclusions: Mapping[str, int],
    false_exclusions: Mapping[str, int],
) -> None:
    for bucket in set(false_inclusions) | set(false_exclusions):
        key = (subject_kind, bucket)
        dimension_totals = totals.setdefault(
            key,
            {
                name: {"false_inclusions": 0, "false_exclusions": 0}
                for name in (
                    "selected_nodes",
                    "claimed_direct_nodes",
                    "structural_context_nodes",
                    "exact_relations",
                )
            },
        )
        dimension_totals[dimension]["false_inclusions"] += false_inclusions.get(
            bucket, 0
        )
        dimension_totals[dimension]["false_exclusions"] += false_exclusions.get(
            bucket, 0
        )


def _reason_breakdown(
    attribution: AssociationAttributionObservation,
    reason_totals: Mapping[tuple[str, str], Mapping[str, Mapping[str, int]]],
    reason_involvement_totals: Mapping[
        tuple[str, str], Mapping[str, Mapping[str, int]]
    ],
) -> list[dict[str, Any]]:
    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    observed_members: dict[tuple[str, str], set[str]] = defaultdict(set)
    observed_classes: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for row in attribution.rows:
        key = (row.subject_kind, row.association)
        entry = candidates.setdefault(
            key,
            {
                "subject_kind": row.subject_kind,
                "association": row.association,
                "candidate_count": 0,
                "selected_count": 0,
                "deferred_count": 0,
            },
        )
        entry["candidate_count"] += 1
        entry[f"{row.candidate_state}_count"] += 1
        if row.structural_member_id is not None:
            observed_members[key].add(row.structural_member_id)
            assert row.structural_membership_class is not None
            observed_classes[key][row.structural_membership_class] += 1
    result = []
    for key in sorted(candidates):
        entry = dict(candidates[key])
        entry["observed_anchor_memberships"] = len(observed_members[key])
        entry["observed_membership_classes"] = dict(
            sorted(observed_classes[key].items())
        )
        entry["comparison"] = {
            dimension: dict(counts)
            for dimension, counts in sorted(reason_totals.get(key, {}).items())
        }
        entry["comparison_involved"] = {
            dimension: dict(counts)
            for dimension, counts in sorted(
                reason_involvement_totals.get(key, {}).items()
            )
        }
        result.append(entry)
    return result


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
        candidate_node_id=(
            str(value["candidate_node_id"])
            if value.get("candidate_node_id") is not None
            else None
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
        lineage_node_ids=_strings(value.get("lineage_node_ids", [])),
        lineage_relation_group_ids=_strings(
            value.get("lineage_relation_group_ids", [])
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


def _candidate_node_ids_by_review_symbol(brief: ReviewBrief) -> dict[str, str]:
    result: dict[str, str] = {}
    for node in brief.projection.review_graph.nodes:
        previous = result.get(node.review_symbol_id)
        if previous is not None and previous != node.id:
            raise ValueError(
                "association attribution found duplicate structural node identity "
                f"for {node.review_symbol_id}"
            )
        result[node.review_symbol_id] = node.id
    return result


def _observed_lineage(
    brief: ReviewBrief,
    inspection,
    root_node_id: str | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return observed graph members reachable from one selected anchor.

    This is a consumer-local lineage join over the already selected overlay.
    It does not add members, rerun closure, or claim that a downstream member
    would disappear in a producer counterfactual.
    """

    if inspection is None or root_node_id is None:
        return (), ()
    overlay = inspection.structural_overlay
    node_ids = {item.member_id for item in overlay.nodes}
    if root_node_id not in node_ids:
        return (), ()
    adjacency: dict[str, set[str]] = defaultdict(set)

    def connect(source: str, target: str) -> None:
        if source in node_ids and target in node_ids:
            adjacency[source].add(target)
            adjacency[target].add(source)

    graph = brief.projection.review_graph
    edge_ids = set(overlay.edge_ids)
    for edge in graph.edges:
        if edge.id in edge_ids:
            connect(edge.source_node_id, edge.target_node_id)
    ownership_ids = set(overlay.ownership_edge_ids)
    for edge in graph.ownership_edges:
        if edge.id in ownership_ids:
            connect(edge.parent_node_id, edge.child_node_id)
    placement_ids = set(overlay.placement_ids)
    for placement in graph.placements:
        if placement.id in placement_ids:
            connect(placement.parent_node_id, placement.child_node_id)

    reachable = {root_node_id}
    frontier = deque((root_node_id,))
    while frontier:
        current = frontier.popleft()
        for neighbor in adjacency[current]:
            if neighbor not in reachable:
                reachable.add(neighbor)
                frontier.append(neighbor)

    graph_edges = {item.id: item for item in graph.edges}
    lineage_groups = []
    for group in graph.relation_groups:
        if group.id not in overlay.relation_group_ids:
            continue
        if any(
            edge_id in graph_edges
            and reachable.intersection(
                {
                    graph_edges[edge_id].source_node_id,
                    graph_edges[edge_id].target_node_id,
                }
            )
            for edge_id in group.member_edge_ids
        ):
            lineage_groups.append(group.id)
    return tuple(sorted(reachable)), tuple(sorted(lineage_groups))


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


def _subject_kind_values(value: object) -> tuple[object, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, (Mapping, list, tuple)) for item in value
    ):
        raise ValueError("association attribution subject kinds must be pairs")
    return tuple(value)


def _subject_kind_pair(value: object) -> tuple[str, VerificationSubjectKind]:
    if isinstance(value, Mapping):
        return (
            _string(value, "subject_id"),
            cast(VerificationSubjectKind, _string(value, "subject_kind")),
        )
    if isinstance(value, (list, tuple)) and len(value) == 2:
        subject_id, subject_kind = value
        if isinstance(subject_id, str) and isinstance(subject_kind, str):
            return (
                subject_id,
                cast(VerificationSubjectKind, subject_kind),
            )
    raise ValueError("association attribution subject kind must be a pair")
