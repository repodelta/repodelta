from __future__ import annotations

from dataclasses import replace

from .contracts import (
    AssociationKind,
    ProjectionDiagnostic,
    ProjectionRelation,
    ProjectionSlot,
)

_ASSOCIATION_ORDER: dict[AssociationKind, int] = {
    "provided_association": 0,
    "explicit_reference": 1,
    "exact_identifier": 2,
    "distinctive_phrase": 3,
    "claim_bridge": 4,
    "structural_bridge": 5,
    "current_head": 6,
}


def relation_key(item: ProjectionRelation) -> tuple[object, ...]:
    return (
        item.slot,
        _ASSOCIATION_ORDER[item.association],
        item.selection_ordinal,
        item.target_id,
    )


def select_relations(
    relations: tuple[ProjectionRelation, ...],
    *,
    slot: ProjectionSlot,
    selected_limit: int,
    candidate_limit: int,
    diagnostics: list[ProjectionDiagnostic],
    focus_id: str,
) -> tuple[ProjectionRelation, ...]:
    ordered = tuple(sorted(relations, key=relation_key))
    kept = ordered[:candidate_limit]
    result = tuple(
        replace(item, state="selected" if index < selected_limit else "not_selected")
        for index, item in enumerate(kept)
    )
    if len(ordered) > candidate_limit:
        diagnostics.append(
            ProjectionDiagnostic(
                focus_statement_id=focus_id,
                slot=slot,
                state="budget_truncated",
                message=(
                    f"{slot.replace('_', ' ')} candidate inspection stopped at "
                    f"{candidate_limit} items for {focus_id}."
                ),
                affected_ids=tuple(
                    item.target_id for item in ordered[candidate_limit:]
                ),
            )
        )
    return result
