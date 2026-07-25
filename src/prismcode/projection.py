from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from typing import Iterable, Literal

from .contracts import (
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
    RequirementProfile,
    ReviewProjection,
    ReviewSlice,
    ReviewStatement,
)
from .matching import semantic_tokens
from .structural_graph import StructuralGraphResult

_REFERENCE_RE = re.compile(r"\b(?:R|G|AC|REQ)[-_ ]?\d+\b", re.IGNORECASE)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")
_ASSOCIATION_ORDER: dict[AssociationKind, int] = {
    "provided_association": 0,
    "explicit_reference": 1,
    "exact_identifier": 2,
    "distinctive_phrase": 3,
    "claim_bridge": 4,
    "structural_bridge": 5,
    "current_head": 6,
    "boundary_scan": 7,
}


@dataclass(frozen=True)
class ProjectionPolicy:
    max_claims: int = 2
    max_changed: int = 2
    max_runtime: int = 2
    max_tests: int = 2
    max_verification: int = 1
    max_paths: int = 2
    max_boundary: int = 2
    max_candidates_per_slot: int = 12


def build_projection_candidates(
    *,
    requirements: tuple[Requirement, ...],
    claims: tuple[ReviewStatement, ...],
    evidence_catalog: EvidenceCatalog,
    structural_graph: StructuralGraphResult | None,
    head_sha: str | None,
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
            key=_anchor_key,
        )
    )
    relations: list[ProjectionRelation] = []
    groups: list[ProjectionCandidateGroup] = []
    diagnostics: list[ProjectionDiagnostic] = []
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
        profile = _requirement_profile(focus)
        focus_relations: list[ProjectionRelation] = []
        focus_diagnostics: list[ProjectionDiagnostic] = []

        claim_relations = _claim_relations(focus, claims)
        claim_relations = _bound(
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
            focus_diagnostics.append(
                _missing(
                    focus.id,
                    "claim",
                    "source_absent" if not claims else "no_association",
                    "No PR-authored claim was available."
                    if not claims
                    else "No deterministic PR-claim association was found.",
                )
            )

        eligible_anchors = tuple(
            item for item in changed if _eligible_anchor(item, profile)
        )
        anchor_relations = _anchor_relations(
            focus,
            selected_claims,
            claims,
            eligible_anchors,
        )
        anchor_relations = _bound(
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
        focus_diagnostics.extend(
            _structural_coverage_diagnostics(focus, structural_graph)
        )
        for slot, selected_limit in (
            ("runtime_context", policy.max_runtime),
            ("test_context", policy.max_tests),
            ("structural_path", policy.max_paths),
        ):
            slot_relations = _bound(
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
        verification_relations = _bound(
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
            boundary = tuple(
                _relation(
                    focus.id,
                    "boundary_fact",
                    "evidence",
                    relation.target_id,
                    "boundary_scan",
                    (
                        AssociationReason(
                            kind="boundary_scan",
                            detail=(
                                "The selected changed anchor is inside the explicit "
                                "guardrail review scan."
                            ),
                        ),
                    ),
                    bridge_ids=(relation.id,),
                )
                for relation in anchor_relations
                if relation.state == "selected"
            )
            boundary = _bound(
                boundary,
                slot="boundary_fact",
                selected_limit=policy.max_boundary,
                candidate_limit=policy.max_candidates_per_slot,
                diagnostics=focus_diagnostics,
                focus_id=focus.id,
            )
            focus_relations.extend(boundary)
            if not boundary:
                focus_diagnostics.append(
                    _missing(
                        focus.id,
                        "boundary_fact",
                        "no_association",
                        "No changed anchor entered the bounded guardrail scan.",
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
            key=_relation_key,
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
                diagnostics=tuple(focus_diagnostics),
            )
        )

    return ProjectionCandidateSet(
        relations=tuple(relations),
        groups=tuple(groups),
        diagnostics=tuple(diagnostics),
    )


def build_review_projection(
    candidates: ProjectionCandidateSet,
) -> ReviewProjection:
    relations = candidates.by_id()
    slices = []
    for group in candidates.groups:
        selected = tuple(
            relations[relation_id]
            for relation_id in group.relation_ids
            if relation_id in relations and relations[relation_id].state == "selected"
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
                "boundary_fact",
            )
        }
        slices.append(
            ReviewSlice(
                focus_statement_id=group.focus_statement_id,
                profile=group.profile,
                claim_relation_ids=by_slot["claim"],
                changed_anchor_relation_ids=by_slot["changed_anchor"],
                runtime_relation_ids=by_slot["runtime_context"],
                test_relation_ids=by_slot["test_context"],
                verification_relation_ids=by_slot["verification"],
                structural_path_relation_ids=by_slot["structural_path"],
                boundary_relation_ids=by_slot["boundary_fact"],
                diagnostics=group.diagnostics,
            )
        )
    return ReviewProjection(
        slices=tuple(slices),
        diagnostics=candidates.diagnostics,
    )


def _claim_relations(
    focus: Requirement,
    claims: tuple[ReviewStatement, ...],
) -> tuple[ProjectionRelation, ...]:
    result = []
    for claim in claims:
        reasons = _text_reasons(focus, claim.text)
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
    return tuple(sorted(result, key=_relation_key))


def _anchor_relations(
    focus: Requirement,
    selected_claim_ids: set[str],
    claims: tuple[ReviewStatement, ...],
    anchors: tuple[EvidenceItem, ...],
) -> tuple[ProjectionRelation, ...]:
    claims_by_id = {item.id: item for item in claims}
    result = []
    for anchor in anchors:
        provided = tuple(anchor.metadata.get("provided_for_statement_ids", ()))
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
                )
            )
            continue
        direct = _text_reasons(focus, _evidence_text(anchor))
        bridges = []
        for claim_id in sorted(selected_claim_ids):
            claim = claims_by_id.get(claim_id)
            if claim is None or not _text_reasons(claim, _evidence_text(anchor)):
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
                )
            )
    return tuple(sorted(result, key=_relation_key))


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
    return tuple(sorted(result, key=_relation_key))


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
        observed_sha = str(item.metadata.get("head_sha") or "")
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
    return tuple(sorted(result, key=_relation_key))


