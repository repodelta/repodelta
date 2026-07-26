from __future__ import annotations

from dataclasses import replace
from urllib.parse import ParseResult, quote, urlparse

from prismcode.model.contracts import Diagnostic, ReviewSourcePacket, SourceRef
from prismcode.changes.hunks import DiffHunkCollection
from prismcode.providers.structural import (
    GraphSymbol,
    StructuralGraphCollection,
    StructuralGraphProvider,
    StructuralGraphResult,
    StructuralRevision,
)


def map_packet_changed_symbols(
    packet: ReviewSourcePacket,
    changes: DiffHunkCollection,
    head_provider: StructuralGraphProvider,
    *,
    base_provider: StructuralGraphProvider | None = None,
) -> StructuralGraphCollection:
    """Collect revision-aware structural facts without computing a delta."""

    head = _map_revision(packet, changes, head_provider, "head")
    revisions = [head]
    diagnostics = list(changes.diagnostics)
    if base_provider is not None:
        revisions.append(_map_revision(packet, changes, base_provider, "base"))
    elif any(hunk.removed_lines for hunk in changes.hunks):
        diagnostics.append(
            Diagnostic(
                code="structural_graph_base_input_missing",
                message=(
                    "Changed base lines exist, but no base-revision checkout "
                    "was provided; base structural facts were not collected."
                ),
            )
        )
    result = StructuralGraphCollection(
        revisions=tuple(revisions),
        diagnostics=tuple(diagnostics),
    )
    result.validate_consistency()
    return result


def _map_revision(
    packet: ReviewSourcePacket,
    changes: DiffHunkCollection,
    provider: StructuralGraphProvider,
    revision_side: StructuralRevision,
) -> StructuralGraphResult:
    result = provider.symbols_overlapping(changes.hunks)
    if result.revision_side != revision_side:
        raise ValueError("structural provider returned the wrong revision side")
    result = provider.expand_paths(result)
    return _attach_github_line_sources(packet, result)


def _attach_github_line_sources(
    packet: ReviewSourcePacket, result: StructuralGraphResult
) -> StructuralGraphResult:
    revision = (
        packet.head_sha
        if result.revision_side == "head"
        else packet.base_sha
    )
    if not revision:
        return result
    parsed = urlparse(packet.source_url or "")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return result

    def enrich_symbol(symbol: GraphSymbol) -> GraphSymbol:
        return replace(
            symbol,
            sources=tuple(
                _line_source(packet, parsed, source, revision)
                for source in symbol.sources
            ),
        )

    overlaps = tuple(
        replace(
            overlap,
            symbol=enrich_symbol(overlap.symbol),
            sources=tuple(
                _line_source(packet, parsed, source, revision)
                for source in overlap.sources
            ),
        )
        for overlap in result.overlaps
    )
    paths = tuple(
        replace(
            path,
            steps=tuple(
                replace(
                    step,
                    source=enrich_symbol(step.source),
                    target=enrich_symbol(step.target),
                )
                for step in path.steps
            ),
            sources=tuple(
                _line_source(packet, parsed, source, revision)
                for source in path.sources
            ),
        )
        for path in result.paths
    )
    return replace(result, overlaps=overlaps, paths=paths)


def _line_source(
    packet: ReviewSourcePacket,
    parsed: ParseResult,
    source: SourceRef,
    revision: str,
) -> SourceRef:
    if not source.path or source.url:
        return source
    fragment = ""
    if source.line_start:
        fragment = f"#L{source.line_start}"
        if source.line_end and source.line_end != source.line_start:
            fragment += f"-L{source.line_end}"
    root = f"{parsed.scheme}://{parsed.netloc}"
    url = (
        f"{root}/{packet.repository}/blob/{revision}/"
        f"{quote(source.path, safe='/')}{fragment}"
    )
    return replace(source, url=url)
