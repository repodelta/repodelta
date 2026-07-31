from __future__ import annotations

from typing import Iterable, Literal

from prismcode.routing.association import (
    distinctive_text_terms,
    statement_reasons,
)
from prismcode.model.contracts import (
    AssociationReason,
    CoverageState,
    EvidenceCatalog,
    EvidenceItem,
    ClosureScanPlanSet,
    ProjectionCandidateGroup,
    ProjectionCandidateSet,
    ProjectionDiagnostic,
    ProjectionRelation,
    ProjectionSlot,
    Requirement,
    ReviewStatement,
)
from prismcode.routing.coverage import review_provider_diagnostics
from prismcode.routing.focus_anchors import associate_focus_anchors
from prismcode.routing.relations import candidate_key, projection_relation
from prismcode.routing.semantics import (
    anchor_key,
    requirement_profile,
)
from prismcode.providers.structural import StructuralGraphCollection


def build_projection_candidates(
    *,
    requirements: tuple[Requirement, ...],
    claims: tuple[ReviewStatement, ...],
    evidence_catalog: EvidenceCatalog,
    structural_graph: StructuralGraphCollection | None,
    head_sha: str | None,
    claim_source_state: Literal[
        "source_absent", "extraction_missing", "available"
    ] = "available",
    closure_scan_plans: ClosureScanPlanSet = ClosureScanPlanSet(),
) -> ProjectionCandidateSet:
    """Enumerate typed per-focus candidates without selecting or truncating."""

    evidence = evidence_catalog.by_id()
    changed = tuple(
        sorted(
            (
                item
                for item in evidence.values()
                if item.changed
                and item.kind
                in {"structural_change", "change_relation", "changed_file"}
            ),
            key=anchor_key,
        )
    )
    focus_distinctive_terms = distinctive_text_terms(
        tuple((item.id, item.text) for item in requirements)
    )
    claim_distinctive_terms = distinctive_text_terms(
        tuple((item.id, item.text) for item in claims)
    )
    plans_by_statement = closure_scan_plans.by_statement_id()
    relations: list[ProjectionRelation] = []
    groups: list[ProjectionCandidateGroup] = []
    diagnostics: list[ProjectionDiagnostic] = list(
        review_provider_diagnostics(structural_graph)
    )
    if not requirements:
        diagnostics.append(
            ProjectionDiagnostic(
                focus_statement_id="I1",
                slot="claim",
                state="source_absent",
                message=(
                    "No explicit acceptance criteria found. Intent and PR claims "
                    "remain context and were not promoted to requirements."
                ),
            )
        )

    for focus in requirements:
        profile = requirement_profile(focus)
        focus_relations: list[ProjectionRelation] = []
        focus_diagnostics: list[ProjectionDiagnostic] = []

        claim_relations = _claim_relations(
            focus,
            claims,
            focus_distinctive_terms=focus_distinctive_terms.get(
                focus.id,
                frozenset(),
            ),
        )
        focus_relations.extend(claim_relations)
        associated_claims = {relation.target_id for relation in claim_relations}
        if not claim_relations:
            claim_state: CoverageState = (
                "source_absent"
                if claim_source_state == "source_absent"
                else "no_eligible_fact"
                if claim_source_state == "extraction_missing"
                else "no_association"
            )
            focus_diagnostics.append(
                _missing(
                    focus.id,
                    "claim",
                    claim_state,
                    {
                        "source_absent": "No PR description source was collected.",
                        "no_eligible_fact": (
                            "A PR description was collected, but no typed claim "
                            "was extracted from its recognized sections."
                        ),
                        "no_association": (
                            "Typed PR claims exist, but none has a deterministic "
                            "association with this focus."
                        ),
                    }[claim_state],
                )
            )

        anchor_associations = associate_focus_anchors(
            focus,
            associated_claims,
            claims,
            changed,
            focus_distinctive_terms=focus_distinctive_terms.get(
                focus.id,
                frozenset(),
            ),
            claim_distinctive_terms=claim_distinctive_terms,
            profile=profile,
        )
        anchor_relations = anchor_associations.relations
        eligible_anchor_ids = anchor_associations.eligible_anchor_ids
        focus_relations.extend(anchor_relations)
        candidate_anchor_ids = tuple(
            relation.target_id for relation in anchor_relations
        )
        if not anchor_relations:
            state: CoverageState = (
                "source_absent"
                if not changed
                else "unsupported_change_type"
                if all(item.profile == "generated" for item in changed)
                else "no_eligible_fact"
                if not eligible_anchor_ids
                else "no_association"
            )
            focus_diagnostics.append(
                _missing(
                    focus.id,
                    "changed_anchor",
                    state,
                    {
                        "source_absent": "No changed repository anchor was collected.",
                        "unsupported_change_type": (
                            "Only generated/vendor changed facts were collected; "
                            "the current profile has no deterministic routing strategy."
                        ),
                        "no_eligible_fact": (
                            f"Changed facts exist, but none is eligible for the "
                            f"{profile} profile."
                        ),
                        "no_association": (
                            "Eligible changed anchors exist, but no deterministic "
                            "association was found."
                        ),
                    }[state],
                )
            )

        structural = (
            *_structural_relations(
                focus,
                candidate_anchor_ids,
                evidence,
            ),
            *_provided_context_relations(focus, evidence.values()),
        )
        for slot in ("runtime_context", "test_context", "structural_path"):
            slot_relations = tuple(item for item in structural if item.slot == slot)
            focus_relations.extend(slot_relations)
            if not slot_relations:
                state, message = _structural_missing(
                    focus,
                    slot,
                    candidate_anchor_ids,
                    structural_graph,
                )
                if not any(
                    item.slot == slot and item.state == state
                    for item in focus_diagnostics
                ):
                    focus_diagnostics.append(
                        _missing(focus.id, slot, state, message)
                    )

        verification_relations = _verification_relations(
            focus,
            evidence.values(),
            head_sha=head_sha,
        )
        focus_relations.extend(verification_relations)
        if not verification_relations:
            observations = tuple(
                item for item in evidence.values() if item.profile == "verification"
            )
            state = "stale_source" if observations else "source_absent"
            message = (
                "Verification observations exist, but none matches the current head."
                if observations
                else "No current-head verification observation was collected."
            )
            focus_diagnostics.append(
                _missing(focus.id, "verification", state, message)
            )

        if focus.kind == "guardrail":
            plan = plans_by_statement.get(focus.id)
            closure_facts = tuple(
                item
                for item in evidence.values()
                if item.role == "closure_fact"
                and item.associated_statement_ids == (focus.id,)
            )
            result = (
                closure_facts[0].closure_scan_result
                if closure_facts
                else None
            )
            for ordinal, fact in enumerate(closure_facts):
                focus_relations.append(
                    projection_relation(
                        focus.id,
                        "closure_fact",
                        "evidence",
                        fact.id,
                        "provided_association",
                        (
                            AssociationReason(
                                kind="provided_association",
                                detail=(
                                    "The bounded scan provider explicitly "
                                    "associates this observation with the guardrail."
                                ),
                            ),
                        ),
                        source_ordinal=ordinal,
                    )
                )
            if result is None:
                diagnostic = next(
                    (
                        item
                        for item in evidence_catalog.closure_scan_diagnostics
                        if item.statement_id == focus.id
                        or (plan is not None and item.plan_id == plan.id)
                    ),
                    None,
                )
                focus_diagnostics.append(
                    _missing(
                        focus.id,
                        "closure_fact",
                        (
                            "stale_source"
                            if diagnostic
                            and diagnostic.code == "closure_scan_stale_checkout"
                            else "provider_unavailable"
                        ),
                        (
                            diagnostic.message
                            if diagnostic is not None
                            else (
                                f"Closure scan plan {plan.id} exists, but no "
                                "bounded repository scan fact was collected."
                                if plan is not None
                                else "No canonical closure scan plan applies."
                            )
                        ),
                        affected_ids=(plan.id,) if plan is not None else (),
                    )
                )
            elif any(
                item.state == "partial" for item in result.revisions
            ):
                focus_diagnostics.append(
                    _missing(
                        focus.id,
                        "closure_fact",
                        "partial_coverage",
                        (
                            "A bounded closure scan fact was collected, but one "
                            "or more planned surfaces have incomplete coverage."
                        ),
                        affected_ids=(result.id,),
                    )
                )
        else:
            focus_diagnostics.append(
                _missing(
                    focus.id,
                    "closure_fact",
                    "not_applicable",
                    "Closure scanning applies only to guardrails.",
                )
            )

        focus_relations = sorted(
            {item.id: item for item in focus_relations}.values(),
            key=candidate_key,
        )
        focus_diagnostics = list(
            {
                (
                    item.focus_statement_id,
                    item.slot,
                    item.state,
                    item.message,
                ): item
                for item in focus_diagnostics
            }.values()
        )
        relations.extend(focus_relations)
        diagnostics.extend(focus_diagnostics)
        groups.append(
            ProjectionCandidateGroup(
                focus_statement_id=focus.id,
                profile=profile,
                relation_ids=tuple(item.id for item in focus_relations),
                diagnostic_ids=tuple(item.id for item in focus_diagnostics),
            )
        )

    return ProjectionCandidateSet(
        relations=tuple(relations),
        groups=tuple(groups),
        diagnostics=tuple(diagnostics),
    )


