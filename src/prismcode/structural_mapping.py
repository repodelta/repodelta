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
