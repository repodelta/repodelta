from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable, Literal

from prismcode.routing.association import evidence_reasons, statement_reasons
from prismcode.model.contracts import (
    AssociationKind,
    AssociationReason,
    CoverageState,
    EvidenceCatalog,
    EvidenceItem,
    ProjectionCandidateGroup,
    ProjectionCandidateSet,
    ProjectionDiagnostic,
    ProjectionRelation,
    ProjectionSlot,
    Requirement,
    ReviewStatement,
)
from prismcode.routing.coverage import review_provider_diagnostics
from prismcode.facts.semantics import (
    anchor_key,
    eligible_changed_anchor,
    evidence_text,
    requirement_profile,
)
from prismcode.routing.selection import relation_key, select_relations
from prismcode.providers.structural import StructuralGraphResult


@dataclass(frozen=True)
class ProjectionPolicy:
    max_claims: int = 2
    max_changed: int = 2
    max_runtime: int = 2
    max_tests: int = 2
    max_verification: int = 1
    max_paths: int = 2
    max_candidates_per_slot: int = 12


def build_projection_candidates(
    *,
    requirements: tuple[Requirement, ...],
    claims: tuple[ReviewStatement, ...],
    evidence_catalog: EvidenceCatalog,
    structural_graph: StructuralGraphResult | None,
    head_sha: str | None,
    claim_source_state: Literal[
        "source_absent", "extraction_missing", "available"
    ] = "available",
    policy: ProjectionPolicy = ProjectionPolicy(),
) -> ProjectionCandidateSet:
    """Route canonical facts into typed per-focus slots without conclusions."""

    evidence = evidence_catalog.by_id()
    changed = tuple(
        sorted(
            (
                item
                for item in evidence.values()
                if item.changed
                and item.kind in {"symbol", "changed_hunk", "changed_file"}
            ),
            key=anchor_key,
        )
    )
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

        claim_relations = _claim_relations(focus, claims)
        claim_relations = select_relations(
            claim_relations,
            slot="claim",
            selected_limit=policy.max_claims,
            candidate_limit=policy.max_candidates_per_slot,
            diagnostics=focus_diagnostics,
            focus_id=focus.id,
        )
        focus_relations.extend(claim_relations)
        selected_claims = {
            relation.target_id
            for relation in claim_relations
            if relation.state == "selected"
        }
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

        eligible_anchors = tuple(
            item for item in changed if eligible_changed_anchor(item, profile, focus)
        )
        anchor_relations = _anchor_relations(
            focus,
            selected_claims,
            claims,
            eligible_anchors,
        )
        anchor_relations = select_relations(
            anchor_relations,
            slot="changed_anchor",
            selected_limit=policy.max_changed,
            candidate_limit=policy.max_candidates_per_slot,
            diagnostics=focus_diagnostics,
            focus_id=focus.id,
        )
        focus_relations.extend(anchor_relations)
        selected_anchor_ids = {
            relation.target_id
            for relation in anchor_relations
            if relation.state == "selected"
        }
        if not anchor_relations:
            state: CoverageState = (
                "source_absent"
                if not changed
                else "unsupported_change_type"
                if all(item.profile == "generated" for item in changed)
                else "no_eligible_fact"
                if not eligible_anchors
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
                selected_anchor_ids,
                evidence,
            ),
            *_provided_context_relations(focus, evidence.values()),
        )
        for slot, selected_limit in (
            ("runtime_context", policy.max_runtime),
            ("test_context", policy.max_tests),
            ("structural_path", policy.max_paths),
        ):
            slot_relations = select_relations(
                tuple(item for item in structural if item.slot == slot),
                slot=slot,
                selected_limit=selected_limit,
                candidate_limit=policy.max_candidates_per_slot,
                diagnostics=focus_diagnostics,
                focus_id=focus.id,
            )
            focus_relations.extend(slot_relations)
            if not slot_relations:
                state, message = _structural_missing(
                    focus,
                    slot,
                    selected_anchor_ids,
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
        verification_relations = select_relations(
            verification_relations,
            slot="verification",
            selected_limit=policy.max_verification,
            candidate_limit=policy.max_candidates_per_slot,
            diagnostics=focus_diagnostics,
            focus_id=focus.id,
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
            focus_diagnostics.append(
                _missing(
                    focus.id,
                    "boundary_fact",
                    "provider_unavailable",
                    (
                        "No bounded repository scan fact was collected for this "
                        "guardrail; selected changed anchors are not absence proof."
                    ),
                )
            )
        else:
            focus_diagnostics.append(
                _missing(
                    focus.id,
                    "boundary_fact",
                    "not_applicable",
                    "Boundary scanning applies only to guardrails.",
                )
            )

        focus_relations = sorted(
            {item.id: item for item in focus_relations}.values(),
            key=relation_key,
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
) -> tuple[ProjectionRelation, ...]:
    result = []
    for claim in claims:
        reasons = statement_reasons(focus, claim)
        if not reasons:
            continue
        result.append(
            _relation(
                focus.id,
                "claim",
                "statement",
                claim.id,
                reasons[0].kind,
                reasons,
            )
        )
    return tuple(sorted(result, key=relation_key))


def _anchor_relations(
    focus: Requirement,
    selected_claim_ids: set[str],
    claims: tuple[ReviewStatement, ...],
    anchors: tuple[EvidenceItem, ...],
) -> tuple[ProjectionRelation, ...]:
    claims_by_id = {item.id: item for item in claims}
    result = []
    for ordinal, anchor in enumerate(anchors):
        provided = anchor.associated_statement_ids
        if focus.id in provided:
            reasons = (
                AssociationReason(
                    kind="provided_association",
                    detail="The provider explicitly associates this fact with the focus.",
                ),
            )
            result.append(
                _relation(
                    focus.id,
                    "changed_anchor",
                    "evidence",
                    anchor.id,
                    "provided_association",
                    reasons,
                    selection_ordinal=ordinal,
                )
            )
            continue
        direct = evidence_reasons(focus, evidence_text(anchor))
        bridges = []
        for claim_id in sorted(selected_claim_ids):
            claim = claims_by_id.get(claim_id)
            if claim is None or not evidence_reasons(claim, evidence_text(anchor)):
                continue
            bridges.append(claim_id)
        if direct:
            result.append(
                _relation(
                    focus.id,
                    "changed_anchor",
                    "evidence",
                    anchor.id,
                    direct[0].kind,
                    direct,
                    selection_ordinal=ordinal,
                )
            )
        elif bridges:
            result.append(
                _relation(
                    focus.id,
                    "changed_anchor",
                    "evidence",
                    anchor.id,
                    "claim_bridge",
                    (
                        AssociationReason(
                            kind="claim_bridge",
                            detail=(
                                "An associated PR claim has a deterministic "
                                "identifier or phrase relation to this changed anchor."
                            ),
                        ),
                    ),
                    bridge_ids=tuple(bridges),
                    selection_ordinal=ordinal,
                )
            )
    return tuple(sorted(result, key=relation_key))


def _structural_relations(
    focus: Requirement,
    selected_anchor_ids: set[str],
    evidence: dict[str, EvidenceItem],
) -> tuple[ProjectionRelation, ...]:
    path_ids = {
        path_id
        for anchor_id in selected_anchor_ids
        if anchor_id in evidence and evidence[anchor_id].kind == "symbol"
        for path_id in evidence[anchor_id].structural_path_ids
    }
    result = []
    for path_id in sorted(path_ids):
        path = evidence.get(path_id)
        if path is None or path.kind != "structural_path":
            continue
        result.append(
            _relation(
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
                bridge_ids=tuple(sorted(selected_anchor_ids)),
            )
        )
        for item in evidence.values():
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
                _relation(
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
                )
            )
    return tuple(sorted(result, key=relation_key))


def _verification_relations(
    focus: Requirement,
    evidence: Iterable[EvidenceItem],
    *,
    head_sha: str | None,
) -> tuple[ProjectionRelation, ...]:
    if not head_sha:
        return ()
    result = []
    for item in evidence:
        if item.profile != "verification":
            continue
        observed_sha = item.observed_head_sha or ""
        if observed_sha != head_sha:
            continue
        result.append(
            _relation(
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
            )
        )
    return tuple(sorted(result, key=relation_key))


def _provided_context_relations(
    focus: Requirement,
    evidence: Iterable[EvidenceItem],
) -> tuple[ProjectionRelation, ...]:
    result = []
    for item in evidence:
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
            _relation(
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
            )
        )
    return tuple(sorted(result, key=relation_key))


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
    selected_anchor_ids: set[str],
    graph: StructuralGraphResult | None,
) -> tuple[CoverageState, str]:
    label = slot.replace("_", " ")
    if not selected_anchor_ids:
        return "not_applicable", f"{label} requires a selected changed anchor."
    if graph is None:
        return "not_applicable", (
            f"{label} was not collected because no structural provider was used."
        )
    if not graph.index.usable:
        return "not_applicable", (
            f"{label} was not collected; review-level provider coverage reports "
            "the structural source state."
        )
    return "no_association", f"No eligible {label} was connected to the selected anchor."


def _relation(
    focus_id: str,
    slot: ProjectionSlot,
    target_type: Literal["statement", "evidence"],
    target_id: str,
    association: AssociationKind,
    reasons: tuple[AssociationReason, ...],
    *,
    bridge_ids: tuple[str, ...] = (),
    selection_ordinal: int = 0,
) -> ProjectionRelation:
    identity = f"{focus_id}\0{slot}\0{target_type}\0{target_id}\0{association}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return ProjectionRelation(
        id=f"PR:{digest}",
        focus_statement_id=focus_id,
        slot=slot,
        target_type=target_type,
        target_id=target_id,
        association=association,
        reasons=reasons,
        bridge_ids=bridge_ids,
        selection_ordinal=selection_ordinal,
    )
