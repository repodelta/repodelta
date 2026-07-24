from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from .contracts import (
    ChangedFile,
    EvidenceCatalog,
    EvidenceClassification,
    EvidenceItem,
    ReviewSourcePacket,
    SourceRef,
    VerificationObservation,
)
from .diff_hunks import ChangedHunk, parse_changed_files
from .structural_graph import GraphSymbol, StructuralGraphResult, StructuralPath

_DOCUMENT_SUFFIXES = {".md", ".mdx", ".rst", ".txt", ".pdf", ".doc", ".docx"}


def build_evidence_catalog(
    packet: ReviewSourcePacket,
    structural_graph: StructuralGraphResult | None = None,
    *,
    supplied: tuple[EvidenceItem, ...] = (),
) -> EvidenceCatalog:
    """Normalize source, structural, and supplied facts into one ID-addressed catalog."""

    items: dict[str, EvidenceItem] = {}
    hunk_collection = parse_changed_files(packet.changed_files)
    hunks_by_path: dict[str, list[ChangedHunk]] = {}
    for hunk in hunk_collection.hunks:
        hunks_by_path.setdefault(hunk.file_path, []).append(hunk)
    mapped_hunk_ids = (
        {overlap.hunk_id for overlap in structural_graph.overlaps}
        if structural_graph is not None
        else set()
    )

    for changed_file in packet.changed_files:
        file_hunks = hunks_by_path.get(changed_file.path, ())
        if not file_hunks:
            _put(items, _changed_file_fallback(changed_file))
            continue
        for hunk in file_hunks:
            if hunk.id not in mapped_hunk_ids:
                _put(items, _changed_hunk_item(changed_file, hunk))

    if structural_graph is not None:
        changed_symbol_ids = {
            overlap.symbol.id for overlap in structural_graph.overlaps
        }
        path_ids = {
            _path_key(path): evidence_id("structural_path", _path_key(path))
            for path in structural_graph.paths
        }
        symbol_paths: dict[str, set[str]] = {}
        for path in structural_graph.paths:
            path_id = path_ids[_path_key(path)]
            symbol_paths.setdefault(path.seed_symbol_id, set()).add(path_id)
            for step in path.steps:
                symbol_paths.setdefault(step.source.id, set()).add(path_id)
                symbol_paths.setdefault(step.target.id, set()).add(path_id)

        for overlap in structural_graph.overlaps:
            _put(
                items,
                _symbol_item(
                    overlap.symbol,
                    changed=True,
                    structural_path_ids=tuple(
                        sorted(symbol_paths.get(overlap.symbol.id, ()))
                    ),
                    extra_sources=overlap.sources,
                ),
            )
        for path in structural_graph.paths:
            for step in path.steps:
                for symbol in (step.source, step.target):
                    _put(
                        items,
                        _symbol_item(
                            symbol,
                            changed=symbol.id in changed_symbol_ids,
                            structural_path_ids=tuple(
                                sorted(symbol_paths.get(symbol.id, ()))
                            ),
                        ),
                    )
            path_id = path_ids[_path_key(path)]
            _put(
                items,
                EvidenceItem(
                    id=path_id,
                    kind="structural_path",
                    summary=_path_summary(path),
                    classification=path.classification,
                    sources=path.sources,
                    structural_path_ids=(path_id,),
                    metadata={
                        "seed_symbol_id": path.seed_symbol_id,
                        "depth": path.depth,
                        "steps": tuple(
                            {
                                "source_symbol_id": step.source.id,
                                "target_symbol_id": step.target.id,
                                "relation": step.relation,
                                "direction": step.direction,
                            }
                            for step in path.steps
                        ),
                    },
                ),
            )

    for observation in packet.verification_observations:
        _put(items, verification_evidence(observation))
    for item in supplied:
        if not item.id:
            raise ValueError("supplied evidence must have a stable ID")
        _put(items, item)

    return EvidenceCatalog(
        items=tuple(sorted(items.values(), key=lambda item: item.id)),
        diagnostics=hunk_collection.diagnostics,
    )


def evidence_id(kind: str, identity: str) -> str:
    digest = hashlib.sha256(f"{kind}\0{identity}".encode("utf-8")).hexdigest()[:20]
    return f"E:{kind}:{digest}"