def _claim_relations(
    focus: Requirement,
    claims: tuple[ReviewStatement, ...],
    *,
    focus_distinctive_terms: frozenset[str],
) -> tuple[ProjectionRelation, ...]:
    result = []
    for ordinal, claim in enumerate(claims):
        reasons = statement_reasons(
            focus,
            claim,
            distinctive_terms=focus_distinctive_terms,
        )
        if not reasons:
            continue
        result.append(
            projection_relation(
                focus.id,
                "claim",
                "statement",
                claim.id,
                reasons[0].kind,
                reasons,
                source_ordinal=ordinal,
            )
        )
    return tuple(sorted(result, key=candidate_key))


def _structural_relations(
    focus: Requirement,
    candidate_anchor_ids: tuple[str, ...],
    evidence: dict[str, EvidenceItem],
) -> tuple[ProjectionRelation, ...]:
    path_ids = tuple(
        dict.fromkeys(
            path_id
            for anchor_id in candidate_anchor_ids
            if anchor_id in evidence
            for path_id in evidence[anchor_id].structural_path_ids
        )
    )
    result = []
    for path_ordinal, path_id in enumerate(path_ids):
        path = evidence.get(path_id)
        if path is None or path.kind != "structural_path":
            continue
        anchor_ids = tuple(
            sorted(
                anchor_id
                for anchor_id in candidate_anchor_ids
                if anchor_id in evidence
                and path_id in evidence[anchor_id].structural_path_ids
            )
        )
        result.append(
            projection_relation(
                focus.id,
                "structural_path",
                "evidence",
                path.id,
                "structural_bridge",
                (
                    AssociationReason(
                        kind="structural_bridge",
                        detail="The bounded path is rooted in a selected exact changed anchor.",
                    ),
                ),
                bridge_ids=anchor_ids,
                source_ordinal=path_ordinal,
            )
        )
        for item_ordinal, item in enumerate(evidence.values()):
            if item.changed or path_id not in item.structural_path_ids:
                continue
            slot: ProjectionSlot | None = (
                "test_context"
                if item.profile == "test"
                else "runtime_context"
                if item.profile == "production"
                else None
            )
            if slot is None:
                continue
            result.append(
                projection_relation(
                    focus.id,
                    slot,
                    "evidence",
                    item.id,
                    "structural_bridge",
                    (
                        AssociationReason(
                            kind="structural_bridge",
                            detail=(
                                "The unchanged symbol occurs on a bounded path "
                                "rooted in a selected changed anchor."
                            ),
                        ),
                    ),
                    bridge_ids=(path_id,),
                    source_ordinal=item_ordinal,
                )
            )
    return tuple(sorted(result, key=candidate_key))


