from __future__ import annotations

from html import escape
from pathlib import Path
import re
from urllib.parse import quote, urlparse, urlunparse

from prismcode.model.contracts import (
    ChangedFile,
    EvidenceItem,
    ProjectionDiagnostic,
    ProjectionRelation,
    ReviewBrief,
    ReviewProjection,
    ReviewSlice,
    ReviewStatement,
    ReviewStructuralGraph,
    SourceRef,
    StructuralGraphEdge,
    StructuralGraphNode,
    StructuralGraphOwnershipEdge,
)

_DEFERRED_STRUCTURAL_PREVIEW_LIMIT = 5


def _safe_href(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else None


def _source(source: SourceRef) -> str:
    parsed = urlparse(source.url or "")
    parts = tuple(part for part in parsed.path.split("/") if part)
    concrete_label = None
    if len(parts) >= 4 and parts[-2] == "issues" and parts[-1].isdigit():
        concrete_label = f"Issue #{parts[-1]}"
    elif len(parts) >= 4 and parts[-2] == "pull" and parts[-1].isdigit():
        concrete_label = f"PR #{parts[-1]}"
    label_parts = source.label.split(" · ", 1)
    section = label_parts[1] if len(label_parts) == 2 else None
    display_label = concrete_label or label_parts[0]
    if section:
        display_label += f" · {section}"
    label = escape(display_label)
    href = _safe_href(source.url)
    if href and section and not parsed.fragment:
        fragment = re.sub(r"[^a-z0-9]+", "-", section.casefold()).strip("-")
        href = urlunparse(parsed._replace(fragment=fragment))
    if href:
        return (
            f'<a class="source-link" href="{escape(href, quote=True)}" '
            f'target="_blank" rel="noopener">{label}</a>'
        )
    if source.path:
        return f"<code>{escape(source.path)}</code>"
    return label


def _sources(item: EvidenceItem, brief: ReviewBrief) -> str:
    unique: list[SourceRef] = []
    seen: set[tuple[object, ...]] = set()
    for source in item.sources:
        key = (source.url, source.path, source.line_start, source.line_end)
        if key in seen:
            continue
        seen.add(key)
        if not source.url and source.path and brief.packet.head_sha:
            line = f"#L{source.line_start}" if source.line_start else ""
            if source.line_end and source.line_end != source.line_start:
                line += f"-L{source.line_end}"
            source = SourceRef(
                label=source.label,
                url=(
                    f"https://github.com/{brief.packet.repository}/blob/"
                    f"{brief.packet.head_sha}/{quote(source.path, safe='/')}{line}"
                ),
                path=source.path,
                line_start=source.line_start,
                line_end=source.line_end,
            )
        unique.append(source)
    shown = " · ".join(_source(source) for source in unique[:3])
    return shown + (
        f' <span class="more">+{len(unique) - 3} sources</span>'
        if len(unique) > 3
        else ""
    )


def _changed_file(item: ChangedFile) -> str:
    href = _safe_href(item.source_url)
    display_path = item.display_path
    source = (
        f'<a class="file-link" href="{escape(href, quote=True)}" '
        f'target="_blank" rel="noopener">{escape(Path(display_path).name)}</a>'
    if href
        else escape(Path(display_path).name)
    )
    counts = []
    if item.additions is not None:
        counts.append(f"+{item.additions}")
    if item.deletions is not None:
        counts.append(f"-{item.deletions}")
    return (
        '<div class="file-row"><div class="file-name">'
        f'{source}<span class="file-path">{escape(_changed_file_path(item))}</span></div>'
        f'<div class="file-state">{escape(item.status)}'
        + (f" · {' '.join(counts)}" if counts else "")
        + "</div></div>"
    )


def _changed_file_path(item: ChangedFile) -> str:
    if item.status == "renamed":
        return f"{item.base_path} → {item.head_path}"
    return item.display_path


def _statement_context(label: str, statements: tuple[ReviewStatement, ...]) -> str:
    if not statements:
        return ""
    rows = []
    for item in statements:
        sources = " · ".join(_source(source) for source in item.sources)
        rows.append(
            '<div class="context-row">'
            f'<span class="context-id">{escape(item.id)}</span>'
            f'<span class="context-copy">{escape(item.text)}</span>'
            f'<span class="context-authority">{escape(item.authority.replace("_", " "))}</span>'
            + (
                f'<span class="context-source">Source: {sources}</span>'
                if sources
                else ""
            )
            + "</div>"
        )
    return (
        f'<details class="context"><summary>{escape(label)} · {len(statements)} '
        f"statement{'s' if len(statements) != 1 else ''}</summary>"
        f'<div class="context-list">{"".join(rows)}</div></details>'
    )


def _relation_fact(
    relation: ProjectionRelation,
    brief: ReviewBrief,
    *,
    label: str,
) -> str:
    evidence = brief.evidence_catalog.by_id().get(relation.target_id)
    if evidence is None:
        raise ValueError(f"projection references missing evidence: {relation.target_id}")
    sources = _sources(evidence, brief)
    reason = relation.reasons[0] if relation.reasons else None
    reason_copy = reason.detail if reason else relation.association.replace("_", " ")
    return (
        '<div class="projection-item">'
        f'<span class="relation-label">{escape(label)}</span>'
        f'<span class="projection-copy">{escape(evidence.summary)}</span>'
        f'<span class="relation-reason">{escape(reason_copy)}</span>'
        + (
            f'<span class="projection-source">Source: {sources}</span>'
            if sources
            else ""
        )
        + "</div>"
    )


def _boundary_fact(
    relation: ProjectionRelation,
    brief: ReviewBrief,
) -> str:
    evidence = brief.evidence_catalog.by_id().get(relation.target_id)
    if evidence is None or evidence.guardrail_scan_result is None:
        raise ValueError(
            f"projection references invalid boundary fact: {relation.target_id}"
        )
    result = evidence.guardrail_scan_result
    coverage = " · ".join(
        (
            f"{item.surface}: {item.state}"
            f" ({item.inspected_count} inspected"
            f"{f', {item.inspected_bytes} bytes' if item.inspected_bytes else ''})"
        )
        for item in result.coverages
    )
    truncation = " · ".join(
        (
            f"{item.kind.replace('_', ' ')} on {item.surface}: "
            f"limit {item.limit}, observed {item.observed}"
        )
        for item in result.truncations
    )
    sources = _sources(evidence, brief)
    return (
        '<div class="projection-item">'
        '<span class="relation-label">bounded observation</span>'
        f'<span class="projection-copy">{escape(evidence.summary)}</span>'
        f'<span class="relation-reason">{escape(coverage)}</span>'
        + (
            f'<span class="relation-reason">Safety boundary: '
            f"{escape(truncation)}</span>"
            if truncation
            else ""
        )
        + (
            f'<span class="projection-source">Candidate locations: {sources}</span>'
            if sources
            else '<span class="projection-source">No selector match observed '
            "within the stated bounded coverage.</span>"
        )
        + "</div>"
    )


def _diagnostic_rows(
    diagnostics: tuple[ProjectionDiagnostic, ...],
    *,
    slots: set[str],
) -> str:
    rows = []
    for item in diagnostics:
        if item.slot not in slots or item.state == "not_applicable":
            continue
        rows.append(
            '<div class="slot-diagnostic">'
            f'<span>{escape(item.slot.replace("_", " "))} · '
            f'{escape(item.state.replace("_", " "))}</span>'
            f"<p>{escape(item.message)}</p></div>"
        )
    return "".join(rows)


def _review_graph(
    graph: ReviewStructuralGraph,
    projection: ReviewProjection,
    brief: ReviewBrief,
) -> str:
    if not graph.nodes:
        return ""
    evidence = brief.evidence_catalog.by_id()
    nodes = {item.id: item for item in graph.nodes}
    edges = {item.id: item for item in graph.edges}
    ownership_edges = {item.id: item for item in graph.ownership_edges}
    backbone_nodes = {
        node_id: nodes[node_id] for node_id in graph.backbone_node_ids
    }
    backbone_edges = tuple(
        edges[edge_id] for edge_id in graph.backbone_edge_ids
    )
    backbone_ownership_edges = tuple(
        ownership_edges[edge_id]
        for edge_id in graph.backbone_ownership_edge_ids
    )
    node_focus: dict[str, list[tuple[str, str]]] = {}
    edge_focus: dict[str, list[str]] = {}
    ownership_edge_focus: dict[str, list[str]] = {}
    for review_slice in projection.slices:
        focus_id = review_slice.focus_statement_id
        for node in review_slice.structural_overlay.nodes:
            if node.node_id not in nodes:
                raise ValueError(
                    f"{focus_id}: structural overlay references missing node "
                    f"{node.node_id}"
                )
            node_focus.setdefault(node.node_id, []).append(
                (focus_id, node.role)
            )
        for edge_id in review_slice.structural_overlay.edge_ids:
            if edge_id not in edges:
                raise ValueError(
                    f"{focus_id}: structural overlay references missing edge "
                    f"{edge_id}"
                )
            edge_focus.setdefault(edge_id, []).append(focus_id)
        for edge_id in review_slice.structural_overlay.ownership_edge_ids:
            if edge_id not in ownership_edges:
                raise ValueError(
                    f"{focus_id}: structural overlay references missing ownership "
                    f"edge {edge_id}"
                )
            ownership_edge_focus.setdefault(edge_id, []).append(focus_id)
    executable_connected_node_ids = {
        node_id
        for edge in backbone_edges
        for node_id in (edge.source_node_id, edge.target_node_id)
    }
    ownership_connected_node_ids = {
        node_id
        for edge in backbone_ownership_edges
        for node_id in (edge.parent_node_id, edge.child_node_id)
    }
    connected_node_ids = executable_connected_node_ids | ownership_connected_node_ids
    connected_nodes = tuple(
        node
        for node in backbone_nodes.values()
        if node.id in connected_node_ids
    )
    positions, canvas_width, canvas_height = _structural_layout(
        connected_nodes,
        backbone_edges,
        backbone_ownership_edges,
    )

    ownership_edge_shapes = []
    occupied_label_boxes: list[tuple[int, int, int, int]] = []
    for edge in backbone_ownership_edges:
        parent_node = nodes.get(edge.parent_node_id)
        child_node = nodes.get(edge.child_node_id)
        ownership_change = evidence.get(edge.ownership_change_evidence_id)
        parent = (
            _structural_node_fact(parent_node.evidence_ids, evidence)
            if parent_node is not None
            else None
        )
        child = (
            _structural_node_fact(child_node.evidence_ids, evidence)
            if child_node is not None
            else None
        )
        if (
            parent_node is None
            or child_node is None
            or parent is None
            or child is None
        ):
            raise ValueError("ownership edge references a missing node")
        if (
            ownership_change is None
            or ownership_change.kind != "structural_ownership_change"
        ):
            raise ValueError(
                "ownership edge references missing ownership-change evidence"
            )
        parent_x, parent_y = positions[edge.parent_node_id]
        child_x, child_y = positions[edge.child_node_id]
        label = f"contains · {edge.operation}"
        path, label_x, label_y, label_width = _structural_edge_path(
            parent_x,
            parent_y,
            child_x,
            child_y,
            label,
            occupied_label_boxes,
        )
        ownership_edge_shapes.append(
            f'<g class="ownership-edge operation-{escape(edge.operation)}" '
            f'data-focuses="{escape(" ".join(ownership_edge_focus.get(edge.id, ())), quote=True)}">'
            f'<path d="{path}" marker-end="url(#arrow-ownership-{escape(edge.operation)})"/>'
            f'<rect class="delta-edge-label-bg" x="{label_x - label_width // 2}" '
            f'y="{label_y - 11}" width="{label_width}" height="16" rx="4"/>'
            f'<text class="delta-edge-label" x="{label_x}" y="{label_y}">'
            f"{escape(label)}</text>"
            f"<title>{escape(parent.summary)} → {escape(child.summary)}</title></g>"
        )

    edge_shapes = []
    for edge in backbone_edges:
        source_node = nodes.get(edge.source_node_id)
        target_node = nodes.get(edge.target_node_id)
        relation_change = evidence.get(edge.relation_change_evidence_id)
        source = (
            next(
                (
                    evidence.get(evidence_id)
                    for evidence_id in source_node.evidence_ids
                ),
                None,
            )
            if source_node is not None
            else None
        )
        target = (
            next(
                (
                    evidence.get(evidence_id)
                    for evidence_id in target_node.evidence_ids
                ),
                None,
            )
            if target_node is not None
            else None
        )
        if source_node is None or target_node is None or source is None or target is None:
            raise ValueError("structural graph edge references a missing node")
        if relation_change is None or relation_change.kind != "structural_relation_change":
            raise ValueError(
                "structural graph edge references a missing relation-change fact"
            )
        source_x, source_y = positions[edge.source_node_id]
        target_x, target_y = positions[edge.target_node_id]
        label = f"{edge.relation} · {edge.operation}"
        path, label_x, label_y, label_width = _structural_edge_path(
            source_x,
            source_y,
            target_x,
            target_y,
            label,
            occupied_label_boxes,
        )
        edge_shapes.append(
            f'<g class="delta-edge operation-{escape(edge.operation)}" '
            f'data-focuses="{escape(" ".join(edge_focus.get(edge.id, ())), quote=True)}">'
            f'<path d="{path}" marker-end="url(#arrow-{escape(edge.operation)})"/>'
            f'<rect class="delta-edge-label-bg" x="{label_x - label_width // 2}" '
            f'y="{label_y - 11}" width="{label_width}" height="16" rx="4"/>'
            f'<text class="delta-edge-label" x="{label_x}" y="{label_y}">'
            f"{escape(label)}</text>"
            f"<title>{escape(source.summary)} → {escape(target.summary)} · "
            f'{len(edge.path_relation_ids)} support refs</title></g>'
        )

    node_shapes = []
    for node in connected_nodes:
        fact = _structural_node_fact(node.evidence_ids, evidence)
        x, y = positions[node.id]
        full_name = _structural_name(fact)
        path_label, name_label = _structural_label_parts(full_name)
        kind = str(fact.metadata.get("symbol_kind", "symbol")).replace("_", " ")
        focuses = " ".join(
            focus_id for focus_id, _role in node_focus.get(node.id, ())
        )
        content = (
            f'<g class="delta-node operation-{escape(node.delta)}'
            + (
                " ownership-only"
                if node.id not in executable_connected_node_ids
                else ""
            )
            + '" '
            f'data-focuses="{escape(focuses, quote=True)}" '
            f'transform="translate({x} {y})">'
            '<rect width="210" height="72" rx="10"/>'
            f'<text class="delta-node-kind" x="12" y="17">'
            f'{escape(kind)} · {escape(node.delta)}</text>'
            f'<text class="delta-node-name" x="12" y="39">'
            f'{escape(name_label)}</text>'
            f'<text class="delta-node-path" x="12" y="57">'
            f'{escape(path_label)}</text>'
            f"<title>{escape(full_name)}</title></g>"
        )
        href = _structural_href(fact, brief)
        node_shapes.append(
            f'<a href="{escape(href, quote=True)}" target="_blank" '
            f'rel="noopener">{content}</a>'
            if href
            else content
        )

    isolated_rows = []
    for node in backbone_nodes.values():
        if node.id in connected_node_ids or node.delta == "retained":
            continue
        fact = _structural_node_fact(node.evidence_ids, evidence)
        sources = _sources(fact, brief)
        focuses = ", ".join(
            focus_id for focus_id, _role in node_focus.get(node.id, ())
        )
        kind = str(fact.metadata.get("symbol_kind", "symbol")).replace("_", " ")
        isolated_rows.append(
            f'<div class="isolated-anchor operation-{escape(node.delta)}" '
            f'data-focuses="{escape(" ".join(item[0] for item in node_focus.get(node.id, ())), quote=True)}">'
            f'<span class="isolated-anchor-focus">{escape(focuses)}</span>'
            f'<span class="isolated-anchor-operation">{escape(node.delta)}</span>'
            f'<span class="isolated-anchor-name">{escape(_structural_name(fact))}</span>'
            f'<span class="isolated-anchor-kind">{escape(kind)}</span>'
            + (
                f'<span class="projection-source">Source: {sources}</span>'
                if sources
                else ""
            )
            + "</div>"
        )

    visible_focus_ids = {
        *(
            focus_id
            for node_id, focus_roles in node_focus.items()
            if node_id in backbone_nodes
            for focus_id, _role in focus_roles
        ),
        *(
            focus_id
            for edge_id, edge_focus_ids in edge_focus.items()
            if edge_id in graph.backbone_edge_ids
            for focus_id in edge_focus_ids
        ),
        *(
            focus_id
            for edge_id, edge_focus_ids in ownership_edge_focus.items()
            if edge_id in graph.backbone_ownership_edge_ids
            for focus_id in edge_focus_ids
        ),
    }
    focus_ids = tuple(
        review_slice.focus_statement_id for review_slice in projection.slices
    )
    slices_by_focus = {
        review_slice.focus_statement_id: review_slice
        for review_slice in projection.slices
    }
    controls = (
        '<div class="delta-focus-controls" role="group" '
        'aria-label="Structural graph focus">'
        '<button class="delta-focus active" type="button" '
        'data-focus-target="all">All</button>'
        + "".join(
            (
            f'<button class="delta-focus'
            f'{" no-visible-backbone" if focus_id not in visible_focus_ids else ""}'
            f' disposition-{escape(slices_by_focus[focus_id].structural_disposition.state)}" '
            f'type="button" '
            f'data-focus-target="{escape(focus_id, quote=True)}" '
            f'data-empty-copy="{escape(_structural_focus_empty_copy(slices_by_focus[focus_id]), quote=True)}" '
            f'title="{escape(_structural_disposition_label(slices_by_focus[focus_id]), quote=True)}">'
            f"{escape(focus_id)}</button>"
            )
            for focus_id in focus_ids
        )
        + (
            '<button class="hierarchy-toggle active" type="button" '
            'aria-pressed="true">Structure</button>'
            if backbone_ownership_edges
            else ""
        )
        + "</div>"
    )
    canvas = (
        '<div class="delta-canvas-scroll"><svg class="delta-canvas" '
        f'viewBox="0 0 {canvas_width} {canvas_height}" '
        f'aria-label="Structural delta graph" role="img">'
        "<defs>"
        '<marker id="arrow-added" markerWidth="8" markerHeight="8" refX="7" '
        'refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z"/></marker>'
        '<marker id="arrow-removed" markerWidth="8" markerHeight="8" refX="7" '
        'refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z"/></marker>'
        '<marker id="arrow-retained" markerWidth="8" markerHeight="8" refX="7" '
        'refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z"/></marker>'
        '<marker id="arrow-ownership-added" markerWidth="8" markerHeight="8" '
        'refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z"/></marker>'
        '<marker id="arrow-ownership-removed" markerWidth="8" markerHeight="8" '
        'refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z"/></marker>'
        '<marker id="arrow-ownership-retained" markerWidth="8" markerHeight="8" '
        'refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z"/></marker>'
        "</defs>"
        + "".join(ownership_edge_shapes)
        + "".join(edge_shapes)
        + "".join(node_shapes)
        + "</svg></div>"
        if connected_nodes
        else '<p class="delta-empty">No safe canonical relation delta is available.</p>'
    )
    isolated = (
        '<details class="isolated-anchors"><summary>'
        f'{len(isolated_rows)} isolated changed anchor'
        f'{"s" if len(isolated_rows) != 1 else ""}</summary>'
        f'<div class="isolated-anchor-list">{"".join(isolated_rows)}</div></details>'
        if isolated_rows
        else ""
    )
    return (
        '<div class="review-structural-graph">'
        '<div class="delta-graph-heading"><div>'
        '<h3>Structural delta graph</h3>'
        f'<div class="subgraph-summary">{len(backbone_nodes)} backbone nodes · '
        f'{len(graph.nodes) - len(backbone_nodes)} support nodes · '
        f'{len(backbone_edges)} backbone executable edges · '
        f'{len(backbone_ownership_edges)} backbone ownership edges · '
        f'{len(isolated_rows)} isolated changed anchors · '
        f'{len(graph.path_relation_ids)} support refs</div></div>'
        f'{controls}</div><p class="delta-focus-empty" hidden></p>{canvas}{isolated}'
        "</div>"
    )


def _structural_disposition_label(review_slice: ReviewSlice) -> str:
    state = review_slice.structural_disposition.state
    return {
        "projected": "Structural evidence projected",
        "non_structural_only": "Review evidence only; no structural projection",
        "deferred": "Structural candidates deferred",
        "unassociated": "No deterministic structural association",
        "unavailable": "Structural evidence unavailable or not applicable",
        "no_structural_evidence": "No structural evidence",
    }[state]


def _structural_focus_empty_copy(review_slice: ReviewSlice) -> str:
    focus_id = review_slice.focus_statement_id
    state = review_slice.structural_disposition.state
    if state == "projected":
        return (
            f"{focus_id} has projected structural evidence outside the default "
            "change backbone."
        )
    return {
        "non_structural_only": (
            f"{focus_id} has review evidence, but no deterministically associated "
            "structural node or edge."
        ),
        "deferred": (
            f"{focus_id} has structural candidates, but they were deferred by an "
            "upstream safety boundary."
        ),
        "unassociated": (
            f"{focus_id} has no deterministic structural association."
        ),
        "unavailable": (
            f"{focus_id} structural evidence is unavailable or not applicable."
        ),
        "no_structural_evidence": (
            f"{focus_id} has no eligible structural evidence."
        ),
    }[state]


def _structural_node_fact(
    evidence_ids: tuple[str, ...],
    evidence: dict[str, EvidenceItem],
) -> EvidenceItem:
    fact = next((evidence.get(evidence_id) for evidence_id in evidence_ids), None)
    if fact is None:
        raise ValueError("structural graph references missing node evidence")
    return fact


def _structural_label_parts(value: str) -> tuple[str, str]:
    path, separator, name = value.partition(" · ")
    if not separator:
        return "", _truncate_label(path, 30)
    return _truncate_label(path, 34), _truncate_label(name, 30)


def _truncate_label(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _structural_href(item: EvidenceItem, brief: ReviewBrief) -> str | None:
    for source in item.sources:
        href = _safe_href(source.url)
        if href:
            return href
        if source.path and brief.packet.head_sha:
            line = f"#L{source.line_start}" if source.line_start else ""
            return (
                f"https://github.com/{brief.packet.repository}/blob/"
                f"{brief.packet.head_sha}/{quote(source.path, safe='/')}{line}"
            )
    return None


def _structural_layout(
    nodes: tuple[StructuralGraphNode, ...],
    edges: tuple[StructuralGraphEdge, ...],
    ownership_edges: tuple[StructuralGraphOwnershipEdge, ...] = (),
) -> tuple[dict[str, tuple[int, int]], int, int]:
    node_ids = tuple(node.id for node in nodes)
    predecessors = {node_id: set() for node_id in node_ids}
    successors = {node_id: set() for node_id in node_ids}
    for edge in edges:
        if edge.source_node_id in successors and edge.target_node_id in predecessors:
            successors[edge.source_node_id].add(edge.target_node_id)
            predecessors[edge.target_node_id].add(edge.source_node_id)
    for edge in ownership_edges:
        if edge.parent_node_id in successors and edge.child_node_id in predecessors:
            successors[edge.parent_node_id].add(edge.child_node_id)
            predecessors[edge.child_node_id].add(edge.parent_node_id)
    levels = {node_id: 0 for node_id in node_ids}
    remaining = set(node_ids)
    ready = [node_id for node_id in node_ids if not predecessors[node_id]]
    while ready:
        node_id = ready.pop(0)
        if node_id not in remaining:
            continue
        remaining.remove(node_id)
        for target_id in node_ids:
            if target_id not in successors[node_id]:
                continue
            levels[target_id] = max(levels[target_id], levels[node_id] + 1)
            if predecessors[target_id].isdisjoint(remaining):
                ready.append(target_id)
    for node_id in node_ids:
        if node_id in remaining:
            connected_levels = [
                levels[source_id] + 1
                for source_id in predecessors[node_id]
                if source_id not in remaining
            ]
            levels[node_id] = max(connected_levels, default=0)
    by_level: dict[int, list[str]] = {}
    for node_id in node_ids:
        by_level.setdefault(levels[node_id], []).append(node_id)
    positions = {
        node_id: (30 + level * 360, 35 + row * 120)
        for level, level_nodes in by_level.items()
        for row, node_id in enumerate(level_nodes)
    }
    column_count = max(by_level, default=0) + 1
    row_count = max((len(items) for items in by_level.values()), default=1)
    return positions, max(620, 60 + column_count * 360), 70 + row_count * 120


def _structural_edge_path(
    source_x: int,
    source_y: int,
    target_x: int,
    target_y: int,
    label: str,
    occupied_label_boxes: list[tuple[int, int, int, int]],
) -> tuple[str, int, int, int]:
    start_x, start_y = source_x + 210, source_y + 36
    end_x, end_y = target_x, target_y + 36
    if end_x > start_x:
        control = max(36, (end_x - start_x) // 2)
        path = (
            f"M {start_x} {start_y} C {start_x + control} {start_y}, "
            f"{end_x - control} {end_y}, {end_x} {end_y}"
        )
    else:
        bend_y = max(source_y + 90, target_y + 90)
        path = (
            f"M {start_x} {start_y} C {start_x + 35} {bend_y}, "
            f"{end_x - 35} {bend_y}, {end_x} {end_y}"
        )
    right_x, right_y = (
        (target_x, target_y)
        if target_x >= source_x
        else (source_x, source_y)
    )
    label_x = right_x - 75
    label_width = max(52, min(140, len(label) * 5 + 12))
    for offset in (0, -18, 18, -36, 36, -54, 54):
        label_y = right_y + 36 + offset
        candidate = (
            label_x - label_width // 2,
            label_y - 12,
            label_x + label_width // 2,
            label_y + 6,
        )
        if not any(
            not (
                candidate[2] <= occupied[0]
                or occupied[2] <= candidate[0]
                or candidate[3] <= occupied[1]
                or occupied[3] <= candidate[1]
            )
            for occupied in occupied_label_boxes
        ):
            occupied_label_boxes.append(candidate)
            return path, label_x, label_y, label_width
    occupied_label_boxes.append(candidate)
    return path, label_x, label_y, label_width


def _structural_name(item: EvidenceItem) -> str:
    qualified_name = str(item.metadata.get("qualified_name", item.summary))
    path = str(item.metadata.get("path", ""))
    if not path:
        return qualified_name
    parts = Path(path).parts
    short_path = "/".join(parts[-2:])
    return f"{short_path} · {qualified_name}"


def _projection_slice(
    review_slice: ReviewSlice,
    statement: ReviewStatement,
    brief: ReviewBrief,
    *,
    profile: str,
    diagnostics: tuple[ProjectionDiagnostic, ...],
) -> str:
    relations = brief.projection_candidates.by_id()
    claims = {item.id: item for item in brief.claims}

    claim_rows = []
    for relation_id in review_slice.claim_relation_ids:
        relation = relations.get(relation_id)
        claim = claims.get(relation.target_id) if relation else None
        if relation is None or claim is None:
            raise ValueError(f"projection references missing claim relation: {relation_id}")
        source = " · ".join(_source(item) for item in claim.sources)
        reason = relation.reasons[0] if relation.reasons else None
        claim_rows.append(
            '<div class="projection-item">'
            f'<span class="relation-label">{escape(relation.association.replace("_", " "))}</span>'
            f'<span class="projection-copy"><b>{escape(claim.id)}</b> {escape(claim.text)}</span>'
            + (
                f'<span class="relation-reason">{escape(reason.detail)}</span>'
                if reason
                else ""
            )
            + (
                f'<span class="projection-source">Source: {source}</span>'
                if source
                else ""
            )
            + "</div>"
        )

    groups = (
        (
            "Changed anchors",
            review_slice.standalone_changed_fact_relation_ids,
            "changed fact",
        ),
        (
            "Test support",
            review_slice.standalone_test_support_relation_ids,
            "changed test",
        ),
        (
            "Documentation support",
            review_slice.standalone_document_support_relation_ids,
            "changed document",
        ),
        (
            "Runtime context",
            review_slice.standalone_runtime_relation_ids,
            "context fact",
        ),
        (
            "Test context",
            review_slice.standalone_test_relation_ids,
            "context fact",
        ),
        (
            "Verification",
            review_slice.verification_relation_ids,
            "current-head observation",
        ),
    )
    fact_groups = []
    disposition = _structural_disposition(
        review_slice,
        brief,
        relations=relations,
    )
    if disposition:
        fact_groups.append(disposition)
    if review_slice.guardrail_scan_plan_id is not None:
        plan = brief.guardrail_scan_plans.by_id().get(
            review_slice.guardrail_scan_plan_id
        )
        if plan is None:
            raise ValueError(
                "projection references missing guardrail scan plan: "
                f"{review_slice.guardrail_scan_plan_id}"
            )
        sources = " · ".join(_source(source) for source in plan.sources)
        fact_groups.append(
            '<div class="projection-group">'
            '<span class="block-title">Guardrail scan plan</span>'
            f'<span class="projection-copy">{escape(plan.scope)} '
            f'{" / ".join(escape(item) for item in plan.surfaces)} · '
            f'{escape(plan.revision_side)} revision</span>'
            f'<span class="relation-reason">{escape(plan.query_text)}</span>'
            + (
                '<span class="relation-reason">Selectors: '
                + " · ".join(escape(item.value) for item in plan.selectors)
                + "</span>"
                if plan.selectors
                else '<span class="relation-reason">No conservative executable '
                "selector.</span>"
            )
            + (
                f'<span class="projection-source">Source: {sources}</span>'
                if sources
                else ""
            )
            + "</div>"
        )
    boundary_rows = "".join(
        _boundary_fact(relations[relation_id], brief)
        for relation_id in review_slice.boundary_fact_relation_ids
        if relation_id in relations
    )
    if boundary_rows:
        fact_groups.append(
            '<div class="projection-group"><span class="block-title">'
            f"Boundary scan observation</span>{boundary_rows}</div>"
        )
    for heading, relation_ids, label in groups:
        rows = "".join(
            _relation_fact(relations[relation_id], brief, label=label)
            for relation_id in relation_ids
            if relation_id in relations
        )
        if rows:
            fact_groups.append(
                f'<div class="projection-group"><span class="block-title">'
                f"{escape(heading)}</span>{rows}</div>"
            )
    claim_diagnostics = _diagnostic_rows(
        diagnostics,
        slots={"claim"},
    )
    fact_diagnostics = _diagnostic_rows(
        diagnostics,
        slots={
            "changed_anchor",
            "runtime_context",
            "test_context",
            "verification",
            "structural_path",
            "boundary_fact",
        },
    )
    contract_label = statement.authority.replace("_", " ")
    statement_sources = " · ".join(_source(source) for source in statement.sources)
    authority_note = f"{statement.role.replace('_', ' ')} · {statement.purpose.replace('_', ' ')}"
    return (
        '<div class="projection">'
        '<div class="projection-column">'
        f'<span class="projection-heading">{escape(contract_label)}</span>'
        f'<span class="profile-chip">{escape(profile.replace("_", " "))}</span>'
        f'<p class="projection-copy">{escape(statement.text)}</p>'
        f'<span class="relation-reason">{escape(authority_note)}</span>'
        + (
            f'<span class="projection-source">Source: {statement_sources}</span>'
            if statement_sources
            else ""
        )
        + "</div>"
        '<div class="projection-arrow">→</div>'
        '<div class="projection-column">'
        '<span class="projection-heading">PR says</span>'
        + "".join(claim_rows)
        + claim_diagnostics
        + "</div>"
        '<div class="projection-arrow">→</div>'
        '<div class="projection-column projection-facts">'
        '<span class="projection-heading">Repository facts</span>'
        + "".join(fact_groups)
        + fact_diagnostics
        + "</div></div>"
    )


def _structural_disposition(
    review_slice: ReviewSlice,
    brief: ReviewBrief,
    *,
    relations: dict[str, ProjectionRelation],
) -> str:
    disposition = review_slice.structural_disposition
    if (
        disposition.state == "projected"
        and not disposition.deferred_structural_relation_ids
    ):
        return ""
    deferred_relation_ids = disposition.deferred_structural_relation_ids
    displayed_deferred_ids = deferred_relation_ids[
        :_DEFERRED_STRUCTURAL_PREVIEW_LIMIT
    ]
    deferred_rows = "".join(
        _relation_fact(
            relations[relation_id],
            brief,
            label="deferred structural candidate",
        )
        for relation_id in displayed_deferred_ids
        if relation_id in relations
    )
    return (
        '<div class="projection-group structural-disposition">'
        '<span class="block-title">Structural disposition</span>'
        f'<span class="projection-copy">{escape(_structural_disposition_label(review_slice))}</span>'
        + (
            '<span class="relation-reason">'
            f'{len(disposition.non_structural_relation_ids)} selected '
            "non-structural evidence "
            f'item{"s" if len(disposition.non_structural_relation_ids) != 1 else ""}.'
            "</span>"
            if disposition.non_structural_relation_ids
            else ""
        )
        + (
            '<details class="deferred-structural"><summary>'
            f'{len(displayed_deferred_ids)} of {len(deferred_relation_ids)} deferred '
            "structural candidate"
            f'{"s" if len(deferred_relation_ids) != 1 else ""}'
            f"</summary>{deferred_rows}"
            + (
                '<span class="relation-reason">'
                f'{len(deferred_relation_ids) - len(displayed_deferred_ids)} '
                "additional canonical relations omitted from display."
                "</span>"
                if len(deferred_relation_ids) > len(displayed_deferred_ids)
                else ""
            )
            + "</details>"
            if deferred_rows
            else ""
        )
        + "</div>"
    )


def _attention(brief: ReviewBrief) -> str:
    rows = (
        '<div class="attention-row">'
        f'<div class="attention-kind">{escape(item.label)}</div>'
        f'<div class="attention-copy">{escape(", ".join(item.focus_statement_ids))}'
        + (" · " if item.focus_statement_ids else "")
        + f"{escape(item.message)}</div></div>"
        for item in brief.overview.attention
    )
    rendered = "".join(rows)
    return rendered or '<p class="empty">No unresolved attention items.</p>'


def render_html(brief: ReviewBrief) -> str:
    packet = brief.packet
    statements = {
        item.id: item for item in (*brief.requirements, *brief.guardrails)
    }
    groups = {
        item.focus_statement_id: item
        for item in brief.projection_candidates.groups
    }
    diagnostics = {
        **brief.projection_candidates.diagnostics_by_id(),
        **brief.candidate_convergence.diagnostics_by_id(),
    }
    cards = []
    for index, review_slice in enumerate(brief.projection.slices):
        statement = statements.get(review_slice.focus_statement_id)
        group = groups.get(review_slice.focus_statement_id)
        if statement is None or group is None:
            raise ValueError(
                f"projection references missing focus: {review_slice.focus_statement_id}"
            )
        slice_diagnostics = tuple(
            diagnostics[diagnostic_id]
            for diagnostic_id in review_slice.diagnostic_ids
            if diagnostic_id in diagnostics
        )
        if len(slice_diagnostics) != len(review_slice.diagnostic_ids):
            raise ValueError(
                f"projection references missing diagnostic: {review_slice.focus_statement_id}"
            )
        focus_attribute = (
            f' data-focus-id="{escape(statement.id, quote=True)}"'
        )
        cards.append(
            f'<details class="requirement"{focus_attribute}'
            f'{" open" if index == 0 else ""}>'
            '<summary>'
            f'<span class="req-id">{escape(statement.id)}</span>'
            f'<span class="req-title">{escape(statement.text)}</span>'
            '</summary><div class="req-body">'
            f"{_projection_slice(review_slice, statement, brief, profile=group.profile, diagnostics=slice_diagnostics)}</div></details>"
        )
    if not cards:
        if brief.overview.empty_review_message is None:
            raise ValueError("projection rendered no cards without an empty-review fact")
        cards.append(
            f'<div class="empty-state">{escape(brief.overview.empty_review_message)}</div>'
        )

    source_priority = {"linked_issue": 0, "ticket": 0, "pull_request": 1}
    source_links = [
        _source(SourceRef(label=record.kind, url=record.url))
        for record in sorted(
            packet.source_records,
            key=lambda item: source_priority.get(item.kind, 2),
        )
        if record.kind in {"linked_issue", "ticket", "pull_request"} and record.url
    ]
    source_line = " · ".join(source_links) or "Source URL not provided."
    pr_label = (
        f"PR #{packet.pull_request}"
        if packet.pull_request is not None
        else "Fixture review"
    )
    pr_state = brief.overview.pull_request_state.title()
    ci_copy = {
        "not_observed": "CI: no run observed",
        "failure": "CI: failure observed",
        "passing": "CI: passing",
        "pending": "CI: queued or running",
    }[brief.overview.ci_state]
    pr_link = (
        _source(SourceRef(label=pr_label, url=packet.source_url))
        if packet.source_url
        else escape(pr_label)
    )
    files = "".join(_changed_file(item) for item in packet.changed_files)
    review_contract = (
        '<div class="review-contract">'
        + _statement_context("Goals", brief.objectives)
        + _statement_context("Scope", brief.scope)
        + _statement_context(
            "Verification expectations",
            brief.verification_expectations,
        )
        + "</div>"
        if (
            brief.objectives
            or brief.scope
            or brief.verification_expectations
        )
        else ""
    )
    semantic_context = _statement_context("PR claim context", brief.claims)
    review_graph = _review_graph(
        brief.projection.review_graph,
        brief.projection,
        brief,
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(packet.title)} · PrismCode</title>
<style>
:root{{color-scheme:dark;--bg:#080c0f;--panel:#10171b;--border:#26373f;--text:#edf3f0;--muted:#9eaaaf;--faint:#6f7d83;--green:#7be3ac;--amber:#e7ca7c;--red:#ef8f91;--blue:#9fcdf0;--shadow:0 22px 64px rgba(0,0,0,.28)}}*{{box-sizing:border-box}}body{{margin:0;color:var(--text);line-height:1.55;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:radial-gradient(circle at 18% -8%,rgba(69,167,118,.12),transparent 31rem),var(--bg)}}code{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}}.shell{{width:min(1180px,calc(100% - 40px));margin:30px auto 84px}}.topbar{{margin-bottom:22px;font-weight:720}}.brand-mark{{display:inline-block;width:14px;height:14px;margin-right:10px;border:2px solid white;transform:rotate(45deg);border-radius:3px}}.section{{border:2px solid var(--border);border-radius:18px;background:linear-gradient(180deg,rgba(17,24,28,.97),rgba(11,17,21,.98));box-shadow:var(--shadow);padding:28px;margin-bottom:22px}}h1{{font-size:31px;margin:0 0 14px}}h2{{font-size:22px;margin:0 0 14px}}h3{{font-size:16px;margin:0 0 8px}}.meta{{display:flex;flex-wrap:wrap;gap:9px;color:var(--muted);font-size:13px;margin-bottom:16px}}.intent{{max-width:850px;color:#d2dade;font-size:15px}}.source-link,.file-link{{color:#b9dfff;text-decoration:none}}.source-note,.projection-source,.context-source{{display:block;color:var(--faint);font-size:10px;line-height:1.45}}.requirements{{border-top:1px solid rgba(111,128,135,.24)}}.requirement{{border-bottom:1px solid rgba(111,128,135,.24)}}.requirement summary{{list-style:none;cursor:pointer;display:grid;grid-template-columns:52px minmax(0,1fr);gap:16px;padding:18px 0}}.requirement summary::-webkit-details-marker{{display:none}}.req-id{{color:var(--green);font:760 12px ui-monospace,SFMono-Regular,Menlo,monospace}}.req-title{{font-size:14px;font-weight:640}}.req-body{{padding:0 0 22px 68px}}.projection{{display:grid;grid-template-columns:minmax(0,.85fr) 24px minmax(0,1fr) 24px minmax(0,1.35fr);gap:10px;align-items:start}}.projection-column{{min-width:0;padding:14px;border:1px solid rgba(111,128,135,.22);border-radius:12px;background:rgba(5,10,13,.24)}}.projection-heading,.block-title{{display:block;margin-bottom:9px;color:#89979d;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.045em}}.projection-arrow{{align-self:center;color:var(--faint);text-align:center}}.profile-chip,.relation-label{{display:inline-flex;margin:0 0 8px;padding:3px 7px;border-radius:999px;background:rgba(54,118,87,.20);color:#bfeacf;font-size:8px;font-weight:720}}.projection-copy{{margin:0 0 7px;color:#d7dddf;font-size:11px}}.projection-item{{padding:9px 0;border-bottom:1px solid rgba(111,128,135,.16)}}.projection-item:last-child{{border-bottom:0}}.relation-reason{{display:block;color:var(--faint);font-size:9px;margin-bottom:6px}}.projection-group+.projection-group{{margin-top:15px}}.review-structural-graph{{margin-top:24px;padding:18px;border:1px solid rgba(111,128,135,.22);border-radius:12px;background:rgba(5,10,13,.24)}}.delta-graph-heading{{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}}.subgraph-summary{{color:var(--muted);font-size:9px}}.delta-focus-controls{{display:flex;flex:1 1 560px;min-width:0;max-width:720px;flex-wrap:wrap;justify-content:flex-end;gap:5px}}.delta-focus,.hierarchy-toggle{{border:1px solid rgba(111,128,135,.35);border-radius:999px;padding:4px 9px;background:transparent;color:var(--muted);font:700 9px inherit;cursor:pointer}}.delta-focus:hover,.delta-focus.active,.hierarchy-toggle:hover,.hierarchy-toggle.active{{border-color:var(--green);background:rgba(54,118,87,.20);color:#c9efd6}}.hierarchy-toggle{{margin-left:7px;border-color:rgba(159,205,240,.5);color:var(--blue)}}.delta-canvas-scroll{{margin-top:14px;overflow-x:auto;border:1px solid rgba(111,128,135,.16);border-radius:10px;background:rgba(3,7,9,.34)}}.delta-canvas{{display:block;min-width:100%;height:auto;max-height:720px}}.delta-edge,.ownership-edge,.delta-node,.isolated-anchor{{transition:opacity .16s ease,filter .16s ease}}.delta-edge path,.ownership-edge path{{fill:none}}.delta-edge path{{stroke-width:1.8}}.ownership-edge path{{stroke-width:1.25;stroke-dasharray:3 4}}.delta-edge-label-bg{{fill:rgba(3,7,9,.92);stroke:rgba(111,128,135,.24);stroke-width:.7}}.delta-edge-label{{font-size:8px;text-anchor:middle;paint-order:stroke;stroke:var(--bg);stroke-width:2px;stroke-linejoin:round}}.delta-edge.operation-added path,.ownership-edge.operation-added path{{stroke:var(--green)}}.delta-edge.operation-added text,.ownership-edge.operation-added text{{fill:var(--green)}}.delta-edge.operation-removed path,.ownership-edge.operation-removed path{{stroke:var(--red);stroke-dasharray:6 5}}.delta-edge.operation-removed text,.ownership-edge.operation-removed text{{fill:var(--red)}}.delta-edge.operation-retained path{{stroke:#73848c}}.delta-edge.operation-retained text{{fill:#94a2a8}}.ownership-edge.operation-retained path{{stroke:var(--blue)}}.ownership-edge.operation-retained text{{fill:var(--blue)}}#arrow-added path{{fill:var(--green)}}#arrow-removed path{{fill:var(--red)}}#arrow-retained path{{fill:#73848c}}#arrow-ownership-added path{{fill:var(--green)}}#arrow-ownership-removed path{{fill:var(--red)}}#arrow-ownership-retained path{{fill:var(--blue)}}.hierarchy-collapsed .ownership-edge,.hierarchy-collapsed .delta-node.ownership-only{{display:none}}.delta-node rect{{fill:#111a1f;stroke:#53656e;stroke-width:1.2}}.delta-node.operation-added rect{{stroke:var(--green);fill:rgba(54,118,87,.14)}}.delta-node.operation-modified rect{{stroke:var(--amber);fill:rgba(106,85,30,.13)}}.delta-node.operation-removed rect{{stroke:var(--red);stroke-dasharray:6 4;fill:rgba(112,43,48,.12)}}.delta-node-kind{{fill:var(--muted);font-size:8px;text-transform:uppercase}}.delta-node-name{{fill:var(--text);font-size:10px;font-weight:700}}.delta-node-path{{fill:var(--faint);font-size:8px}}.focus-muted{{opacity:.13}}.focus-active{{opacity:1;filter:drop-shadow(0 0 5px rgba(123,227,172,.35))}}.delta-empty{{margin:14px 0 0;padding:18px;border:1px dashed rgba(111,128,135,.26);border-radius:10px;color:var(--faint);font-size:11px}}.isolated-anchors{{margin-top:12px;border-top:1px solid rgba(111,128,135,.18);padding-top:10px}}.isolated-anchors>summary{{cursor:pointer;color:var(--muted);font-size:10px}}.isolated-anchor-list{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin-top:9px}}.isolated-anchor{{display:grid;grid-template-columns:auto 1fr auto;gap:4px 7px;min-width:0;padding:8px;border:1px solid rgba(111,128,135,.16);border-left:2px solid var(--amber);border-radius:7px}}.isolated-anchor.operation-added{{border-left-color:var(--green)}}.isolated-anchor.operation-removed{{border-left-color:var(--red);border-style:dashed}}.isolated-anchor-focus,.isolated-anchor-operation,.isolated-anchor-kind{{color:var(--faint);font-size:8px}}.isolated-anchor-operation{{text-transform:uppercase}}.isolated-anchor-kind{{text-align:right}}.isolated-anchor-name{{grid-column:1/-1;overflow-wrap:anywhere;font-size:9px}}.isolated-anchor .projection-source{{grid-column:1/-1}}.slot-diagnostic{{margin:9px 0;padding:9px;border-radius:8px;background:rgba(106,85,30,.16);color:#e8d18e;font-size:9px}}.slot-diagnostic p{{margin:3px 0 0;color:var(--muted)}}.context{{margin-bottom:12px;padding-bottom:12px;border-bottom:1px solid rgba(111,128,135,.24)}}.context>summary{{cursor:pointer;color:var(--muted);font-size:11px}}.context-row{{display:grid;grid-template-columns:48px minmax(0,1fr) 120px;gap:12px;padding:12px 0;border-bottom:1px solid rgba(111,128,135,.18)}}.context-id{{color:#9fcdf0;font:700 11px ui-monospace,SFMono-Regular,Menlo,monospace}}.context-copy{{font-size:12px}}.context-authority{{color:var(--muted);font-size:10px;text-align:right}}.context-source{{grid-column:2/-1}}.attention-list,.file-list{{border-top:1px solid rgba(111,128,135,.24)}}.attention-row{{display:grid;grid-template-columns:220px minmax(0,1fr);gap:18px;padding:14px 0;border-bottom:1px solid rgba(111,128,135,.24)}}.attention-kind{{color:var(--amber);font-size:10px;font-weight:700;text-transform:uppercase}}.attention-copy{{color:#cbd4d7;font-size:12px}}.file-row{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px;padding:14px 0;border-bottom:1px solid rgba(111,128,135,.24)}}.file-name{{font-size:13px;font-weight:650}}.file-path{{display:block;color:var(--faint);font-size:10px}}.file-state{{color:var(--muted);font-size:10px}}.empty,.empty-state{{color:var(--faint);font-size:12px}}.footer{{margin-top:26px;color:var(--faint);font-size:12px;text-align:center}}@media(max-width:950px){{.projection{{grid-template-columns:1fr}}.projection-arrow{{transform:rotate(90deg)}}.req-body{{padding-left:0}}.isolated-anchor-list{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}@media(max-width:600px){{.shell{{width:calc(100% - 18px);margin-top:16px}}.section{{padding:22px 20px}}.attention-row,.context-row{{grid-template-columns:1fr}}.delta-graph-heading{{display:block}}.delta-focus-controls{{max-width:none;justify-content:flex-start;margin-top:10px}}.isolated-anchor-list{{grid-template-columns:1fr}}}}@media print{{:root{{color-scheme:light;--bg:#fff;--panel:#fff;--text:#111;--muted:#444;--faint:#666;--border:#bbb}}body{{background:#fff}}.section{{box-shadow:none;break-inside:avoid}}.delta-focus-controls{{display:none}}.delta-canvas-scroll{{overflow:visible}}.delta-canvas{{max-height:none}}}}
.delta-graph-heading{{flex-wrap:wrap}}
.delta-node.operation-renamed rect{{stroke:var(--blue);stroke-dasharray:8 3;fill:rgba(48,83,110,.14)}}.isolated-anchor.operation-renamed{{border-left-color:var(--blue);border-style:dashed}}
.delta-node.operation-retained rect{{stroke:#53656e;fill:#111a1f}}.delta-node.operation-unresolved rect{{stroke:var(--faint);stroke-dasharray:3 3;fill:rgba(111,125,131,.08)}}.isolated-anchor.operation-unresolved{{border-left-color:var(--faint);border-style:dashed}}
.delta-focus.no-visible-backbone{{border-style:dashed;color:var(--faint)}}
.delta-focus-empty{{margin:12px 0 0;padding:9px 11px;border:1px dashed rgba(111,128,135,.3);border-radius:8px;color:var(--muted);font-size:10px}}.deferred-structural>summary{{cursor:pointer;color:var(--muted);font-size:9px}}
</style></head><body><main class="shell">
<div class="topbar"><span class="brand-mark"></span>PrismCode</div>
<section class="section"><div class="meta">{pr_link}<span>·</span><span>{escape(pr_state)}</span><span>·</span><span>{brief.overview.changed_file_count} changed files</span><span>·</span><span>{escape(ci_copy)}</span></div><h1>{escape(packet.title)}</h1><div class="intent">{escape(brief.intent.text)}</div><span class="source-note">Source: {source_line}</span>{review_contract}</section>
<section class="section"><h2>Review checks</h2>{semantic_context}{review_graph}<div class="requirements">{"".join(cards)}</div></section>
<section class="section"><h2>Needs attention</h2><div class="attention-list">{_attention(brief)}</div></section>
<section class="section"><h2>Changed areas</h2><div class="file-list">{files or '<p class="empty">Not provided.</p>'}</div></section>
<div class="footer">PrismCode · {escape(pr_label)} · Schema {escape(brief.schema_version)} · Generated by {escape(brief.generated_by)}</div>
</main><script>
document.querySelectorAll(".review-structural-graph").forEach((graph) => {{
  const section = graph.closest(".section");
  const requirements = section
    ? section.querySelectorAll(".requirement[data-focus-id]")
    : [];
  const activateFocus = (focus) => {{
    let activeButton = null;
    graph.querySelectorAll(".delta-focus").forEach((item) => {{
      const active = item.dataset.focusTarget === focus;
      item.classList.toggle("active", active);
      if (active) activeButton = item;
    }});
    graph.querySelectorAll("[data-focuses]").forEach((item) => {{
      const active = focus === "all" ||
        item.dataset.focuses.split(/\\s+/).includes(focus);
      item.classList.toggle("focus-muted", !active);
      item.classList.toggle("focus-active", focus !== "all" && active);
    }});
    const empty = graph.querySelector(".delta-focus-empty");
    if (empty) {{
      const show = focus !== "all" &&
        activeButton?.classList.contains("no-visible-backbone");
      empty.hidden = !show;
      empty.textContent = show ? activeButton.dataset.emptyCopy : "";
    }}
  }};
  graph.querySelectorAll(".delta-focus").forEach((button) => {{
    button.addEventListener("click", () =>
      activateFocus(button.dataset.focusTarget));
  }});
  const hierarchyToggle = graph.querySelector(".hierarchy-toggle");
  if (hierarchyToggle) {{
    hierarchyToggle.addEventListener("click", () => {{
      const collapsed = graph.classList.toggle("hierarchy-collapsed");
      hierarchyToggle.classList.toggle("active", !collapsed);
      hierarchyToggle.setAttribute("aria-pressed", String(!collapsed));
    }});
  }}
  requirements.forEach((requirement) => {{
    requirement.querySelector("summary").addEventListener("click", () =>
      activateFocus(requirement.dataset.focusId));
  }});
}});
</script></body></html>"""


def write_html(brief: ReviewBrief, output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(brief), encoding="utf-8")
    return path
