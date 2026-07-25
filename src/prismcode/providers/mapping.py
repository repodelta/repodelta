from __future__ import annotations

from dataclasses import replace
from urllib.parse import ParseResult, quote, urlparse

from prismcode.model.contracts import ReviewSourcePacket, SourceRef
from prismcode.changes.hunks import DiffHunkCollection
from prismcode.providers.structural import (
    GraphSymbol,
    StructuralGraphProvider,
    StructuralGraphResult,
)


def map_packet_changed_symbols(
    packet: ReviewSourcePacket,
    changes: DiffHunkCollection,
    provider: StructuralGraphProvider,
) -> StructuralGraphResult:
    """Map real PR patch hunks to exact structural symbols without conclusions."""

    result = provider.symbols_overlapping(changes.hunks)
    result = provider.expand_paths(result)
    result = _attach_github_line_sources(packet, result)
    if not changes.diagnostics:
        return result
    return replace(
        result,
        diagnostics=(*changes.diagnostics, *result.diagnostics),
    )


def _attach_github_line_sources(
    packet: ReviewSourcePacket, result: StructuralGraphResult
) -> StructuralGraphResult:
    if not packet.head_sha:
        return result
    parsed = urlparse(packet.source_url or "")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return result

    def enrich_symbol(symbol: GraphSymbol) -> GraphSymbol:
        return replace(
            symbol,
            sources=tuple(_line_source(packet, parsed, source) for source in symbol.sources),
        )

    overlaps = tuple(
        replace(
            overlap,
            symbol=enrich_symbol(overlap.symbol),
            sources=tuple(_line_source(packet, parsed, source) for source in overlap.sources),
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
            sources=tuple(_line_source(packet, parsed, source) for source in path.sources),
        )
        for path in result.paths
    )
    return replace(result, overlaps=overlaps, paths=paths)


def _line_source(
    packet: ReviewSourcePacket, parsed: ParseResult, source: SourceRef
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
        f"{root}/{packet.repository}/blob/{packet.head_sha}/"
        f"{quote(source.path, safe='/')}{fragment}"
    )
    return replace(source, url=url)
