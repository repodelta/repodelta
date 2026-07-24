from __future__ import annotations

from dataclasses import replace
from urllib.parse import ParseResult, quote, urlparse

from .contracts import ReviewSourcePacket, SourceRef
from .diff_hunks import parse_changed_files
from .structural_graph import (
    GraphSymbol,
    StructuralGraphProvider,
    StructuralGraphResult,
)


def map_packet_changed_symbols(
    packet: ReviewSourcePacket, provider: StructuralGraphProvider
) -> StructuralGraphResult:
    """Map real PR patch hunks to exact structural symbols without conclusions."""

    collection = parse_changed_files(packet.changed_files)
    result = provider.symbols_overlapping(collection.hunks)
    result = provider.expand_paths(result)
    result = _attach_github_line_sources(packet, result)
    if not collection.diagnostics:
        return result
    return replace(
        result,
        diagnostics=(*collection.diagnostics, *result.diagnostics),
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


def format_structural_graph_status(
    result: StructuralGraphResult | None,
    *,
    disabled: bool = False,
) -> str:
    if disabled:
        return "Structural mapping: disabled · changed-hunk fallback used"
    if result is None:
        return "Structural mapping: unavailable · changed-hunk fallback used"

    state = result.index.state
    if state == "available":
        return (
            "Structural mapping: Codegraph available · "
            f"{result.mapped_hunk_count}/{result.hunk_count} hunks mapped to "
            f"{len(result.overlaps)} symbols · {len(result.paths)} bounded paths · "
            "unmapped hunks retained"
        )
    if state == "partial":
        covered = result.index.requested_files - sum(
            diagnostic.code == "codegraph_file_not_indexed"
            for diagnostic in result.index.diagnostics
        )
        return (
            "Structural mapping: partial · "
            f"{covered}/{result.index.requested_files} changed files indexed · "
            "changed-hunk fallback used for uncovered changes"
        )
    reason_by_state = {
        "stale": "Codegraph index is stale",
        "invalid": "Codegraph index schema is incompatible",
        "error": "Codegraph index could not be read",
    }
    if state == "missing":
        codes = {diagnostic.code for diagnostic in result.index.diagnostics}
        reason = (
            "Codegraph index not found"
            if "codegraph_index_missing" in codes
            else "no changed files are present in the Codegraph index"
        )
    else:
        reason = reason_by_state.get(state, f"Codegraph index is {state}")
    return f"Structural mapping: skipped · {reason} · changed-hunk fallback used"