def provided_evidence(
    *,
    summary: str,
    kind: str,
    classification: EvidenceClassification,
    sources: tuple[SourceRef, ...] = (),
    statement_ids: tuple[str, ...] = (),
) -> EvidenceItem:
    identity = json.dumps(
        {
            "summary": summary,
            "kind": kind,
            "classification": classification,
            "sources": [
                {
                    "label": source.label,
                    "url": source.url,
                    "path": source.path,
                    "line_start": source.line_start,
                    "line_end": source.line_end,
                }
                for source in sources
            ],
            "statement_ids": statement_ids,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return EvidenceItem(
        id=evidence_id("provided", identity),
        summary=summary,
        kind=kind,
        classification=classification,
        sources=sources,
        metadata={
            "provided": True,
            "provided_for_statement_ids": statement_ids,
        },
    )


def _changed_file_fallback(changed_file: ChangedFile) -> EvidenceItem:
    path = changed_file.path
    return EvidenceItem(
        id=evidence_id("changed_file", path),
        kind="changed_file",
        summary=f"{changed_file.status.title()} file: {path}",
        classification=_path_classification(path),
        changed=True,
        sources=(
            SourceRef(
                label="changed file fallback",
                url=changed_file.source_url,
                path=path,
            ),
        ),
        metadata={
            "path": path,
            "status": changed_file.status,
            "additions": changed_file.additions,
            "deletions": changed_file.deletions,
            "changes": changed_file.changes,
            "fallback_reason": "patch_or_hunk_unavailable",
        },
    )


def _changed_hunk_item(changed_file: ChangedFile, hunk: ChangedHunk) -> EvidenceItem:
    path = hunk.file_path
    line_start = hunk.new_start
    line_end = max(hunk.new_start, hunk.new_start + max(hunk.new_count, 1) - 1)
    excerpt = hunk.new_snippet or hunk.old_snippet
    return EvidenceItem(
        id=evidence_id("changed_hunk", hunk.id),
        kind="changed_hunk",
        summary=f"Changed hunk: {path}:{line_start}-{line_end}",
        classification=_path_classification(path),
        changed=True,
        sources=(
            SourceRef(
                label="diff hunk",
                url=changed_file.source_url,
                path=path,
                line_start=line_start,
                line_end=line_end,
            ),
        ),
        metadata={
            "hunk_id": hunk.id,
            "path": path,
            "old_start": hunk.old_start,
            "old_count": hunk.old_count,
            "new_start": hunk.new_start,
            "new_count": hunk.new_count,
            "patch_excerpt": excerpt[:4000],
            "deletion_only": hunk.is_deletion_only,
        },
    )


def verification_evidence_id(observation_id: str) -> str:
    return evidence_id("verification", observation_id)


def verification_evidence(observation: VerificationObservation) -> EvidenceItem:
    return EvidenceItem(
        id=verification_evidence_id(observation.id),
        summary=(
            f"{observation.name}: {observation.status}/"
            f"{observation.conclusion or 'no conclusion'}"
        ),
        kind=observation.kind,
        classification="runtime" if observation.kind == "manual" else "ci",
        sources=(SourceRef(label=observation.name, url=observation.details_url),),
        metadata={
            "observation_id": observation.id,
            "name": observation.name,
            "status": observation.status,
            "conclusion": observation.conclusion,
            "head_sha": observation.head_sha,
        },
    )


def _symbol_item(
    symbol: GraphSymbol,
    *,
    changed: bool,
    structural_path_ids: tuple[str, ...],
    extra_sources: tuple[SourceRef, ...] = (),
) -> EvidenceItem:
    return EvidenceItem(
        id=evidence_id("symbol", symbol.id),
        kind="symbol",
        summary=f"{'Changed' if changed else 'Unchanged'} {symbol.kind}: {symbol.qualified_name}",
        classification=_path_classification(symbol.file_path),
        changed=changed,
        sources=_unique_sources((*symbol.sources, *extra_sources)),
        structural_path_ids=structural_path_ids,
        metadata={
            "symbol_id": symbol.id,
            "symbol_kind": symbol.kind,
            "qualified_name": symbol.qualified_name,
            "path": symbol.file_path,
            "language": symbol.language,
            "start_line": symbol.start_line,
            "end_line": symbol.end_line,
        },
    )


def _path_key(path: StructuralPath) -> str:
    steps = "|".join(
        f"{step.source.id}>{step.direction}:{step.relation}>{step.target.id}"
        for step in path.steps
    )
    return f"{path.seed_symbol_id}|{steps}"


def _path_summary(path: StructuralPath) -> str:
    if not path.steps:
        return path.seed_symbol_id
    parts = [path.steps[0].source.qualified_name]
    for step in path.steps:
        arrow = "→" if step.direction == "outgoing" else "←"
        parts.append(f"{arrow}[{step.relation}] {step.target.qualified_name}")
    return " ".join(parts)


def _path_classification(path: str) -> EvidenceClassification:
    normalized = path.casefold().replace("\\", "/")
    name = Path(normalized).name
    if (
        normalized.startswith(("test/", "tests/"))
        or "/test/" in normalized
        or "/tests/" in normalized
        or name.startswith("test_")
        or name.endswith(("_test.py", ".test.js", ".test.ts", ".spec.js", ".spec.ts"))
    ):
        return "test"
    if Path(normalized).suffix in _DOCUMENT_SUFFIXES:
        return "document"
    return "code"


def _put(items: dict[str, EvidenceItem], candidate: EvidenceItem) -> None:
    existing = items.get(candidate.id)
    if existing is None:
        items[candidate.id] = candidate
        return
    if existing.kind != candidate.kind:
        raise ValueError(f"evidence ID collision for {candidate.id}")
    items[candidate.id] = replace(
        existing,
        changed=existing.changed or candidate.changed,
        sources=_unique_sources((*existing.sources, *candidate.sources)),
        structural_path_ids=tuple(
            sorted({*existing.structural_path_ids, *candidate.structural_path_ids})
        ),
        metadata={**candidate.metadata, **existing.metadata},
        summary=candidate.summary if candidate.changed and not existing.changed else existing.summary,
    )


def _unique_sources(sources: Iterable[SourceRef]) -> tuple[SourceRef, ...]:
    seen: set[tuple[object, ...]] = set()
    result = []
    for source in sources:
        key = (
            source.label,
            source.url,
            source.path,
            source.line_start,
            source.line_end,
        )
        if key not in seen:
            seen.add(key)
            result.append(source)
    return tuple(result)