def _provided_context_relations(
    focus: Requirement,
    evidence: Iterable[EvidenceItem],
) -> tuple[ProjectionRelation, ...]:
    result = []
    for item in evidence:
        if item.changed or focus.id not in item.metadata.get(
            "provided_for_statement_ids", ()
        ):
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
    return tuple(sorted(result, key=_relation_key))


def _text_reasons(
    source: ReviewStatement,
    target_text: str,
) -> tuple[AssociationReason, ...]:
    references = {
        value.replace("_", "").replace("-", "").replace(" ", "").casefold()
        for value in _REFERENCE_RE.findall(target_text)
    }
    focus_reference = source.id.replace("_", "").replace("-", "").casefold()
    if focus_reference in references:
        return (
            AssociationReason(
                kind="explicit_reference",
                detail=f"The candidate explicitly references {source.id}.",
                matched_terms=(source.id,),
            ),
        )
    identifiers = tuple(sorted(_identifier_keys(source.text) & _identifier_keys(target_text)))
    if identifiers:
        return (
            AssociationReason(
                kind="exact_identifier",
                detail="A distinctive identifier occurs in both texts.",
                matched_terms=identifiers,
            ),
        )
    overlap = tuple(sorted(semantic_tokens(source.text) & semantic_tokens(target_text)))
    if len(overlap) >= 2:
        return (
            AssociationReason(
                kind="distinctive_phrase",
                detail="At least two meaningful terms occur in both texts.",
                matched_terms=overlap,
            ),
        )
    return ()


def _identifier_keys(value: str) -> frozenset[str]:
    keys: set[str] = set()
    for token in _WORD_RE.findall(value):
        has_shape = "_" in token or any(char.isupper() for char in token[1:])
        if not has_shape:
            continue
        raw_parts = [part.casefold() for part in token.split("_") if part]
        parts = [
            part
            for part in raw_parts
            if len(part) >= 3 or part.isdigit()
        ]
        collapsed = "".join(parts)
        if len(collapsed) >= 5:
            keys.add(collapsed)
        for index in range(1, len(parts)):
            suffix = "".join(parts[index:])
            if len(suffix) >= 5:
                keys.add(suffix)
    return frozenset(keys)


def _requirement_profile(focus: Requirement) -> RequirementProfile:
    if focus.kind == "guardrail":
        return "guardrail"
    tokens = semantic_tokens(focus.text)
    if tokens & {"documentation", "document", "readme", "docs"}:
        return "documentation"
    if tokens & {"workflow", "configuration", "config", "action", "actions", "pipeline"}:
        return "workflow_configuration"
    if tokens & {"schema", "migration", "database"}:
        return "schema_migration"
    if tokens & {"test", "tests", "testing", "verification", "verified"}:
        return "test_verification"
    if tokens & {"api", "contract", "interface", "schema", "versioned"}:
        return "api_contract"
    if tokens & {"render", "renderer", "html", "component", "display"}:
        return "ui"
    if tokens & {"runtime", "behavior", "execute", "execution", "call"}:
        return "behavior"
    return "generic"


