from __future__ import annotations

from prismcode.model.contracts import (
    CandidateConvergence,
    ProjectionCandidateSet,
    ReviewProjection,
    ReviewSlice,
)


def build_review_projection(
    candidates: ProjectionCandidateSet,
    convergence: CandidateConvergence,
) -> ReviewProjection:
    """Project converged relation IDs without performing retrieval or selection."""

    relations = candidates.by_id()
    convergence_groups = {
        item.focus_statement_id: item for item in convergence.groups
    }
    slices = []
    for group in candidates.groups:
        converged = convergence_groups[group.focus_statement_id]
        selected = tuple(
            relations[relation_id]
            for relation_id in converged.selected_relation_ids
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
                diagnostic_ids=(
                    *group.diagnostic_ids,
                    *converged.diagnostic_ids,
                ),
            )
        )
    return ReviewProjection(slices=tuple(slices))
