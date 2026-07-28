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

    head = _map_overlaps(changes, head_provider, "head")
    revisions: list[StructuralGraphResult] = []
    diagnostics = list(changes.diagnostics)
    if base_provider is not None:
        base = _map_overlaps(changes, base_provider, "base")
        head = head_provider.complete_counterparts(
            head,
            tuple(overlap.symbol for overlap in base.overlaps),
        )
        base = base_provider.complete_counterparts(
            base,
            tuple(overlap.symbol for overlap in head.overlaps),
        )
        head = head_provider.expand_structure(head)
        base = base_provider.expand_structure(base)
        revisions.extend(
            (
                _attach_github_line_sources(packet, head),
                _attach_github_line_sources(packet, base),
            )
        )
    elif any(hunk.removed_lines for hunk in changes.hunks):
        head = head_provider.expand_structure(head)
        revisions.append(_attach_github_line_sources(packet, head))
        diagnostics.append(
            Diagnostic(
                code="structural_graph_base_input_missing",
                message=(
                    "Changed base lines exist, but no base-revision checkout "
                    "was provided; base structural facts were not collected."
                ),
            )
        )
    else:
        head = head_provider.expand_structure(head)
        revisions.append(_attach_github_line_sources(packet, head))
    result = StructuralGraphCollection(
        revisions=tuple(revisions),
        diagnostics=tuple(diagnostics),
    )
    result.validate_consistency()
    return result


def _map_overlaps(
    changes: DiffHunkCollection,
    provider: StructuralGraphProvider,
    revision_side: StructuralRevision,
) -> StructuralGraphResult:
    result = provider.symbols_overlapping(changes.hunks)
    if result.revision_side != revision_side:
        raise ValueError("structural provider returned the wrong revision side")
    return result


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
    ownership_relations = tuple(
        replace(
            relation,
            parent=enrich_symbol(relation.parent),
            child=enrich_symbol(relation.child),
            sources=tuple(
                _line_source(packet, parsed, source, revision)
                for source in relation.sources
            ),
        )
        for relation in result.ownership_relations
    )
    counterpart_symbols = tuple(
        enrich_symbol(symbol) for symbol in result.counterpart_symbols
    )
    return replace(
        result,
        overlaps=overlaps,
        counterpart_symbols=counterpart_symbols,
        paths=paths,
        ownership_relations=ownership_relations,
    )


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
