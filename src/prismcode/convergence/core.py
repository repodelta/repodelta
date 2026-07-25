from __future__ import annotations

from dataclasses import dataclass

from prismcode.model.contracts import (
    AssociationKind,
    CandidateConvergence,
    ConvergenceGroup,
    ProjectionCandidateSet,
    ProjectionDiagnostic,
    ProjectionRelation,
    ProjectionSlot,
)


@dataclass(frozen=True)
class ConvergencePolicy:
    max_claims: int = 2
    max_changed: int = 2
    max_runtime: int = 2
    max_tests: int = 2
    max_verification: int = 1
    max_paths: int = 2
    max_candidates_per_slot: int = 12

    def selected_limit(self, slot: ProjectionSlot) -> int:
        return {
            "claim": self.max_claims,
            "changed_anchor": self.max_changed,
            "runtime_context": self.max_runtime,
            "test_context": self.max_tests,
            "verification": self.max_verification,
            "structural_path": self.max_paths,
            "boundary_fact": 0,
        }[slot]


_SLOT_ORDER: tuple[ProjectionSlot, ...] = (
    "claim",
    "changed_anchor",
    "structural_path",
    "runtime_context",
    "test_context",
    "verification",
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


def converge_candidates(
    candidates: ProjectionCandidateSet,
    *,
    policy: ConvergencePolicy = ConvergencePolicy(),
) -> CandidateConvergence:
    """Converge typed candidates without cross-focus or cross-slot scoring."""

    relations = candidates.by_id()
    groups = []
    diagnostics: list[ProjectionDiagnostic] = []
    for candidate_group in candidates.groups:
        focus_relations = tuple(
            relations[relation_id] for relation_id in candidate_group.relation_ids
        )
        selected_ids: list[str] = []
        deferred_ids: list[str] = []
        focus_diagnostics: list[ProjectionDiagnostic] = []
        selected_targets: dict[ProjectionSlot, set[str]] = {}

        for slot in _SLOT_ORDER:
            raw = tuple(item for item in focus_relations if item.slot == slot)
            eligible = tuple(
                item
                for item in raw
                if _bridge_is_reachable(item, selected_targets)
            )
            unreachable = tuple(item for item in raw if item not in eligible)
            selected, deferred = _converge_slot(
                eligible,
                focus_id=candidate_group.focus_statement_id,
                slot=slot,
                policy=policy,
                diagnostics=focus_diagnostics,
            )
            selected_ids.extend(item.id for item in selected)
            deferred_ids.extend(item.id for item in (*deferred, *unreachable))
            selected_targets[slot] = {item.target_id for item in selected}
            if raw and not eligible:
                focus_diagnostics.append(
                    ProjectionDiagnostic(
                        focus_statement_id=candidate_group.focus_statement_id,
                        slot=slot,
                        state="no_association",
                        message=(
                            f"{slot.replace('_', ' ')} candidates exist, but their "
                            "typed bridge was not selected upstream."
                        ),
                        affected_ids=tuple(item.target_id for item in unreachable),
                    )
                )

        covered = set(selected_ids) | set(deferred_ids)
        deferred_ids.extend(
            item.id for item in focus_relations if item.id not in covered
        )
        focus_diagnostics = list(
            {item.id: item for item in focus_diagnostics}.values()
        )
        diagnostics.extend(focus_diagnostics)
        groups.append(
            ConvergenceGroup(
                focus_statement_id=candidate_group.focus_statement_id,
                selected_relation_ids=tuple(selected_ids),
                deferred_relation_ids=tuple(deferred_ids),
                diagnostic_ids=tuple(item.id for item in focus_diagnostics),
            )
        )
    return CandidateConvergence(
        groups=tuple(groups),
        diagnostics=tuple(diagnostics),
    )


def relation_key(item: ProjectionRelation) -> tuple[object, ...]:
    return (
        item.slot,
        _semantic_tier(item),
        item.source_ordinal,
        item.target_id,
    )


def _semantic_tier(item: ProjectionRelation) -> int:
    return _ASSOCIATION_ORDER[item.association]


def _bridge_is_reachable(
    relation: ProjectionRelation,
    selected_targets: dict[ProjectionSlot, set[str]],
) -> bool:
    if relation.association == "claim_bridge":
        return bool(
            set(relation.bridge_ids) & selected_targets.get("claim", set())
        )
    if relation.slot == "structural_path":
        return bool(
            set(relation.bridge_ids)
            & selected_targets.get("changed_anchor", set())
        )
    if (
        relation.slot in {"runtime_context", "test_context"}
        and relation.association == "structural_bridge"
    ):
        return bool(
            set(relation.bridge_ids)
            & selected_targets.get("structural_path", set())
        )
    return True


def _converge_slot(
    relations: tuple[ProjectionRelation, ...],
    *,
    focus_id: str,
    slot: ProjectionSlot,
    policy: ConvergencePolicy,
    diagnostics: list[ProjectionDiagnostic],
) -> tuple[tuple[ProjectionRelation, ...], tuple[ProjectionRelation, ...]]:
    ordered = tuple(sorted(relations, key=relation_key))
    inspected = ordered[: policy.max_candidates_per_slot]
    uninspected = ordered[policy.max_candidates_per_slot :]
    if uninspected:
        diagnostics.append(
            ProjectionDiagnostic(
                focus_statement_id=focus_id,
                slot=slot,
                state="budget_truncated",
                message=(
                    f"{slot.replace('_', ' ')} candidate inspection stopped at "
                    f"{policy.max_candidates_per_slot} items for {focus_id}."
                ),
                affected_ids=tuple(item.target_id for item in uninspected),
            )
        )

    selected_limit = policy.selected_limit(slot)
    selected = inspected[:selected_limit]
    deferred = (*inspected[selected_limit:], *uninspected)
    if selected and len(ordered) > selected_limit:
        cutoff_tier = _semantic_tier(selected[-1])
        next_tier = _semantic_tier(ordered[selected_limit])
        if cutoff_tier == next_tier:
            tied = tuple(
                item.target_id
                for item in ordered
                if _semantic_tier(item) == cutoff_tier
            )
            diagnostics.append(
                ProjectionDiagnostic(
                    focus_statement_id=focus_id,
                    slot=slot,
                    state="ambiguous",
                    message=(
                        f"{slot.replace('_', ' ')} display budget cuts through "
                        "an equivalent semantic tier; stable source order is only "
                        "a presentation tie-break."
                    ),
                    affected_ids=tied,
                )
            )
    return selected, tuple(deferred)
