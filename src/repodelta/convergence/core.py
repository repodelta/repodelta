from __future__ import annotations

from dataclasses import dataclass

from repodelta.convergence.ordering import relation_key, semantic_tier
from repodelta.convergence.structural import converge_structural_closure
from repodelta.model.contracts import (
    AssociationKind,
    CandidateConvergence,
    ConvergenceGroup,
    EvidenceCatalog,
    EvidenceItem,
    ProjectionCandidateSet,
    ProjectionDiagnostic,
    ProjectionRelation,
    ProjectionSlot,
    ReviewRelevantStructuralClosure,
)


@dataclass(frozen=True)
class ConvergencePolicy:
    max_claims: int = 2
    max_direct_anchor_identities: int = 20
    max_bridged_anchor_identities: int = 10
    max_anchor_identities: int = 30
    max_paths_per_anchor: int = 5
    max_path_identities: int = 30
    max_runtime_context_identities: int = 20
    max_test_context_identities: int = 20
    max_verification_identities: int = 20
    max_candidates_per_slot: int = 12

    def selected_limit(self, slot: ProjectionSlot) -> int:
        return {
            "claim": self.max_claims,
            "closure_fact": 1,
        }[slot]


_SLOT_ORDER: tuple[ProjectionSlot, ...] = (
    "claim",
    "changed_anchor",
    "structural_path",
    "runtime_context",
    "test_context",
    "verification",
    "closure_fact",
)
_DIRECT_ANCHOR_ASSOCIATIONS: frozenset[AssociationKind] = frozenset(
    {
        "provided_association",
        "explicit_reference",
        "exact_identifier",
        "distinctive_phrase",
    }
)


