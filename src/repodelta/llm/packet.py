from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from repodelta.llm.contracts import ShadowEvidenceCandidate
from repodelta.model.contracts import (
    ChangeRelation,
    EvidenceCatalog,
    EvidenceItem,
    SourceRef,
)


@dataclass(frozen=True)
class ShadowCodePacketPolicy:
    max_candidate_code_chars: int = 2_000
    max_request_code_chars: int = 24_000
    max_structural_contexts: int = 6

    def __post_init__(self) -> None:
        if self.max_candidate_code_chars <= 0:
            raise ValueError("max_candidate_code_chars must be positive")
        if self.max_request_code_chars <= 0:
            raise ValueError("max_request_code_chars must be positive")
        if self.max_structural_contexts <= 0:
            raise ValueError("max_structural_contexts must be positive")


def build_shadow_code_packet(
    items: tuple[EvidenceItem, ...],
    catalog: EvidenceCatalog,
    *,
    policy: ShadowCodePacketPolicy = ShadowCodePacketPolicy(),
    provenance: Mapping[str, tuple[str, str]] | None = None,
) -> tuple[tuple[ShadowEvidenceCandidate, ...], tuple[str, ...]]:
    """Project catalog-owned facts into one bounded LLM input packet."""

    relations = {item.id: item for item in catalog.change_relations}
    provenance = provenance or {}
    evidence = catalog.by_id()
    remaining = policy.max_request_code_chars
    candidates = []
    code_truncated = 0
    structural_truncated = 0
    for item in items:
        added, removed = _directional_code(item, relations)
        code_budget = min(policy.max_candidate_code_chars, remaining)
        bounded_added, bounded_removed, truncated = _bound_code(
            added,
            removed,
            code_budget,
        )
        remaining -= len(bounded_added) + len(bounded_removed)
        code_truncated += truncated
        structural = tuple(
            evidence[path_id].summary
            for path_id in item.structural_path_ids
            if path_id in evidence and evidence[path_id].kind == "structural_path"
        )
        if len(structural) > policy.max_structural_contexts:
            structural_truncated += 1
        source = next((value for value in item.sources if value.path), None)
        line_start, line_end = _complete_line_range(source)
        candidates.append(
            ShadowEvidenceCandidate(
                evidence_id=item.id,
                summary=item.summary,
                kind=item.kind,
                revision_side=item.revision_side,
                operation=item.operation,
                classification=item.classification,
                profile=item.profile,
                authority=item.authority,
                path=str(item.metadata.get("path") or (source.path if source else "")),
                line_start=line_start,
                line_end=line_end,
                symbol_kind=str(item.metadata.get("symbol_kind") or ""),
                qualified_name=str(item.metadata.get("qualified_name") or ""),
                added_code=bounded_added,
                removed_code=bounded_removed,
                structural_context=structural[: policy.max_structural_contexts],
                admission_tier=provenance.get(item.id, ("unspecified", "none"))[0],
                association=provenance.get(item.id, ("unspecified", "none"))[1],
            )
        )
    limits = []
    if code_truncated:
        limits.append(
            f"Code excerpts were truncated for {code_truncated} evidence candidates "
            f"within per-candidate ({policy.max_candidate_code_chars}) and request "
            f"({policy.max_request_code_chars}) character limits."
        )
    if structural_truncated:
        limits.append(
            f"Structural context was truncated for {structural_truncated} evidence "
            f"candidates at {policy.max_structural_contexts} paths each."
        )
    return tuple(candidates), tuple(limits)


def _directional_code(
    item: EvidenceItem,
    relations: dict[str, ChangeRelation],
) -> tuple[str, str]:
    selected = tuple(
        relations[relation_id]
        for relation_id in item.change_relation_ids
        if relation_id in relations
    )
    added = "\n".join(
        line.text for relation in selected for line in relation.added
    )
    removed = "\n".join(
        line.text for relation in selected for line in relation.removed
    )
    return added, removed


def _bound_code(added: str, removed: str, budget: int) -> tuple[str, str, int]:
    if not added and not removed:
        return "", "", 0
    if budget <= 0:
        return "", "", 1
    if added and removed:
        removed_budget = min(len(removed), budget // 2)
        added_budget = min(len(added), budget - removed_budget)
        spare = budget - removed_budget - added_budget
        if spare and len(removed) > removed_budget:
            removed_budget += min(spare, len(removed) - removed_budget)
        elif spare and len(added) > added_budget:
            added_budget += min(spare, len(added) - added_budget)
    else:
        added_budget = budget if added else 0
        removed_budget = budget if removed else 0
    bounded_added = added[:added_budget]
    bounded_removed = removed[:removed_budget]
    truncated = int(bounded_added != added or bounded_removed != removed)
    return bounded_added, bounded_removed, truncated


def _complete_line_range(
    source: SourceRef | None,
) -> tuple[int | None, int | None]:
    start = source.line_start if source is not None else None
    end = source.line_end if source is not None else None
    return (start, end) if start is not None and end is not None else (None, None)
