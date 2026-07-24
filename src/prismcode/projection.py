from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .contracts import (
    CandidateBinding,
    CandidateBindingSet,
    Diagnostic,
    EvidenceCatalog,
    EvidenceItem,
    Requirement,
    ReviewProjection,
    ReviewSlice,
)
from .structural_graph import StructuralGraphResult


@dataclass(frozen=True)
class ProjectionPolicy:
    max_claims: int = 2
    max_changed: int = 2
    max_runtime: int = 2
    max_tests: int = 2
    max_ci: int = 1
    max_paths: int = 2


def build_review_projection(
    *,
    requirements: tuple[Requirement, ...],
    evidence_catalog: EvidenceCatalog,
    candidate_bindings: CandidateBindingSet,
    structural_graph: StructuralGraphResult | None,
    policy: ProjectionPolicy = ProjectionPolicy(),
) -> ReviewProjection:
    """Select bounded review slices without copying or upgrading source facts."""

    evidence = evidence_catalog.by_id()
    bindings = {item.id: item for item in candidate_bindings.items}
    slices = tuple(
        _slice(
            requirement,
            evidence=evidence,
            bindings=bindings,
            policy=policy,
        )
        for requirement in requirements
    )
    diagnostics = _structure_diagnostics(structural_graph)
    return ReviewProjection(slices=slices, diagnostics=diagnostics)


def _slice(
    requirement: Requirement,
    *,
    evidence: dict[str, EvidenceItem],
    bindings: dict[str, CandidateBinding],
    policy: ProjectionPolicy,
) -> ReviewSlice:
    related = tuple(
        item
        for item in bindings.values()
        if item.source_id == requirement.id
    )
    claim_bindings = _ranked(
        (item for item in related if item.kind == "requirement_claim"),
        policy.max_claims,
    )
    evidence_bindings = tuple(
        item for item in related if item.kind == "statement_evidence"
    )
    best_by_evidence = _best_evidence_bindings(evidence_bindings)
    changed = _select_changed(best_by_evidence, evidence, policy.max_changed)
    paths = _select_paths(
        changed,
        best_by_evidence,
        evidence,
        policy.max_paths,
    )
    path_ids = {item.id for item in paths}
    context = tuple(
        item
        for item in evidence.values()
        if not item.changed
        and item.id in best_by_evidence
        and path_ids.intersection(item.structural_path_ids)
    )
    runtime = tuple(
        sorted(
            (item for item in context if item.classification == "code"),
            key=_evidence_key,
        )[: policy.max_runtime]
    )
    tests = tuple(
        sorted(
            (item for item in context if item.classification == "test"),
            key=_evidence_key,
        )[: policy.max_tests]
    )
    ci = tuple(
        sorted(
            (
                item
                for item in evidence.values()
                if item.id in best_by_evidence and item.classification == "ci"
            ),
            key=_evidence_key,
        )[: policy.max_ci]
    )
    diagnostics = []
    if not claim_bindings:
        diagnostics.append(
            Diagnostic(
                code="projection_claim_candidate_missing",
                message=f"{requirement.id} has no PR claim candidate.",
                severity="info",
            )
        )
    if not changed:
        diagnostics.append(
            Diagnostic(
                code="projection_changed_anchor_missing",
                message=f"{requirement.id} has no changed evidence candidate.",
                severity="info",
            )
        )
    return ReviewSlice(
        focus_statement_id=requirement.id,
        claim_binding_ids=tuple(item.id for item in claim_bindings),
        changed_evidence_ids=tuple(item.id for item in changed),
        runtime_evidence_ids=tuple(item.id for item in runtime),
        test_evidence_ids=tuple(item.id for item in tests),
        ci_evidence_ids=tuple(item.id for item in ci),
        structural_path_evidence_ids=tuple(item.id for item in paths),
        diagnostics=tuple(diagnostics),
    )


def _best_evidence_bindings(
    bindings: tuple[CandidateBinding, ...],
) -> dict[str, CandidateBinding]:
    selected: dict[str, CandidateBinding] = {}
    for binding in bindings:
        existing = selected.get(binding.target_id)
        if existing is None or (-binding.score, binding.id) < (
            -existing.score,
            existing.id,
        ):
            selected[binding.target_id] = binding
    return selected


def _select_changed(
    bindings: dict[str, CandidateBinding],
    evidence: dict[str, EvidenceItem],
    limit: int,
) -> tuple[EvidenceItem, ...]:
    precision = {"symbol": 0, "changed_hunk": 1, "changed_file": 2}
    candidates = (
        item
        for item in evidence.values()
        if item.changed
        and item.id in bindings
        and item.kind in precision
    )
    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                precision[item.kind],
                -bindings[item.id].score,
                item.id,
            ),
        )[:limit]
    )


def _select_paths(
    changed: tuple[EvidenceItem, ...],
    bindings: dict[str, CandidateBinding],
    evidence: dict[str, EvidenceItem],
    limit: int,
) -> tuple[EvidenceItem, ...]:
    referenced = {
        path_id
        for anchor in changed
        for path_id in (
            *anchor.structural_path_ids,
            *bindings[anchor.id].structural_path_ids,
        )
    }
    candidates = [
        evidence[path_id]
        for path_id in referenced
        if path_id in evidence
        and path_id in bindings
        and evidence[path_id].kind == "structural_path"
    ]
    ordered = sorted(candidates, key=_path_key)
    selected: list[EvidenceItem] = []
    for classifications in ({"runtime"}, {"test", "mixed"}):
        match = next(
            (
                item
                for item in ordered
                if item.classification in classifications
                and item not in selected
            ),
            None,
        )
        if match is not None and len(selected) < limit:
            selected.append(match)
    for item in ordered:
        if len(selected) >= limit:
            break
        if item not in selected:
            selected.append(item)
    return tuple(sorted(selected, key=_path_key))


def _ranked(
    bindings: Iterable[CandidateBinding],
    limit: int,
) -> tuple[CandidateBinding, ...]:
    return tuple(
        sorted(
            bindings,
            key=lambda item: (-item.score, item.target_id, item.id),
        )[:limit]
    )


def _evidence_key(item: EvidenceItem) -> tuple[object, ...]:
    return (
        str(item.metadata.get("path") or ""),
        str(item.metadata.get("qualified_name") or ""),
        item.id,
    )


def _path_key(item: EvidenceItem) -> tuple[object, ...]:
    return (
        int(item.metadata.get("depth") or 0),
        {"runtime": 0, "mixed": 1, "test": 2}.get(item.classification, 3),
        item.id,
    )


def _structure_diagnostics(
    structural_graph: StructuralGraphResult | None,
) -> tuple[Diagnostic, ...]:
    if structural_graph is None:
        return (
            Diagnostic(
                code="projection_structure_unavailable",
                message="unavailable · showing changed-hunk/file anchors",
                severity="info",
            ),
        )
    if not structural_graph.index.usable:
        return (
            Diagnostic(
                code="projection_structure_unavailable",
                message=(
                    "unavailable · showing changed-hunk/file anchors "
                    f"({structural_graph.index.state})"
                ),
                severity="info",
            ),
        )
    return ()
