from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Iterable

from .contracts import (
    BindingReason,
    CandidateBinding,
    CandidateBindingKind,
    CandidateBindingSet,
    CandidateCoverage,
    Diagnostic,
    EvidenceCatalog,
    EvidenceItem,
    Requirement,
    ReviewStatement,
)
from .matching import semantic_tokens


@dataclass(frozen=True)
class CandidateBindingPolicy:
    min_lexical_score: int = 7
    max_per_statement: int = 40
    max_total: int = 500


def build_candidate_bindings(
    *,
    requirements: tuple[Requirement, ...],
    objectives: tuple[ReviewStatement, ...],
    claims: tuple[ReviewStatement, ...],
    evidence_catalog: EvidenceCatalog,
    scope: tuple[ReviewStatement, ...] = (),
    policy: CandidateBindingPolicy = CandidateBindingPolicy(),
) -> CandidateBindingSet:
    """Generate explainable retrieval candidates without review conclusions."""

    bindings: dict[tuple[str, str, str], CandidateBinding] = {}
    statements: tuple[ReviewStatement, ...] = (
        *requirements,
        *objectives,
        *scope,
        *claims,
    )
    evidence = evidence_catalog.items

    for statement in statements:
        for item in evidence:
            reasons = list(
                _lexical_reasons(statement.text, _evidence_text(item), item)
            )
            if statement.id in item.metadata.get(
                "provided_for_statement_ids", ()
            ):
                reasons.append(
                    BindingReason(
                        feature="provided_association",
                        detail=(
                            "The supplied fixture/provider evidence explicitly "
                            "references this statement."
                        ),
                        weight=100,
                    )
                )
            if sum(reason.weight for reason in reasons) >= policy.min_lexical_score:
                _merge(
                    bindings,
                    _binding(
                        "statement_evidence",
                        statement.id,
                        item.id,
                        tuple(reasons),
                        item.structural_path_ids,
                    ),
                )

    for requirement in requirements:
        for claim in claims:
            reasons = _lexical_reasons(requirement.text, claim.text)
            if sum(reason.weight for reason in reasons) >= policy.min_lexical_score:
                _merge(
                    bindings,
                    _binding(
                        "requirement_claim",
                        requirement.id,
                        claim.id,
                        reasons,
                    ),
                )

    _add_structural_neighbors(bindings, evidence_catalog)
    _add_claim_bridges(bindings, requirements, claims)
    selected, diagnostics = _apply_budget(bindings.values(), policy)
    coverage = _coverage(selected, requirements, claims, evidence)
    return CandidateBindingSet(
        items=selected,
        coverage=coverage,
        diagnostics=diagnostics,
    )


def _lexical_reasons(
    source_text: str,
    target_text: str,
    evidence: EvidenceItem | None = None,
) -> tuple[BindingReason, ...]:
    source_tokens = semantic_tokens(source_text)
    target_tokens = semantic_tokens(target_text)
    overlap = tuple(sorted(source_tokens & target_tokens))
    if not overlap:
        return ()
    reasons = [
        BindingReason(
            feature="term_overlap",
            detail="Meaningful source terms occur in the candidate.",
            weight=min(35, 7 * len(overlap)),
            matched_terms=overlap,
        )
    ]
    compound = tuple(term for term in overlap if "_" in term)
    if compound:
        reasons.append(
            BindingReason(
                feature="identifier_overlap",
                detail="A compound identifier occurs on both sides.",
                weight=min(20, 10 * len(compound)),
                matched_terms=compound,
            )
        )
    if evidence is not None:
        path = str(evidence.metadata.get("path") or "")
        path_overlap = tuple(sorted(source_tokens & semantic_tokens(path)))
        if path_overlap:
            reasons.append(
                BindingReason(
                    feature="path_overlap",
                    detail="Statement terms occur in the evidence path.",
                    weight=min(12, 4 * len(path_overlap)),
                    matched_terms=path_overlap,
                )
            )
        if evidence.changed:
            reasons.append(
                BindingReason(
                    feature="changed_context",
                    detail="The candidate is directly changed by the pull request.",
                    weight=3,
                )
            )
    return tuple(reasons)


