from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from prismcode.model.contracts import (
    AssociationSignature,
    ChangedFile,
    ChangeOperation,
    EvidenceCatalog,
    EvidenceClassification,
    EvidenceItem,
    ReviewSourcePacket,
    SourceRef,
    SuppliedEvidence,
    VerificationObservation,
    VerificationIdentity,
)
from prismcode.changes.hunks import (
    ChangedHunk,
    ChangedLine,
    ChangedSpan,
    DiffHunkCollection,
)
from prismcode.facts.lexical import association_signature, merge_signatures
from prismcode.providers.structural import (
    GraphSymbol,
    HunkSymbolOverlap,
    StructuralGraphResult,
    StructuralPath,
)

_DOCUMENT_SUFFIXES = {".md", ".mdx", ".rst", ".txt", ".pdf", ".doc", ".docx"}
_WORKFLOW_PREFIXES = (".github/workflows/", ".circleci/")
_CONFIG_NAMES = {
    "pyproject.toml",
    "setup.cfg",
    "tox.ini",
    "package.json",
    "tsconfig.json",
    "dockerfile",
}
_DEPENDENCY_NAMES = {
    "requirements.txt",
    "poetry.lock",
    "uv.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "cargo.lock",
    "go.sum",
}


def build_evidence_catalog(
    packet: ReviewSourcePacket,
    changes: DiffHunkCollection,
    structural_graph: StructuralGraphResult | None = None,
    *,
    supplied: tuple[SuppliedEvidence, ...] = (),
) -> EvidenceCatalog:
    """Normalize source, structural, and supplied facts into one ID-addressed catalog."""

    items: dict[str, EvidenceItem] = {}
    hunks_by_path: dict[str, list[ChangedHunk]] = {}
    for hunk in changes.hunks:
        hunks_by_path.setdefault(hunk.file_path, []).append(hunk)
    hunks_by_id = {hunk.id: hunk for hunk in changes.hunks}
    overlaps_by_hunk: dict[str, list[HunkSymbolOverlap]] = {}
    if structural_graph is not None:
        for overlap in structural_graph.overlaps:
            overlaps_by_hunk.setdefault(overlap.hunk_id, []).append(overlap)

    for changed_file in packet.changed_files:
        file_hunks = hunks_by_path.get(changed_file.path, ())
        if not file_hunks:
            _put(items, _changed_file_fallback(changed_file))
            continue
        for hunk in file_hunks:
            overlaps = overlaps_by_hunk.get(hunk.id, ())
            mapped_lines = {
                line for overlap in overlaps for line in overlap.changed_lines
            }
            for span in hunk.spans:
                uncovered = tuple(
                    line for line in span.added if line.number not in mapped_lines
                )
                if uncovered or not span.added:
                    _put(
                        items,
                        _changed_span_item(
                            changed_file,
                            span,
                            added=uncovered,
                            include_removed=not bool(mapped_lines & set(span.added_lines)),
                        ),
                    )

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
            hunk = hunks_by_id.get(overlap.hunk_id)
            head_signature, base_signature = _overlap_signatures(
                hunk,
                overlap.changed_lines,
            )
            _put(
                items,
                _symbol_item(
                    overlap.symbol,
                    changed=True,
                    operation=(
                        "added"
                        if hunk is not None
                        and hunk.added_lines
                        and not hunk.removed_lines
                        else "modified"
                    ),
                    structural_path_ids=tuple(
                        sorted(symbol_paths.get(overlap.symbol.id, ()))
                    ),
                    extra_sources=overlap.sources,
                    head_signature=head_signature,
                    base_signature=base_signature,
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
                            operation=(
                                "modified"
                                if symbol.id in changed_symbol_ids
                                else "unchanged"
                            ),
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
                    profile="structural_path",
                    authority="structural_provider",
                    revision_side="unchanged",
                    operation="observed",
                    role="structural_path",
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
        _put(
            items,
            provided_evidence(
                summary=item.summary,
                kind=item.kind,
                classification=item.classification,
                sources=item.sources,
                statement_ids=item.statement_ids,
            ),
        )

    catalog = EvidenceCatalog(
        items=tuple(sorted(items.values(), key=lambda item: item.id)),
        diagnostics=changes.diagnostics,
    )
    catalog.validate_consistency()
    return catalog


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
        profile=(
            "verification"
            if classification in {"ci", "runtime"}
            else "test"
            if classification == "test"
            else "document"
            if classification == "document"
            else "production"
        ),
        authority="supplied",
        revision_side="review",
        operation="observed",
        role="provided_context",
        associated_statement_ids=statement_ids,
        sources=sources,
        metadata={
            "provided": True,
        },
    )


def _changed_file_fallback(changed_file: ChangedFile) -> EvidenceItem:
    path = changed_file.path
    summary = f"{changed_file.status.title()} file: {path}"
    return EvidenceItem(
        id=evidence_id("changed_file", path),
        kind="changed_file",
        summary=summary,
        classification=_path_classification(path),
        profile=_fact_profile(path),
        authority="github_diff",
        revision_side=(
            "base" if changed_file.status == "removed" else "head"
        ),
        operation=(
            "removed"
            if changed_file.status == "removed"
            else "added"
            if changed_file.status == "added"
            else "renamed"
            if changed_file.status == "renamed"
            else "modified"
        ),
        role="changed_anchor",
        changed=True,
        head_signature=association_signature(summary, path),
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


def _changed_span_item(
    changed_file: ChangedFile,
    span: ChangedSpan,
    *,
    added: tuple[ChangedLine, ...],
    include_removed: bool,
) -> EvidenceItem:
    path = span.file_path
    removed = span.removed if include_removed else ()
    head_text = "\n".join(item.text for item in added)
    base_text = "\n".join(item.text for item in removed)
    display_lines = added or removed
    line_start = min((item.number for item in display_lines), default=0)
    line_end = max((item.number for item in display_lines), default=line_start)
    operation = (
        "removed"
        if removed and not added
        else "added"
        if added and not removed
        else "modified"
    )
    identity = f"{span.id}:{','.join(str(item.number) for item in added)}"
    summary = f"Changed span: {path}:{line_start}-{line_end}"
    return EvidenceItem(
        id=evidence_id("changed_span", identity),
        kind="changed_span",
        summary=summary,
        classification=_path_classification(path),
        profile=_fact_profile(path),
        authority="github_diff",
        revision_side="base" if operation == "removed" else "head",
        operation=operation,
        role="changed_anchor",
        changed=True,
        head_signature=association_signature(summary, path, head_text),
        base_signature=association_signature(summary, path, base_text),
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
            "hunk_id": span.hunk_id,
            "span_id": span.id,
            "path": path,
            "added_lines": tuple(item.number for item in added),
            "removed_lines": tuple(item.number for item in removed),
            "head_preview": head_text[:4000],
            "base_preview": base_text[:4000],
            "deletion_only": bool(removed and not added),
        },
    )


def verification_evidence_id(observation_id: str) -> str:
    return evidence_id("verification", observation_id)


def verification_evidence(observation: VerificationObservation) -> EvidenceItem:
    identity = VerificationIdentity(
        provider=observation.provider.strip().casefold() or "unknown",
        kind=observation.kind,
        name=" ".join(observation.name.split()).casefold(),
    )
    return EvidenceItem(
        id=verification_evidence_id(observation.id),
        summary=(
            f"{observation.name}: {observation.status}/"
            f"{observation.conclusion or 'no conclusion'}"
        ),
        kind=observation.kind,
        classification="runtime" if observation.kind == "manual" else "ci",
        profile="verification",
        authority="verification_provider",
        revision_side="review",
        operation="observed",
        role="verification",
        observed_head_sha=observation.head_sha,
        verification_identity=identity,
        verification_status=observation.status.strip().casefold() or "unknown",
        verification_conclusion=observation.conclusion.strip().casefold(),
        sources=(SourceRef(label=observation.name, url=observation.details_url),),
    )


def _symbol_item(
    symbol: GraphSymbol,
    *,
    changed: bool,
    operation: ChangeOperation,
    structural_path_ids: tuple[str, ...],
    extra_sources: tuple[SourceRef, ...] = (),
    head_signature: AssociationSignature = AssociationSignature(),
    base_signature: AssociationSignature = AssociationSignature(),
) -> EvidenceItem:
    canonical_signature = association_signature(
        symbol.qualified_name,
        symbol.file_path,
    )
    return EvidenceItem(
        id=evidence_id("symbol", symbol.id),
        kind="symbol",
        summary=f"{'Changed' if changed else 'Unchanged'} {symbol.kind}: {symbol.qualified_name}",
        classification=_path_classification(symbol.file_path),
        profile=_fact_profile(symbol.file_path),
        authority="structural_provider",
        revision_side="head" if changed else "unchanged",
        operation=operation,
        role=(
            "changed_anchor"
            if changed
            else "test_context"
            if _fact_profile(symbol.file_path) == "test"
            else "runtime_context"
        ),
        changed=changed,
        head_signature=merge_signatures(canonical_signature, head_signature),
        base_signature=base_signature,
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


def _overlap_signatures(
    hunk: ChangedHunk | None,
    changed_lines: tuple[int, ...],
) -> tuple[AssociationSignature, AssociationSignature]:
    if hunk is None:
        return AssociationSignature(), AssociationSignature()
    covered = set(changed_lines)
    head_values = []
    base_values = []
    for span in hunk.spans:
        selected = tuple(item.text for item in span.added if item.number in covered)
        if not selected:
            continue
        head_values.extend(selected)
        base_values.extend(item.text for item in span.removed)
    return (
        association_signature(*head_values),
        association_signature(*base_values),
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


def _fact_profile(path: str) -> str:
    normalized = path.casefold().replace("\\", "/")
    name = Path(normalized).name
    suffix = Path(normalized).suffix
    if _path_classification(path) == "test":
        return "test"
    if suffix in _DOCUMENT_SUFFIXES:
        return "document"
    if normalized.startswith(_WORKFLOW_PREFIXES):
        return "workflow"
    if name in _DEPENDENCY_NAMES:
        return "dependency"
    if name in _CONFIG_NAMES or suffix in {".ini", ".toml", ".yaml", ".yml", ".json"}:
        return "configuration"
    if "migration" in normalized or "schema" in normalized:
        return "schema"
    if any(part in normalized.split("/") for part in ("vendor", "generated", "dist")):
        return "generated"
    return "production"


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
        head_signature=merge_signatures(
            existing.head_signature,
            candidate.head_signature,
        ),
        base_signature=merge_signatures(
            existing.base_signature,
            candidate.base_signature,
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
