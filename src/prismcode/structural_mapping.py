from __future__ import annotations

from dataclasses import replace

from .contracts import ReviewSourcePacket
from .diff_hunks import parse_changed_files
from .structural_graph import StructuralGraphProvider, StructuralGraphResult


def map_packet_changed_symbols(
    packet: ReviewSourcePacket, provider: StructuralGraphProvider
) -> StructuralGraphResult:
    """Map real PR patch hunks to exact structural symbols without conclusions."""

    collection = parse_changed_files(packet.changed_files)
    result = provider.symbols_overlapping(collection.hunks)
    if not collection.diagnostics:
        return result
    return replace(
        result,
        diagnostics=(*collection.diagnostics, *result.diagnostics),
    )


def format_structural_graph_status(
    result: StructuralGraphResult | None,
    *,
    disabled: bool = False,
) -> str:
    if disabled:
        return "Structural mapping: disabled · lexical requirement binding used"
    if result is None:
        return "Structural mapping: unavailable · lexical fallback used"

    state = result.index.state
    if state == "available":
        return (
            "Structural mapping: Codegraph available · "
            f"{result.mapped_hunk_count}/{result.hunk_count} hunks mapped to "
            f"{len(result.overlaps)} symbols · lexical requirement binding retained"
        )
    if state == "partial":
        covered = result.index.requested_files - sum(
            diagnostic.code == "codegraph_file_not_indexed"
            for diagnostic in result.index.diagnostics
        )
        return (
            "Structural mapping: partial · "
            f"{covered}/{result.index.requested_files} changed files indexed · "
            "lexical fallback used for uncovered changes"
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
    return f"Structural mapping: skipped · {reason} · lexical fallback used"