def _verification_relations(
    focus: Requirement,
    evidence: Iterable[EvidenceItem],
    *,
    head_sha: str | None,
) -> tuple[ProjectionRelation, ...]:
    if not head_sha:
        return ()
    result = []
    for ordinal, item in enumerate(evidence):
        if item.profile != "verification":
            continue
        observed_sha = item.observed_head_sha or ""
        if observed_sha != head_sha:
            continue
        result.append(
            projection_relation(
                focus.id,
                "verification",
                "evidence",
                item.id,
                "current_head",
                (
                    AssociationReason(
                        kind="current_head",
                        detail="The observation belongs to the analyzed PR head.",
                    ),
                ),
                source_ordinal=ordinal,
            )
        )
    return tuple(sorted(result, key=candidate_key))


def _provided_context_relations(
    focus: Requirement,
    evidence: Iterable[EvidenceItem],
) -> tuple[ProjectionRelation, ...]:
    result = []
    for ordinal, item in enumerate(evidence):
        if item.changed or focus.id not in item.associated_statement_ids:
            continue
        slot: ProjectionSlot | None = (
            "test_context"
            if item.profile == "test"
            else "runtime_context"
            if item.profile == "production"
            else None
        )
        if slot is None:
            continue
        result.append(
            projection_relation(
                focus.id,
                slot,
                "evidence",
                item.id,
                "provided_association",
                (
                    AssociationReason(
                        kind="provided_association",
                        detail=(
                            "The supplied provider explicitly associates this "
                            "context fact with the focus."
                        ),
                    ),
                ),
                source_ordinal=ordinal,
            )
        )
    return tuple(sorted(result, key=candidate_key))


def _missing(
    focus_id: str,
    slot: ProjectionSlot,
    state: CoverageState,
    message: str,
    *,
    affected_ids: tuple[str, ...] = (),
) -> ProjectionDiagnostic:
    return ProjectionDiagnostic(
        focus_statement_id=focus_id,
        slot=slot,
        state=state,
        message=message,
        affected_ids=affected_ids,
    )


def _structural_missing(
    focus: Requirement,
    slot: ProjectionSlot,
    candidate_anchor_ids: tuple[str, ...],
    graph: StructuralGraphCollection | None,
) -> tuple[CoverageState, str]:
    label = slot.replace("_", " ")
    if not candidate_anchor_ids:
        return "not_applicable", f"{label} requires a selected changed anchor."
    if graph is None:
        return "not_applicable", (
            f"{label} was not collected because no structural provider was used."
        )
    head = graph.for_revision("head")
    if head is None or not head.index.usable:
        return "not_applicable", (
            f"{label} was not collected; review-level provider coverage reports "
            "the structural source state."
        )
    return "no_association", f"No eligible {label} was connected to the selected anchor."