def _eligible_anchor(item: EvidenceItem, profile: RequirementProfile) -> bool:
    if item.profile == "generated":
        return False
    allowed = {
        "documentation": {"document"},
        "workflow_configuration": {
            "workflow",
            "configuration",
            "dependency",
            "production",
            "test",
        },
        "schema_migration": {"schema", "production", "test", "configuration"},
        "test_verification": {"test", "workflow", "production"},
        "api_contract": {"production", "test", "schema"},
        "ui": {"production", "test", "document"},
        "behavior": {"production", "test", "configuration"},
        "guardrail": {
            "production",
            "test",
            "document",
            "workflow",
            "configuration",
            "dependency",
            "schema",
        },
        "generic": {
            "production",
            "test",
            "document",
            "workflow",
            "configuration",
            "dependency",
            "schema",
            "unknown",
        },
    }
    return item.profile in allowed[profile]


def _bound(
    relations: tuple[ProjectionRelation, ...],
    *,
    slot: ProjectionSlot,
    selected_limit: int,
    candidate_limit: int,
    diagnostics: list[ProjectionDiagnostic],
    focus_id: str,
) -> tuple[ProjectionRelation, ...]:
    ordered = tuple(sorted(relations, key=_relation_key))
    kept = ordered[:candidate_limit]
    result = tuple(
        replace(
            item,
            state=(
                "selected"
                if index < selected_limit
                else "not_selected"
            ),
        )
        for index, item in enumerate(kept)
    )
    if len(ordered) > candidate_limit:
        diagnostics.append(
            _missing(
                focus_id,
                slot,
                "budget_truncated",
                (
                    f"{slot.replace('_', ' ')} candidate inspection stopped at "
                    f"{candidate_limit} items for {focus_id}."
                ),
                affected_ids=tuple(item.target_id for item in ordered[candidate_limit:]),
            )
        )
    return result


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
        return "provider_unavailable", f"{label} is unavailable without a structural provider."
    if graph.index.state == "partial":
        return "partial_coverage", f"{label} was not selected from the partial structural index."
    if graph.index.state == "stale":
        return "stale_source", f"{label} is unavailable because the structural index is stale."
    if not graph.index.usable:
        return "provider_unavailable", (
            f"{label} is unavailable because the structural provider state is "
            f"{graph.index.state}."
        )
    return "no_association", f"No eligible {label} was connected to the selected anchor."


def _structural_coverage_diagnostics(
    focus: Requirement,
    graph: StructuralGraphResult | None,
) -> tuple[ProjectionDiagnostic, ...]:
    if graph is None:
        return ()
    result = []
    if graph.index.state == "partial":
        result.append(
            ProjectionDiagnostic(
                focus_statement_id=focus.id,
                slot="structural_path",
                state="partial_coverage",
                provider=graph.index.provider,
                message=(
                    "Structural facts come from a partial index; selected paths "
                    "do not represent complete repository coverage."
                ),
            )
        )
    if any(
        item.code == "structural_graph_traversal_budget_reached"
        for item in graph.diagnostics
    ):
        result.append(
            ProjectionDiagnostic(
                focus_statement_id=focus.id,
                slot="structural_path",
                state="budget_truncated",
                provider=graph.index.provider,
                message=(
                    "Structural path collection reached the provider traversal "
                    "budget before projection selection."
                ),
            )
        )
    return tuple(result)


def _relation(
    focus_id: str,
    slot: ProjectionSlot,
    target_type: Literal["statement", "evidence"],
    target_id: str,
    association: AssociationKind,
    reasons: tuple[AssociationReason, ...],
    *,
    bridge_ids: tuple[str, ...] = (),
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
    )


def _anchor_key(item: EvidenceItem) -> tuple[object, ...]:
    precision = {"symbol": 0, "changed_hunk": 1, "changed_file": 2}
    return (
        precision.get(item.kind, 3),
        str(item.metadata.get("path") or ""),
        str(item.metadata.get("qualified_name") or ""),
        item.id,
    )


def _relation_key(item: ProjectionRelation) -> tuple[object, ...]:
    return (
        item.slot,
        _ASSOCIATION_ORDER[item.association],
        item.target_id,
        item.id,
    )


def _evidence_text(item: EvidenceItem) -> str:
    metadata = item.metadata
    return "\n".join(
        value
        for value in (
            item.summary,
            str(metadata.get("path") or ""),
            str(metadata.get("qualified_name") or ""),
            str(metadata.get("patch_excerpt") or ""),
        )
        if value
    )
