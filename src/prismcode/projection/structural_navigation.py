from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from urllib.parse import quote

from prismcode.model.contracts import (
    EvidenceItem,
    ReviewSourcePacket,
    StructuralGraphEdge,
    StructuralGraphNode,
    StructuralNavigationPurpose,
    StructuralNavigationTarget,
)


@dataclass(frozen=True)
class StructuralNavigationProjection:
    nodes: tuple[StructuralGraphNode, ...]
    edges: tuple[StructuralGraphEdge, ...]
    targets: tuple[StructuralNavigationTarget, ...]


def project_structural_navigation(
    *,
    nodes: tuple[StructuralGraphNode, ...],
    edges: tuple[StructuralGraphEdge, ...],
    evidence: dict[str, EvidenceItem],
    packet: ReviewSourcePacket | None,
) -> StructuralNavigationProjection:
    """Project every structural destination once, before presentation."""

    targets = []
    projected_nodes = []
    target_by_node_id: dict[str, StructuralNavigationTarget] = {}
    for node in nodes:
        symbol_target = _symbol_target(node, evidence, packet)
        change_target = _change_target(node, evidence, packet)
        targets.extend((symbol_target, change_target))
        target_by_node_id[node.id] = symbol_target
        projected_nodes.append(
            replace(
                node,
                symbol_navigation_target_id=symbol_target.id,
                change_navigation_target_id=change_target.id,
            )
        )

    projected_edges = tuple(
        replace(
            edge,
            source_navigation_target_id=target_by_node_id[
                edge.source_node_id
            ].id,
            target_navigation_target_id=target_by_node_id[
                edge.target_node_id
            ].id,
        )
        for edge in edges
    )
    return StructuralNavigationProjection(
        nodes=tuple(projected_nodes),
        edges=projected_edges,
        targets=tuple(targets),
    )


def _symbol_target(
    node: StructuralGraphNode,
    evidence: dict[str, EvidenceItem],
    packet: ReviewSourcePacket | None,
) -> StructuralNavigationTarget:
    target_id = _target_id(node.id, "symbol")
    fact = evidence.get(node.display_evidence_id)
    revision = (
        "base"
        if node.delta == "removed"
        else "head"
        if node.delta in {"added", "modified", "renamed"}
        else fact.revision_side
        if fact is not None and fact.revision_side in {"base", "head"}
        else None
    )
    sha = (
        packet.base_sha
        if packet is not None and revision == "base"
        else packet.head_sha
        if packet is not None and revision == "head"
        else None
    )
    path, line_start, line_end = _location(fact)
    if (
        packet is None
        or revision is None
        or fact is None
        or fact.revision_side != revision
        or not sha
        or not path
    ):
        return _unavailable(
            target_id,
            node.id,
            "symbol",
            "repository revision or symbol location is unavailable",
        )
    line = _blob_line_fragment(line_start, line_end)
    return StructuralNavigationTarget(
        id=target_id,
        owner_node_id=node.id,
        purpose="symbol",
        state="available",
        kind="revision_symbol",
        revision_side=revision,
        url=(
            f"https://github.com/{packet.repository}/blob/{sha}/"
            f"{quote(path, safe='/')}{line}"
        ),
        path=path,
        line_start=line_start,
        line_end=line_end,
    )


def _change_target(
    node: StructuralGraphNode,
    evidence: dict[str, EvidenceItem],
    packet: ReviewSourcePacket | None,
) -> StructuralNavigationTarget:
    target_id = _target_id(node.id, "change")
    if node.delta not in {"added", "modified", "renamed", "removed"}:
        return _unavailable(
            target_id,
            node.id,
            "change",
            "node is retained context or has no canonical change operation",
        )
    revision = "base" if node.delta == "removed" else "head"
    fact = _changed_location_fact(node, evidence, revision)
    path, _start, _end = _location(fact)
    changed_lines = tuple(
        int(item)
        for item in (fact.metadata.get("changed_lines", ()) if fact else ())
    )
    if (
        packet is None
        or packet.pull_request is None
        or not path
        or not changed_lines
    ):
        return _unavailable(
            target_id,
            node.id,
            "change",
            "exact changed line or pull request location is unavailable",
        )
    line = min(changed_lines)
    side = "L" if revision == "base" else "R"
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()
    return StructuralNavigationTarget(
        id=target_id,
        owner_node_id=node.id,
        purpose="change",
        state="available",
        kind="pull_request_diff",
        revision_side=revision,
        url=(
            f"https://github.com/{packet.repository}/pull/"
            f"{packet.pull_request}/files#diff-{digest}{side}{line}"
        ),
        path=path,
        line_start=line,
        line_end=max(changed_lines),
    )


def _changed_location_fact(
    node: StructuralGraphNode,
    evidence: dict[str, EvidenceItem],
    revision: str,
) -> EvidenceItem | None:
    candidates = tuple(
        evidence[item_id]
        for item_id in node.evidence_ids
        if item_id in evidence
        and evidence[item_id].revision_side == revision
        and evidence[item_id].metadata.get("changed_lines")
    )
    return min(candidates, key=lambda item: item.id) if candidates else None


def _location(
    fact: EvidenceItem | None,
) -> tuple[str | None, int | None, int | None]:
    if fact is None:
        return None, None, None
    path = fact.metadata.get("path")
    start = fact.metadata.get("start_line")
    end = fact.metadata.get("end_line")
    if path:
        return str(path), _integer(start), _integer(end)
    for source in fact.sources:
        if source.path:
            return source.path, source.line_start, source.line_end
    return None, None, None


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _blob_line_fragment(
    line_start: int | None,
    line_end: int | None,
) -> str:
    if line_start is None:
        return ""
    if line_end is not None and line_end != line_start:
        return f"#L{line_start}-L{line_end}"
    return f"#L{line_start}"


def _target_id(node_id: str, purpose: StructuralNavigationPurpose) -> str:
    digest = hashlib.sha256(f"{node_id}\0{purpose}".encode()).hexdigest()[:20]
    return f"SNT:{digest}"


def _unavailable(
    target_id: str,
    node_id: str,
    purpose: StructuralNavigationPurpose,
    reason: str,
) -> StructuralNavigationTarget:
    return StructuralNavigationTarget(
        id=target_id,
        owner_node_id=node_id,
        purpose=purpose,
        state="unavailable",
        reason=reason,
    )