def _add_structural_neighbors(
    bindings: dict[tuple[str, str, str], CandidateBinding],
    catalog: EvidenceCatalog,
) -> None:
    evidence_by_id = catalog.by_id()
    path_items = {
        item.id: item for item in catalog.items if item.kind == "structural_path"
    }
    symbols_by_path: dict[str, list[EvidenceItem]] = {}
    for item in catalog.items:
        if item.kind != "symbol":
            continue
        for path_id in item.structural_path_ids:
            symbols_by_path.setdefault(path_id, []).append(item)

    anchors = tuple(
        binding
        for binding in bindings.values()
        if binding.kind == "statement_evidence"
        and evidence_by_id.get(binding.target_id) is not None
        and evidence_by_id[binding.target_id].kind == "symbol"
    )
    for anchor in anchors:
        anchor_item = evidence_by_id[anchor.target_id]
        anchor_symbol_id = str(anchor_item.metadata.get("symbol_id") or "")
        for path_id in anchor_item.structural_path_ids:
            path = path_items.get(path_id)
            if path is None:
                continue
            positions = _path_positions(path)
            if anchor_symbol_id not in positions:
                continue
            anchor_position = positions[anchor_symbol_id]
            path_reason = BindingReason(
                feature="structural_path",
                detail=(
                    f"Reached from lexical anchor {anchor.target_id} through "
                    f"bounded path {path_id}."
                ),
                weight=max(4, 12 - (2 * int(path.metadata.get("depth") or 1))),
            )
            lexical_reason = BindingReason(
                feature="lexical_anchor",
                detail=f"Structural expansion preserves anchor {anchor.target_id}.",
                weight=max(4, min(30, anchor.score // 2)),
            )
            _merge(
                bindings,
                _binding(
                    "statement_evidence",
                    anchor.source_id,
                    path.id,
                    (lexical_reason, path_reason),
                    (path_id,),
                ),
            )
            for neighbor in symbols_by_path.get(path_id, ()):
                neighbor_symbol_id = str(neighbor.metadata.get("symbol_id") or "")
                if neighbor.id == anchor.target_id or neighbor_symbol_id not in positions:
                    continue
                distance = abs(positions[neighbor_symbol_id] - anchor_position)
                if distance < 1:
                    continue
                neighbor_reason = replace(
                    path_reason,
                    detail=(
                        f"{neighbor.id} is {distance} hop(s) from lexical anchor "
                        f"{anchor.target_id} on bounded path {path_id}."
                    ),
                    weight=max(3, 12 - (3 * distance)),
                )
                _merge(
                    bindings,
                    _binding(
                        "statement_evidence",
                        anchor.source_id,
                        neighbor.id,
                        (lexical_reason, neighbor_reason),
                        (path_id,),
                    ),
                )


def _add_claim_bridges(
    bindings: dict[tuple[str, str, str], CandidateBinding],
    requirements: tuple[Requirement, ...],
    claims: tuple[ReviewStatement, ...],
) -> None:
    requirement_ids = {item.id for item in requirements}
    claim_ids = {item.id for item in claims}
    requirement_claims = tuple(
        item
        for item in bindings.values()
        if item.kind == "requirement_claim"
        and item.source_id in requirement_ids
        and item.target_id in claim_ids
    )
    claim_evidence = tuple(
        item
        for item in bindings.values()
        if item.kind == "statement_evidence" and item.source_id in claim_ids
    )
    by_claim: dict[str, list[CandidateBinding]] = {}
    for item in claim_evidence:
        by_claim.setdefault(item.source_id, []).append(item)
    for requirement_claim in requirement_claims:
        for claim_binding in by_claim.get(requirement_claim.target_id, ()):
            reasons = (
                BindingReason(
                    feature="requirement_claim_alignment",
                    detail=(
                        f"{requirement_claim.source_id} is lexically aligned with "
                        f"claim {requirement_claim.target_id}."
                    ),
                    weight=max(4, requirement_claim.score // 2),
                ),
                BindingReason(
                    feature="claim_evidence_bridge",
                    detail=(
                        f"Claim {requirement_claim.target_id} has candidate evidence "
                        f"{claim_binding.target_id}."
                    ),
                    weight=max(4, claim_binding.score // 2),
                ),
            )
            _merge(
                bindings,
                _binding(
                    "statement_evidence",
                    requirement_claim.source_id,
                    claim_binding.target_id,
                    reasons,
                    claim_binding.structural_path_ids,
                ),
            )


def _apply_budget(
    bindings: Iterable[CandidateBinding],
    policy: CandidateBindingPolicy,
) -> tuple[tuple[CandidateBinding, ...], tuple[Diagnostic, ...]]:
    ordered = sorted(
        bindings,
        key=lambda item: (
            item.source_id,
            item.kind,
            -item.score,
            item.target_id,
        ),
    )
    selected: list[CandidateBinding] = []
    per_statement_kind: dict[tuple[str, str], int] = {}
    truncated = False
    for item in ordered:
        if len(selected) >= policy.max_total:
            truncated = True
            break
        budget_key = (item.source_id, item.kind)
        count = per_statement_kind.get(budget_key, 0)
        if count >= policy.max_per_statement:
            truncated = True
            continue
        selected.append(item)
        per_statement_kind[budget_key] = count + 1
    diagnostics = (
        (
            Diagnostic(
                code="candidate_binding_budget_reached",
                message=(
                    "Candidate binding stopped at its deterministic budget "
                    f"({policy.max_per_statement} per statement/binding kind, "
                    f"{policy.max_total} total)."
                ),
                severity="info",
            ),
        )
        if truncated
        else ()
    )
    return tuple(selected), diagnostics


def _coverage(
    bindings: tuple[CandidateBinding, ...],
    requirements: tuple[Requirement, ...],
    claims: tuple[ReviewStatement, ...],
    evidence: tuple[EvidenceItem, ...],
) -> CandidateCoverage:
    statement_evidence_sources = {
        item.source_id for item in bindings if item.kind == "statement_evidence"
    }
    bound_evidence = {
        item.target_id for item in bindings if item.kind == "statement_evidence"
    }
    claims_with_requirement = {
        item.target_id for item in bindings if item.kind == "requirement_claim"
    }
    return CandidateCoverage(
        requirement_ids_without_evidence_candidates=tuple(
            item.id for item in requirements if item.id not in statement_evidence_sources
        ),
        claim_ids_without_requirement_candidates=tuple(
            item.id for item in claims if item.id not in claims_with_requirement
        ),
        evidence_ids_without_statement_candidates=tuple(
            item.id for item in evidence if item.id not in bound_evidence
        ),
    )


def _binding(
    kind: CandidateBindingKind,
    source_id: str,
    target_id: str,
    reasons: tuple[BindingReason, ...],
    structural_path_ids: tuple[str, ...] = (),
) -> CandidateBinding:
    score = min(100, sum(reason.weight for reason in reasons))
    identity = f"{kind}\0{source_id}\0{target_id}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return CandidateBinding(
        id=f"B:{kind}:{digest}",
        kind=kind,
        source_id=source_id,
        target_id=target_id,
        score=score,
        reasons=reasons,
        structural_path_ids=tuple(sorted(set(structural_path_ids))),
    )


def _merge(
    bindings: dict[tuple[str, str, str], CandidateBinding],
    candidate: CandidateBinding,
) -> None:
    key = (candidate.kind, candidate.source_id, candidate.target_id)
    existing = bindings.get(key)
    if existing is None:
        bindings[key] = candidate
        return
    reasons = {
        (
            reason.feature,
            reason.detail,
            reason.weight,
            reason.matched_terms,
        ): reason
        for reason in (*existing.reasons, *candidate.reasons)
    }
    bindings[key] = replace(
        existing,
        score=min(100, sum(reason.weight for reason in reasons.values())),
        reasons=tuple(
            sorted(
                reasons.values(),
                key=lambda reason: (
                    reason.feature,
                    reason.detail,
                    reason.matched_terms,
                ),
            )
        ),
        structural_path_ids=tuple(
            sorted(
                {
                    *existing.structural_path_ids,
                    *candidate.structural_path_ids,
                }
            )
        ),
    )


def _evidence_text(item: EvidenceItem) -> str:
    metadata = item.metadata
    values = (
        item.summary,
        str(metadata.get("path") or ""),
        str(metadata.get("qualified_name") or ""),
        str(metadata.get("name") or ""),
        str(metadata.get("patch_excerpt") or ""),
    )
    return "\n".join(value for value in values if value)


def _path_positions(path: EvidenceItem) -> dict[str, int]:
    seed = str(path.metadata.get("seed_symbol_id") or "")
    positions = {seed: 0} if seed else {}
    for index, step in enumerate(path.metadata.get("steps") or (), start=1):
        target = str(step.get("target_symbol_id") or "")
        if target and target not in positions:
            positions[target] = index
    return positions