def converge_candidates(
    candidates: ProjectionCandidateSet,
    *,
    evidence_catalog: EvidenceCatalog,
    policy: ConvergencePolicy = ConvergencePolicy(),
) -> CandidateConvergence:
    """Converge typed candidates without cross-focus or cross-slot scoring."""

    relations = candidates.by_id()
    evidence = evidence_catalog.by_id()
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
        structural_closure = ReviewRelevantStructuralClosure()

        for slot in _SLOT_ORDER:
            if slot in {"runtime_context", "test_context"}:
                continue
            raw = tuple(item for item in focus_relations if item.slot == slot)
            eligible = tuple(
                item
                for item in raw
                if _bridge_is_reachable(item, selected_targets)
            )
            unreachable = tuple(item for item in raw if item not in eligible)
            if slot == "changed_anchor":
                selected, deferred = _converge_changed_anchor_slot(
                    eligible,
                    focus_id=candidate_group.focus_statement_id,
                    policy=policy,
                    diagnostics=focus_diagnostics,
                )
            elif slot == "structural_path":
                runtime = tuple(
                    item for item in focus_relations
                    if item.slot == "runtime_context"
                )
                tests = tuple(
                    item for item in focus_relations
                    if item.slot == "test_context"
                )
                structural = converge_structural_closure(
                    paths=eligible,
                    unreachable_paths=unreachable,
                    runtime=runtime,
                    tests=tests,
                    evidence=evidence,
                    selected_anchor_ids=selected_targets.get(
                        "changed_anchor",
                        set(),
                    ),
                    focus_id=candidate_group.focus_statement_id,
                    max_paths_per_anchor=policy.max_paths_per_anchor,
                    max_path_identities=policy.max_path_identities,
                    max_runtime_context_identities=(
                        policy.max_runtime_context_identities
                    ),
                    max_test_context_identities=(
                        policy.max_test_context_identities
                    ),
                    diagnostics=focus_diagnostics,
                )
                selected = structural.selected
                deferred = structural.deferred
                structural_closure = structural.closure
                for context_slot in ("runtime_context", "test_context"):
                    selected_targets[context_slot] = {
                        item.target_id
                        for item in selected
                        if item.slot == context_slot
                    }
                unreachable = ()
            elif slot == "verification":
                selected, deferred = _converge_verification_slot(
                    eligible,
                    evidence=evidence,
                    focus_id=candidate_group.focus_statement_id,
                    identity_limit=policy.max_verification_identities,
                    diagnostics=focus_diagnostics,
                )
            else:
                selected, deferred = _converge_competitive_slot(
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
                upstream = slot in {
                    "structural_path",
                    "runtime_context",
                    "test_context",
                }
                focus_diagnostics.append(
                    ProjectionDiagnostic(
                        focus_statement_id=candidate_group.focus_statement_id,
                        slot=slot,
                        state="upstream_deferred" if upstream else "no_association",
                        message=(
                            f"{slot.replace('_', ' ')} candidates exist, but all "
                            "depend on canonical upstream identities deferred by "
                            "a safety boundary."
                            if upstream
                            else f"{slot.replace('_', ' ')} candidates exist, but "
                            "their typed bridge was not selected upstream."
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
                structural_closure=structural_closure,
                diagnostic_ids=tuple(item.id for item in focus_diagnostics),
            )
        )
    return CandidateConvergence(
        groups=tuple(groups),
        diagnostics=tuple(diagnostics),
    )


def _semantic_tier(item: ProjectionRelation) -> int:
    return semantic_tier(item)


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


def _converge_competitive_slot(
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


def _converge_changed_anchor_slot(
    relations: tuple[ProjectionRelation, ...],
    *,
    focus_id: str,
    policy: ConvergencePolicy,
    diagnostics: list[ProjectionDiagnostic],
) -> tuple[tuple[ProjectionRelation, ...], tuple[ProjectionRelation, ...]]:
    """Retain a bounded set of canonical changed anchors; anchors do not compete."""

    by_target: dict[str, list[ProjectionRelation]] = {}
    for relation in relations:
        by_target.setdefault(relation.target_id, []).append(relation)

    canonical = []
    duplicates = []
    for target_relations in by_target.values():
        ordered = tuple(sorted(target_relations, key=relation_key))
        canonical.append(ordered[0])
        duplicates.extend(ordered[1:])

    direct = tuple(
        sorted(
            (
                item
                for item in canonical
                if item.association in _DIRECT_ANCHOR_ASSOCIATIONS
            ),
            key=relation_key,
        )
    )
    bridged = tuple(
        sorted(
            (item for item in canonical if item.association == "claim_bridge"),
            key=relation_key,
        )
    )
    unsupported = tuple(
        sorted(
            (
                item
                for item in canonical
                if item.association not in _DIRECT_ANCHOR_ASSOCIATIONS
                and item.association != "claim_bridge"
            ),
            key=relation_key,
        )
    )
    if unsupported:
        raise ValueError(
            "changed-anchor convergence received unsupported associations: "
            + ", ".join(sorted({item.association for item in unsupported}))
        )

    within_class_limits = (
        *direct[: policy.max_direct_anchor_identities],
        *bridged[: policy.max_bridged_anchor_identities],
    )
    selected = tuple(within_class_limits[: policy.max_anchor_identities])
    selected_ids = {item.id for item in selected}
    deferred = tuple(
        item
        for item in (
            *direct,
            *bridged,
            *sorted(duplicates, key=relation_key),
        )
        if item.id not in selected_ids
    )
    omitted_canonical = tuple(
        item for item in (*direct, *bridged) if item.id not in selected_ids
    )
    if omitted_canonical:
        diagnostics.append(
            ProjectionDiagnostic(
                focus_statement_id=focus_id,
                slot="changed_anchor",
                state="budget_truncated",
                message=(
                    f"{len(canonical)} canonical changed anchors were associated "
                    f"with {focus_id}; {len(selected)} are retained within direct "
                    f"({policy.max_direct_anchor_identities}), claim-bridged "
                    f"({policy.max_bridged_anchor_identities}), and total "
                    f"({policy.max_anchor_identities}) identity safety limits."
                ),
                affected_ids=tuple(item.target_id for item in omitted_canonical),
            )
        )
    return selected, deferred


def _converge_verification_slot(
    relations: tuple[ProjectionRelation, ...],
    *,
    evidence: dict[str, EvidenceItem],
    focus_id: str,
    identity_limit: int,
    diagnostics: list[ProjectionDiagnostic],
) -> tuple[tuple[ProjectionRelation, ...], tuple[ProjectionRelation, ...]]:
    """Retain a bounded set of distinct checks; checks do not compete."""

    by_identity: dict[tuple[str, str, str], list[ProjectionRelation]] = {}
    for relation in relations:
        fact = evidence.get(relation.target_id)
        if fact is None or fact.verification_identity is None:
            raise ValueError(
                f"{relation.id}: verification relation has no canonical identity"
            )
        identity = fact.verification_identity
        by_identity.setdefault(
            (identity.provider, identity.kind, identity.name),
            [],
        ).append(relation)

    converged = []
    for identity, identity_relations in by_identity.items():
        canonical = _canonical_verification_relations(
            tuple(identity_relations),
            evidence=evidence,
        )
        outcomes = {
            _verification_outcome(evidence[item.target_id])
            for item in canonical
        }
        if len(outcomes) > 1:
            diagnostics.append(
                ProjectionDiagnostic(
                    focus_statement_id=focus_id,
                    slot="verification",
                    state="conflicting_facts",
                    message=(
                        "Conflicting completed outcomes were collected for "
                        f"{identity[0]}:{identity[1]}:{identity[2]}."
                    ),
                    affected_ids=tuple(item.target_id for item in canonical),
                )
            )
        converged.append(
            (
                _verification_identity_priority(canonical, evidence),
                identity,
                canonical,
                tuple(
                    item
                    for item in identity_relations
                    if item.id not in {selected.id for selected in canonical}
                ),
            )
        )

    ordered = tuple(sorted(converged, key=lambda item: (item[0], item[1])))
    kept = ordered[:identity_limit]
    omitted = ordered[identity_limit:]
    selected = tuple(
        relation
        for _, _, canonical, _ in kept
        for relation in canonical
    )
    deferred = tuple(
        relation
        for _, _, _, duplicates in kept
        for relation in duplicates
    ) + tuple(
        relation
        for _, _, canonical, duplicates in omitted
        for relation in (*canonical, *duplicates)
    )
    if omitted:
        diagnostics.append(
            ProjectionDiagnostic(
                focus_statement_id=focus_id,
                slot="verification",
                state="budget_truncated",
                message=(
                    f"{len(ordered)} distinct current-head checks were collected; "
                    f"{identity_limit} are shown and {len(omitted)} are deferred "
                    "by the verification safety limit."
                ),
                affected_ids=tuple(
                    relation.target_id
                    for _, _, canonical, duplicates in omitted
                    for relation in (*canonical, *duplicates)
                ),
            )
        )
    return selected, deferred


def _canonical_verification_relations(
    relations: tuple[ProjectionRelation, ...],
    *,
    evidence: dict[str, EvidenceItem],
) -> tuple[ProjectionRelation, ...]:
    ordered = tuple(
        sorted(
            relations,
            key=lambda item: (
                0
                if evidence[item.target_id].verification_status == "completed"
                else 1,
                0
                if evidence[item.target_id].verification_conclusion
                else 1,
                item.source_ordinal,
                item.target_id,
            ),
        )
    )
    completed_by_outcome: dict[str, ProjectionRelation] = {}
    for relation in ordered:
        fact = evidence[relation.target_id]
        if fact.verification_status != "completed":
            continue
        outcome = _verification_outcome(fact)
        if outcome != "unknown":
            completed_by_outcome.setdefault(outcome, relation)
    if len(completed_by_outcome) > 1:
        return tuple(
            completed_by_outcome[outcome]
            for outcome in ("failure", "pending", "success")
            if outcome in completed_by_outcome
        )
    return ordered[:1]


def _verification_identity_priority(
    relations: tuple[ProjectionRelation, ...],
    evidence: dict[str, EvidenceItem],
) -> int:
    outcomes = {
        _verification_outcome(evidence[item.target_id])
        for item in relations
    }
    if "failure" in outcomes:
        return 0
    if "pending" in outcomes:
        return 1
    if "success" in outcomes:
        return 2
    return 3


def _verification_outcome(item: EvidenceItem) -> str:
    conclusion = item.verification_conclusion
    if conclusion in {
        "failure",
        "failed",
        "error",
        "cancelled",
        "timed_out",
        "action_required",
    }:
        return "failure"
    if conclusion in {"success", "neutral", "skipped"}:
        return "success"
    if item.verification_status not in {"completed", "complete"} or conclusion == "pending":
        return "pending"
    return "unknown"
