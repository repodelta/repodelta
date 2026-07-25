from __future__ import annotations

from prismcode.model.contracts import (
    ProjectionCandidateSet,
    ReviewProjection,
    ReviewSlice,
)


def build_review_projection(
    candidates: ProjectionCandidateSet,
) -> ReviewProjection:
    """Project selected typed relation IDs without performing retrieval."""

    relations = candidates.by_id()
    slices = []
    for group in candidates.groups:
        selected = tuple(
            relations[relation_id]
            for relation_id in group.relation_ids
            if relations[relation_id].state == "selected"
        )
        by_slot = {
            slot: tuple(item.id for item in selected if item.slot == slot)
            for slot in (
                "claim",
                "changed_anchor",
                "runtime_context",
                "test_context",
                "verification",
                "structural_path",
            )
        }
        slices.append(
            ReviewSlice(
                focus_statement_id=group.focus_statement_id,
                claim_relation_ids=by_slot["claim"],
                changed_anchor_relation_ids=by_slot["changed_anchor"],
                runtime_relation_ids=by_slot["runtime_context"],
                test_relation_ids=by_slot["test_context"],
                verification_relation_ids=by_slot["verification"],
                structural_path_relation_ids=by_slot["structural_path"],
                diagnostic_ids=group.diagnostic_ids,
            )
        )
    return ReviewProjection(slices=tuple(slices))
