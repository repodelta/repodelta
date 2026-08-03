from __future__ import annotations

from prismcode.model.contracts import EvidenceItem


def review_symbol_id(item: EvidenceItem | None) -> str | None:
    """Return the canonical review-level symbol identity for structural facts."""

    if item is None:
        return None
    if item.kind == "structural_change" and item.structural_change is not None:
        return item.structural_change.review_symbol_id
    if item.kind == "symbol":
        value = item.metadata.get("review_symbol_id")
        return str(value) if value else None
    return None


def ordered_path_review_ids(
    path: EvidenceItem,
    evidence: dict[str, EvidenceItem],
) -> tuple[str, ...]:
    return tuple(
        review_id
        for evidence_id in ordered_path_evidence_ids(path)
        if (review_id := review_symbol_id(evidence.get(evidence_id))) is not None
    )


def ordered_path_evidence_ids(path: EvidenceItem) -> tuple[str, ...]:
    """Return path symbol evidence identities in provider-observed order."""

    steps = tuple(path.metadata.get("steps", ()))
    if not steps:
        return ()
    evidence_ids = (
        steps[0].get("source_evidence_id"),
        *(step.get("target_evidence_id") for step in steps),
    )
    return tuple(
        str(evidence_id)
        for evidence_id in evidence_ids
        if evidence_id is not None
    )


def path_review_ids(
    path: EvidenceItem | None,
    evidence: dict[str, EvidenceItem],
) -> frozenset[str]:
    if path is None:
        return frozenset()
    return frozenset(ordered_path_review_ids(path, evidence))
