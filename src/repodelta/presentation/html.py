from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
import re
from urllib.parse import quote, urlparse, urlunparse

from repodelta.model.contracts import (
    ArchitecturalComponent,
    EvidenceItem,
    ReviewBrief,
    ReviewProjection,
    ReviewStatement,
    ReviewStructuralGraph,
    SourceRef,
    StructuralGraphEdge,
    StructuralGraphNode,
    StructuralGraphPlacement,
    StructuralNavigationTarget,
    StructuralRelationGroup,
)

@dataclass(frozen=True)
class _StructuralContainerLayout:
    node_id: str
    x: int
    y: int
    width: int
    height: int
    descendant_node_ids: tuple[str, ...]


@dataclass(frozen=True)
class _StructuralLayout:
    positions: dict[str, tuple[int, int]]
    sizes: dict[str, tuple[int, int]]
    containers: tuple[_StructuralContainerLayout, ...]
    secondary_placements: tuple[StructuralGraphPlacement, ...]
    width: int
    height: int


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


def _statement_rows(statements: tuple[ReviewStatement, ...]) -> str:
    rows = []
    for item in statements:
        sources = " · ".join(_source(source) for source in item.sources)
        rows.append(
            '<div class="context-row">'
            f'<span class="context-id">{escape(item.id)}</span>'
            f'<span class="context-copy">{escape(item.text)}</span>'
            + (
                f'<span class="context-source">Source: {sources}</span>'
                if sources
                else ""
            )
            + "</div>"
        )
    return "".join(rows)


def _statement_context(
    label: str,
    statements: tuple[ReviewStatement, ...],
) -> str:
    if not statements:
        return ""
    return (
        f'<details class="context"><summary>{escape(label)} · {len(statements)} '
        f"statement{'s' if len(statements) != 1 else ''}</summary>"
        f'<div class="context-list">{_statement_rows(statements)}</div></details>'
    )


def _brief_goals(brief: ReviewBrief) -> str:
    if not brief.objectives:
        return ""
    return (
        '<section class="brief-goals" aria-labelledby="brief-goals-heading">'
        '<h2 class="brief-goals-heading" id="brief-goals-heading">Goals</h2>'
        f'<div class="context-list">{_statement_rows(brief.objectives)}</div>'
        '</section>'
    )


def _review_context(brief: ReviewBrief) -> str:
    content = (
        _statement_context("Scope", brief.scope)
        + _statement_context(
            "Verification expectations",
            brief.verification_expectations,
        )
        + (
            _statement_context("PR introduction", (brief.intent,))
            if brief.objectives and brief.intent.authority == "pr_description"
            else ""
        )
        + (
            _statement_context("PR claim context", brief.claims)
            if not brief.projection.verification_workspace.transformation_summary.claim_ids
            else ""
        )
    )
    return f'<div class="brief-context">{content}</div>' if content else ""


def _review_graph(
    graph: ReviewStructuralGraph,
    projection: ReviewProjection,
    brief: ReviewBrief,
) -> str:
    if not graph.nodes:
        return (
            '<div class="review-structural-graph">'
            '<p class="delta-empty">No canonical PR structural facts are available.</p>'
            "</div>"
        )
    evidence = brief.evidence_catalog.by_id()
    architectural_components = {
        node_id: component
        for component in projection.architectural_topology.components
        for node_id in component.node_ids
    }
    nodes = {item.id: item for item in graph.nodes}
    edges = {item.id: item for item in graph.edges}
    relation_groups = {item.id: item for item in graph.relation_groups}
    ownership_edges = {item.id: item for item in graph.ownership_edges}
    placements = tuple(
        item
        for item in graph.placements
        if item.parent_node_id in graph.backbone_node_ids
        and item.child_node_id in graph.backbone_node_ids
    )
    backbone_nodes = {
        node_id: nodes[node_id] for node_id in graph.backbone_node_ids
    }
    backbone_edges = tuple(
        edges[edge_id] for edge_id in graph.backbone_edge_ids
    )
    backbone_relation_groups = tuple(
        relation_groups[group_id]
        for group_id in graph.backbone_relation_group_ids
    )
    backbone_ownership_edges = tuple(
        ownership_edges[edge_id]
        for edge_id in graph.backbone_ownership_edge_ids
    )
    node_focus: dict[str, list[tuple[str, str]]] = {}
    edge_focus: dict[str, list[str]] = {}
    relation_group_focus: dict[str, list[str]] = {}
    ownership_edge_focus: dict[str, list[str]] = {}
    placement_focus: dict[str, list[str]] = {}
    workspace = projection.verification_workspace
    for inspection in workspace.inspections:
        focus_id = inspection.subject_id
        overlay = inspection.structural_overlay
        for node in overlay.nodes:
            if node.node_id not in nodes:
                raise ValueError(
                    f"{focus_id}: structural overlay references missing node "
                    f"{node.node_id}"
                )
            node_focus.setdefault(node.node_id, []).append(
                (focus_id, node.role)
            )
        for group_id in overlay.relation_group_ids:
            if group_id not in relation_groups:
                raise ValueError(
                    f"{focus_id}: structural overlay references missing relation "
                    f"group {group_id}"
                )
            relation_group_focus.setdefault(group_id, []).append(focus_id)
        for edge_id in overlay.edge_ids:
            if edge_id not in edges:
                raise ValueError(
                    f"{focus_id}: structural overlay references missing edge "
                    f"{edge_id}"
                )
            edge_focus.setdefault(edge_id, []).append(focus_id)
        for edge_id in overlay.ownership_edge_ids:
            if edge_id not in ownership_edges:
                raise ValueError(
                    f"{focus_id}: structural overlay references missing ownership "
                    f"edge {edge_id}"
                )
            ownership_edge_focus.setdefault(edge_id, []).append(focus_id)
        for placement_id in overlay.placement_ids:
            placement_focus.setdefault(placement_id, []).append(focus_id)
    executable_connected_node_ids = {
        node_id
        for group in backbone_relation_groups
        for node_id in (group.source_node_id, group.target_node_id)
    }
    ownership_connected_node_ids = {
        node_id
        for edge in backbone_ownership_edges
        for node_id in (edge.parent_node_id, edge.child_node_id)
    }
    placement_connected_node_ids = {
        node_id
        for placement in placements
        for node_id in (placement.parent_node_id, placement.child_node_id)
    }
    connected_node_ids = (
        executable_connected_node_ids
        | ownership_connected_node_ids
        | placement_connected_node_ids
    )
    connected_nodes = tuple(
        node
        for node in backbone_nodes.values()
        if node.id in connected_node_ids
    )
    placed_child_node_ids = {placement.child_node_id for placement in placements}
    layout = _structural_compound_layout(
        connected_nodes,
        backbone_relation_groups,
        placements,
        primary_placement_ids=graph.primary_placement_ids,
    )
    positions = layout.positions
    containers = layout.containers
    secondary_placements = layout.secondary_placements
    canvas_width = layout.width
    canvas_height = layout.height

    container_shapes = []
    container_header_shapes = []
    container_node_ids = {item.node_id for item in containers}
    for container in containers:
        parent_node = nodes[container.node_id]
        fact = _structural_display_fact(parent_node, evidence)
        full_name = _structural_name(fact)
        path_label, name_label = _structural_label_parts(full_name)
        kind = str(fact.metadata.get("symbol_kind", "symbol")).replace("_", " ")
        kind_class = _structural_kind_class(fact)
        direct_focuses = tuple(
            focus_id
            for focus_id, role in node_focus.get(container.node_id, ())
            if role != "intermediate"
        )
        contextual_focuses = tuple(
            dict.fromkeys(
                focus_id
                for focus_id in (
                    *(
                        item_focus_id
                        for item_focus_id, role in node_focus.get(
                            container.node_id, ()
                        )
                        if role == "intermediate"
                    ),
                    *(
                        item_focus_id
                        for node_id in container.descendant_node_ids
                        for item_focus_id, _role in node_focus.get(node_id, ())
                    ),
                )
                if focus_id not in direct_focuses
            )
        )
        container_shapes.append(
            f'<rect class="structural-container {kind_class} '
            f'operation-{escape(parent_node.delta)}" '
            f'data-structural-node="{escape(parent_node.id, quote=True)}" '
            f'data-focuses="{escape(" ".join(direct_focuses), quote=True)}" '
            f'data-context-focuses="{escape(" ".join(contextual_focuses), quote=True)}" '
            f'x="{container.x}" y="{container.y}" '
            f'width="{container.width}" height="{container.height}" rx="14">'
            f"<title>{escape(parent_node.review_symbol_id)} ownership container</title>"
            "</rect>"
        )
        header_chip = (
            _architectural_chip(
                architectural_components[parent_node.id],
                container.width - 24,
            )
            if kind == "file"
            else ""
        )
        header = (
            f'<g class="structural-container-header {kind_class} '
            f'operation-{escape(parent_node.delta)}" '
            f'data-structural-node="{escape(parent_node.id, quote=True)}" '
            f'data-focuses="{escape(" ".join(direct_focuses), quote=True)}" '
            f'data-context-focuses="{escape(" ".join(contextual_focuses), quote=True)}" '
            f'transform="translate({container.x + 12} {container.y + 12})">'
            f'<rect width="{container.width - 24}" height="42" rx="8"/>'
            f'<text class="delta-node-kind" x="11" y="15">'
            f'{escape(kind)} · {escape(parent_node.delta)}</text>'
            f'<text class="delta-node-name" x="11" y="32">'
            f'{escape(name_label or path_label)}</text>'
            f'<line class="structural-container-divider" x1="10" y1="41" '
            f'x2="{container.width - 34}" y2="41"/>'
            f'{header_chip}'
            f"<title>{escape(full_name)}</title></g>"
        )
        href = _structural_node_href(
            parent_node,
            graph.navigation_targets,
        )
        container_header_shapes.append(
            f'<a href="{escape(href, quote=True)}" target="_blank" '
            f'rel="noopener">{header}</a>'
            if href
            else header
        )

    secondary_placement_shapes = []
    for placement in secondary_placements:
        parent_node = nodes.get(placement.parent_node_id)
        child_node = nodes.get(placement.child_node_id)
        parent = (
            _structural_display_fact(parent_node, evidence)
            if parent_node is not None
            else None
        )
        child = (
            _structural_display_fact(child_node, evidence)
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
        child_x, child_y = positions[placement.child_node_id]
        label = (
            "previously in "
            if placement.base_ownership_evidence_ids
            and not placement.head_ownership_evidence_ids
            else "also in "
        ) + _truncate_label(_structural_name(parent), 22)
        focus_ids = placement_focus.get(placement.id, ())
        secondary_placement_shapes.append(
            '<g class="secondary-placement" '
            f'data-context-focuses="{escape(" ".join(focus_ids), quote=True)}">'
            f'<rect x="{child_x + 10}" y="{child_y + 51}" '
            f'width="{max(94, min(190, len(label) * 5 + 16))}" height="16" rx="7"/>'
            f'<text x="{child_x + 18}" y="{child_y + 62}">{escape(label)}</text>'
            f"<title>{escape(parent.summary)} contains {escape(child.summary)}</title>"
            "</g>"
        )

    occupied_label_boxes: list[tuple[int, int, int, int]] = []
    node_boxes = tuple(
        (
            positions[node.id][0],
            positions[node.id][1],
            positions[node.id][0] + layout.sizes[node.id][0],
            positions[node.id][1] + layout.sizes[node.id][1],
        )
        for node in connected_nodes
    )
    edge_shapes = []
    for group in backbone_relation_groups:
        source_node = nodes.get(group.source_node_id)
        target_node = nodes.get(group.target_node_id)
        source = (
            _structural_display_fact(source_node, evidence)
            if source_node is not None
            else None
        )
        target = (
            _structural_display_fact(target_node, evidence)
            if target_node is not None
            else None
        )
        if source_node is None or target_node is None or source is None or target is None:
            raise ValueError("structural graph edge references a missing node")
        source_x, source_y = positions[group.source_node_id]
        target_x, target_y = positions[group.target_node_id]
        label = f"{group.relation} · {group.operation}"
        if len(group.member_edge_ids) > 1:
            label += f" · {len(group.member_edge_ids)} edges"
        path, label_x, label_y, label_width = _structural_edge_path(
            source_x,
            source_y,
            *layout.sizes[group.source_node_id],
            target_x,
            target_y,
            *layout.sizes[group.target_node_id],
            label,
            occupied_label_boxes,
            node_boxes,
        )
        edge_shapes.append(
            f'<g class="delta-edge operation-{escape(group.operation)}" '
            f'tabindex="0" role="button" aria-expanded="false" '
            f'aria-controls="members-{escape(group.id, quote=True)}" '
            f'data-group-target="{escape(group.id, quote=True)}" '
            f'data-focuses="{escape(" ".join(relation_group_focus.get(group.id, ())), quote=True)}">'
            f'<path d="{path}" marker-end="url(#arrow-{escape(group.operation)})"/>'
            f'<rect class="delta-edge-label-bg" x="{label_x - label_width // 2}" '
            f'y="{label_y - 11}" width="{label_width}" height="16" rx="4"/>'
            f'<text class="delta-edge-label" x="{label_x}" y="{label_y}">'
            f"{escape(label)}</text>"
            f"<title>{escape(source.summary)} → {escape(target.summary)} · "
            f'{len(group.member_edge_ids)} canonical edges · '
            f'{len(group.path_evidence_ids)} support refs</title></g>'
        )

    navigation_targets = {
        item.id: item for item in graph.navigation_targets
    }
    relation_group_details = []
    for group in backbone_relation_groups:
        member_rows = []
        group_focuses = tuple(relation_group_focus.get(group.id, ()))
        for edge_id in group.member_edge_ids:
            edge = edges[edge_id]
            source_node = nodes[edge.source_node_id]
            target_node = nodes[edge.target_node_id]
            source = _structural_display_fact(source_node, evidence)
            target = _structural_display_fact(target_node, evidence)
            source_target = navigation_targets.get(
                edge.source_navigation_target_id
            )
            target_target = navigation_targets.get(
                edge.target_navigation_target_id
            )
            direct_focuses = tuple(edge_focus.get(edge.id, ()))
            context_focuses = tuple(
                focus_id
                for focus_id in group_focuses
                if focus_id not in direct_focuses
            )
            member_rows.append(
                '<div class="relation-member" '
                f'data-focuses="{escape(" ".join(direct_focuses), quote=True)}" '
                f'data-context-focuses="{escape(" ".join(context_focuses), quote=True)}">'
                f'<span class="relation-member-operation">{escape(edge.operation)}</span>'
                f'{_structural_navigation_link(source, source_target)}'
                '<span class="relation-member-arrow">→</span>'
                f'{_structural_navigation_link(target, target_target)}'
                f'<span class="relation-member-kind">{escape(edge.relation)}</span>'
                "</div>"
            )
        relation_group_details.append(
            '<details class="relation-group-details" '
            f'id="members-{escape(group.id, quote=True)}" '
            f'data-group-id="{escape(group.id, quote=True)}" '
            f'data-focuses="{escape(" ".join(group_focuses), quote=True)}">'
            f'<summary>{escape(group.relation)} · {escape(group.operation)} · '
            f'{len(group.member_edge_ids)} exact edge'
            f'{"s" if len(group.member_edge_ids) != 1 else ""}</summary>'
            f'<div class="relation-member-list">{"".join(member_rows)}</div>'
            "</details>"
        )

    node_shapes = []
    for node in connected_nodes:
        if node.id in container_node_ids:
            continue
        fact = _structural_display_fact(node, evidence)
        x, y = positions[node.id]
        full_name = _structural_name(fact)
        path_label, name_label = _structural_label_parts(full_name)
        kind = str(fact.metadata.get("symbol_kind", "symbol")).replace("_", " ")
        kind_class = _structural_kind_class(fact)
        direct_focuses = " ".join(
            focus_id
            for focus_id, role in node_focus.get(node.id, ())
            if role != "intermediate"
        )
        contextual_focuses = " ".join(
            focus_id
            for focus_id, role in node_focus.get(node.id, ())
            if role == "intermediate"
        )
        node_chip = (
            _architectural_chip(architectural_components[node.id], 210)
            if node.id not in placed_child_node_ids
            else ""
        )
        content = (
            f'<g class="delta-node {kind_class} operation-{escape(node.delta)}'
            + (
                " ownership-only"
                if node.id not in executable_connected_node_ids
                else ""
            )
            + '" '
            f'data-structural-node="{escape(node.id, quote=True)}" '
            f'data-focuses="{escape(direct_focuses, quote=True)}" '
            f'data-context-focuses="{escape(contextual_focuses, quote=True)}" '
            f'transform="translate({x} {y})">'
            '<rect width="210" height="72" rx="10"/>'
            '<line class="delta-node-marker" x1="2" y1="11" x2="2" y2="61"/>'
            f'<text class="delta-node-kind" x="12" y="17">'
            f'{escape(kind)} · {escape(node.delta)}</text>'
            f'<text class="delta-node-name" x="12" y="39">'
            f'{escape(_structural_symbol_label(fact, name_label))}</text>'
            f'<text class="delta-node-path" x="12" y="57">'
            f'{escape("" if node.id in placed_child_node_ids else path_label)}'
            "</text>"
            f'{node_chip}'
            f"<title>{escape(full_name)}</title></g>"
        )
        href = _structural_node_href(node, graph.navigation_targets)
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
        fact = _structural_display_fact(node, evidence)
        sources = _sources(fact, brief)
        focuses = ", ".join(
            focus_id for focus_id, _role in node_focus.get(node.id, ())
        )
        kind = str(fact.metadata.get("symbol_kind", "symbol")).replace("_", " ")
        isolated_rows.append(
            f'<div class="isolated-anchor operation-{escape(node.delta)}" '
            f'data-structural-node="{escape(node.id, quote=True)}" '
            f'data-focuses="{escape(" ".join(item[0] for item in node_focus.get(node.id, ())), quote=True)}">'
            f'<span class="isolated-anchor-focus">{escape(focuses)}</span>'
            f'<span class="isolated-anchor-operation">{escape(node.delta)}</span>'
            f'<span class="isolated-anchor-name">{escape(_structural_standalone_name(fact))}</span>'
            f'<span class="isolated-anchor-kind">{escape(kind)}</span>'
            f'{_architectural_chip_html(architectural_components[node.id])}'
            + (
                f'<span class="projection-source">Source: {sources}</span>'
                if sources
                else ""
            )
            + "</div>"
        )

    controls = (
        '<div class="delta-focus-controls" role="group" '
        'aria-label="Structural graph focus">'
        '<button class="delta-focus active" type="button" '
        'data-focus-target="all">All</button>'
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
        "</defs>"
        + "".join(container_shapes)
        + "".join(edge_shapes)
        + "".join(container_header_shapes)
        + "".join(node_shapes)
        + "".join(secondary_placement_shapes)
        + "</svg></div>"
        if connected_nodes
        else '<p class="delta-empty">No safe canonical relation delta is available.</p>'
    )
    isolated = (
        '<details class="isolated-anchors"><summary>'
        f'Standalone changes · {len(isolated_rows)}</summary>'
        '<p class="standalone-explanation">Changed facts with no observed '
        'executable or ownership relationship in the projected graph.</p>'
        f'<div class="isolated-anchor-list">{"".join(isolated_rows)}</div></details>'
        if isolated_rows
        else ""
    )
    relationship_inspector = (
        '<details class="relationship-inspector"><summary>'
        f'Exact relationships · {len(backbone_relation_groups)} groups · '
        f'{len(backbone_edges)} edges</summary>'
        '<div class="relation-group-inspector">'
        f'{"".join(relation_group_details)}</div>'
        '</details>'
        if relation_group_details
        else ""
    )
    coverage = brief.overview.structural_coverage
    coverage_state = coverage.state
    coverage_copy = (
        f"Structural coverage · {coverage_state}"
        + (
            f" · {coverage.truncated_seed_count} traversal seeds truncated"
            if coverage.truncated_seed_count
            else ""
        )
    )
    return (
        '<div class="review-structural-graph">'
        '<div class="delta-graph-heading"><div>'
        '<h3>Structural delta graph</h3>'
        f'<div class="structural-coverage state-{escape(coverage_state)}">'
        f"{escape(coverage_copy)}</div>"
        f'<div class="subgraph-summary">{len(backbone_nodes)} backbone nodes · '
        f'{len(graph.nodes) - len(backbone_nodes)} support nodes · '
        f'{len(backbone_relation_groups)} backbone relation groups · '
        f'{len(backbone_edges)} canonical executable edges · '
        f'{len(placements)} structural placements · '
        f'{len(backbone_ownership_edges)} ownership deltas · '
        f'{len(isolated_rows)} isolated changed anchors · '
        f'{len(graph.path_evidence_ids)} support refs</div></div>'
        f'{controls}</div><p class="delta-focus-empty" hidden></p>{canvas}'
        f'{relationship_inspector}'
        f'{isolated}'
        "</div>"
    )


def _architectural_membership_attributes(
    component: ArchitecturalComponent,
) -> str:
    return (
        f'data-component-target="{escape(component.id, quote=True)}" '
        f'data-member-node-ids="{escape(" ".join(component.node_ids), quote=True)}" '
        f'data-context-node-ids="{escape(" ".join(component.context_node_ids), quote=True)}" '
        f'data-member-group-ids="{escape(" ".join(component.internal_relation_group_ids), quote=True)}" '
        f'data-context-group-ids="{escape(" ".join(component.context_relation_group_ids), quote=True)}"'
    )


def _architectural_chip_label(component: ArchitecturalComponent) -> str:
    if component.layer != "unclassified":
        return component.layer
    return component.domain.rsplit("/", 1)[-1] + "?"


def _architectural_chip(
    component: ArchitecturalComponent,
    cell_width: int,
) -> str:
    label = _truncate_label(_architectural_chip_label(component), 16)
    width = max(38, min(88, len(label) * 5 + 14))
    x = cell_width - width - 8
    return (
        '<g class="architectural-chip '
        f'layer-{escape(component.layer)}" tabindex="0" role="button" '
        f'{_architectural_membership_attributes(component)} '
        f'transform="translate({x} 7)">'
        f'<rect width="{width}" height="16" rx="8"/>'
        f'<text x="{width // 2}" y="11">{escape(label)}</text>'
        f'<title>{escape(component.domain)} · {escape(component.layer)} · '
        f'{escape(component.classification_authority.replace("_", " "))}</title>'
        '</g>'
    )


def _architectural_chip_html(component: ArchitecturalComponent) -> str:
    label = _architectural_chip_label(component)
    return (
        '<button class="architectural-chip-html '
        f'layer-{escape(component.layer)}" type="button" '
        f'{_architectural_membership_attributes(component)} '
        f'title="{escape(component.domain, quote=True)} · '
        f'{escape(component.classification_authority.replace("_", " "), quote=True)}">'
        f'{escape(label)}</button>'
    )




def _structural_display_fact(
    node: StructuralGraphNode,
    evidence: dict[str, EvidenceItem],
) -> EvidenceItem:
    fact = evidence.get(node.display_evidence_id)
    if fact is None:
        raise ValueError("structural graph references missing display evidence")
    return fact


def _structural_label_parts(value: str) -> tuple[str, str]:
    path, separator, name = value.partition(" · ")
    if not separator:
        return "", _truncate_qualified_name(path, 30)
    return _truncate_label(path, 34), _truncate_qualified_name(name, 30)


def _truncate_qualified_name(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    if "::" not in value:
        return _truncate_label(value, limit)
    return "…" + value[-(limit - 1) :]


def _truncate_label(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _structural_node_href(
    node: StructuralGraphNode,
    targets: tuple[StructuralNavigationTarget, ...],
) -> str | None:
    by_id = {item.id: item for item in targets}
    change = by_id.get(node.change_navigation_target_id)
    symbol = by_id.get(node.symbol_navigation_target_id)
    if symbol is None:
        return None
    selected = (
        change
        if change is not None and change.state == "available"
        else symbol
    )
    return selected.url if selected.state == "available" else None


def _structural_navigation_link(
    fact: EvidenceItem,
    target: StructuralNavigationTarget | None,
) -> str:
    label = escape(_structural_name(fact))
    if target is None or target.state != "available" or not target.url:
        return (
            '<span class="relation-member-node unavailable">'
            f"{label}<small>navigation unavailable</small></span>"
        )
    return (
        f'<a class="relation-member-node" href="{escape(target.url, quote=True)}" '
        f'target="_blank" rel="noopener">{label}</a>'
    )


def _structural_compound_layout(
    nodes: tuple[StructuralGraphNode, ...],
    edges: tuple[StructuralGraphEdge | StructuralRelationGroup, ...],
    placements: tuple[StructuralGraphPlacement, ...] = (),
    *,
    primary_placement_ids: tuple[str, ...] = (),
) -> _StructuralLayout:
    """Lay out observed containment, then order roots by executable topology."""

    node_ids = tuple(node.id for node in nodes)
    node_id_set = set(node_ids)
    by_child: dict[str, list[StructuralGraphPlacement]] = {}
    for placement in placements:
        if (
            placement.parent_node_id in node_id_set
            and placement.child_node_id in node_id_set
        ):
            by_child.setdefault(placement.child_node_id, []).append(placement)
    primary_ids = set(primary_placement_ids)
    primary_by_child = {
        placement.child_node_id: placement
        for placement in placements
        if placement.id in primary_ids
    }
    children_by_parent: dict[str, list[str]] = {}
    for child_id, placement in primary_by_child.items():
        children_by_parent.setdefault(
            placement.parent_node_id, []
        ).append(child_id)

    descendants: dict[str, tuple[str, ...]] = {}

    def collect_descendants(node_id: str) -> tuple[str, ...]:
        collected = []
        for child_id in children_by_parent.get(node_id, ()):
            collected.append(child_id)
            collected.extend(collect_descendants(child_id))
        descendants[node_id] = tuple(collected)
        return descendants[node_id]

    roots = [
        node_id
        for node_id in node_ids
        if node_id not in primary_by_child
    ]
    for root_id in roots:
        collect_descendants(root_id)

    dimensions: dict[str, tuple[int, int]] = {}

    def measure(node_id: str) -> tuple[int, int]:
        child_ids = children_by_parent.get(node_id, ())
        if not child_ids:
            dimensions[node_id] = (210, 72)
            return dimensions[node_id]
        child_width = 210
        child_height = 0
        for child_id in child_ids:
            width, height = measure(child_id)
            child_width = max(child_width, width)
            child_height += height + 14
        dimensions[node_id] = (
            child_width + 40,
            70 + child_height,
        )
        return dimensions[node_id]

    for root_id in roots:
        measure(root_id)

    def root_for(node_id: str) -> str:
        current = node_id
        while current in primary_by_child:
            current = primary_by_child[current].parent_node_id
        return current

    predecessors = {root_id: set() for root_id in roots}
    successors = {root_id: set() for root_id in roots}
    for edge in edges:
        source_root = root_for(edge.source_node_id)
        target_root = root_for(edge.target_node_id)
        if source_root == target_root:
            continue
        successors[source_root].add(target_root)
        predecessors[target_root].add(source_root)
    levels = {root_id: 0 for root_id in roots}
    remaining = set(roots)
    ready = [root_id for root_id in roots if not predecessors[root_id]]
    while ready:
        root_id = ready.pop(0)
        if root_id not in remaining:
            continue
        remaining.remove(root_id)
        for target_id in roots:
            if target_id not in successors[root_id]:
                continue
            levels[target_id] = max(levels[target_id], levels[root_id] + 1)
            if predecessors[target_id].isdisjoint(remaining):
                ready.append(target_id)
    for root_id in roots:
        if root_id in remaining:
            levels[root_id] = max(
                (
                    levels[parent_id] + 1
                    for parent_id in predecessors[root_id]
                    if parent_id not in remaining
                ),
                default=0,
            )
    roots_by_level: dict[int, list[str]] = {}
    for root_id in roots:
        roots_by_level.setdefault(levels[root_id], []).append(root_id)
    column_widths = {
        level: max(dimensions[root_id][0] for root_id in level_roots)
        for level, level_roots in roots_by_level.items()
    }
    column_x: dict[int, int] = {}
    next_x = 24
    for level in sorted(roots_by_level):
        column_x[level] = next_x
        next_x += column_widths[level] + 110

    positions: dict[str, tuple[int, int]] = {}
    sizes: dict[str, tuple[int, int]] = {}
    containers: list[_StructuralContainerLayout] = []

    def place(node_id: str, x: int, y: int) -> None:
        width, height = dimensions[node_id]
        child_ids = children_by_parent.get(node_id, ())
        if not child_ids:
            positions[node_id] = (x, y)
            sizes[node_id] = (210, 72)
            return
        positions[node_id] = (x + 12, y + 12)
        sizes[node_id] = (width - 24, 42)
        child_y = y + 62
        for child_id in child_ids:
            place(child_id, x + 20, child_y)
            child_y += dimensions[child_id][1] + 14
        containers.append(
            _StructuralContainerLayout(
                node_id=node_id,
                x=x,
                y=y,
                width=width,
                height=height,
                descendant_node_ids=descendants[node_id],
            )
        )

    max_y = 0
    for level, level_roots in roots_by_level.items():
        next_y = 24
        for root_id in level_roots:
            place(root_id, column_x[level], next_y)
            next_y += dimensions[root_id][1] + 56
        max_y = max(max_y, next_y)
    for node_id in node_ids:
        if node_id in positions:
            continue
        measure(node_id)
        place(node_id, next_x, 24)
        next_x += dimensions[node_id][0] + 110
        max_y = max(max_y, dimensions[node_id][1] + 80)

    return _StructuralLayout(
        positions=positions,
        sizes=sizes,
        containers=tuple(containers),
        secondary_placements=tuple(
            placement
            for child_id, candidates in by_child.items()
            for placement in candidates
            if placement != primary_by_child[child_id]
        ),
        width=max(620, next_x - 86),
        height=max(190, max_y),
    )


def _structural_edge_path(
    source_x: int,
    source_y: int,
    source_width: int,
    source_height: int,
    target_x: int,
    target_y: int,
    target_width: int,
    target_height: int,
    label: str,
    occupied_label_boxes: list[tuple[int, int, int, int]],
    node_boxes: tuple[tuple[int, int, int, int], ...] = (),
) -> tuple[str, int, int, int]:
    source_center_y = source_y + source_height // 2
    target_center_y = target_y + target_height // 2
    if target_x >= source_x + source_width:
        start_x = source_x + source_width
        end_x = target_x
        middle_x = (start_x + end_x) // 2
        path = (
            f"M {start_x} {source_center_y} H {middle_x} "
            f"V {target_center_y} H {end_x}"
        )
        label_x = (start_x + middle_x) // 2
        base_label_y = source_center_y - 7
    elif source_x >= target_x + target_width:
        start_x = source_x
        end_x = target_x + target_width
        route_y = max(14, min(source_y, target_y) - 22)
        path = (
            f"M {start_x} {source_center_y} H {start_x - 28} "
            f"V {route_y} H {end_x + 28} "
            f"V {target_center_y} H {end_x}"
        )
        label_x = (start_x + end_x) // 2
        base_label_y = route_y - 5
    else:
        start_x = source_x + source_width
        end_x = target_x + target_width
        gutter_x = max(start_x, end_x) + 30
        path = (
            f"M {start_x} {source_center_y} H {gutter_x} "
            f"V {target_center_y} H {end_x}"
        )
        label_x = gutter_x
        base_label_y = (source_center_y + target_center_y) // 2
    label_width = max(52, min(140, len(label) * 5 + 12))
    for offset in (0, -18, 18, -36, 36, -54, 54, -72, 72):
        label_y = base_label_y + offset
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
        ) and not any(
            not (
                candidate[2] <= node_box[0]
                or node_box[2] <= candidate[0]
                or candidate[3] <= node_box[1]
                or node_box[3] <= candidate[1]
            )
            for node_box in node_boxes
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


def _structural_kind_class(item: EvidenceItem) -> str:
    kind = str(item.metadata.get("symbol_kind", "symbol"))
    normalized = "".join(
        character if character.isalnum() else "-" for character in kind
    )
    return f"kind-{normalized or 'symbol'}"


def _structural_symbol_label(item: EvidenceItem, label: str) -> str:
    kind = str(item.metadata.get("symbol_kind", "symbol"))
    if kind not in {"function", "method"} or label.endswith(")"):
        return label
    return f"{label}()"


def _structural_standalone_name(item: EvidenceItem) -> str:
    if item.metadata.get("symbol_kind") == "file" and item.metadata.get("path"):
        return str(item.metadata["path"])
    path_label, name_label = _structural_label_parts(_structural_name(item))
    display_name = _structural_symbol_label(item, name_label)
    return f"{path_label} · {display_name}" if path_label else display_name




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



def _verification_accordion(brief: ReviewBrief) -> str:
    workspace = brief.projection.verification_workspace
    evidence = brief.evidence_catalog.by_id()
    inspections = workspace.inspections_by_subject_id()
    group_labels = {
        "requirement": "Requirements",
        "guardrail": "Guardrails",
        "transformation_claim": "Transformation claims",
        "completion_condition": "Completion conditions",
    }
    rows = []
    previous_kind = None
    for entry in workspace.matrix:
        inspection = inspections[entry.subject_id]
        if entry.subject_kind != previous_kind:
            rows.append(
                '<div class="verification-group-label">'
                f'{escape(group_labels[entry.subject_kind])}</div>'
            )
            previous_kind = entry.subject_kind
        observed = tuple(
            evidence[item]
            for item in inspection.observed_evidence_ids
            if item in evidence
        )
        observed_rows = "".join(
            '<div class="verification-evidence">'
            f'<span class="evidence-kind">'
            f'{escape(item.profile.replace("_", " "))}</span>'
            f'<span>{escape(item.summary)}</span>'
            + (
                '<span class="projection-source">Source: '
                + " · ".join(_source(source) for source in item.sources)
                + "</span>"
                if item.sources
                else ""
            )
            + "</div>"
            for item in observed[:12]
        )
        if len(observed) > 12:
            observed_rows += (
                '<p class="display-boundary">'
                f'{len(observed) - 12} additional canonical evidence references '
                'remain in the serialized inspection.</p>'
            )
        reasons = "".join(
            '<li><b>'
            f'{escape(item.kind.replace("_", " "))}</b> '
            f'{escape(item.detail)}</li>'
            for item in inspection.assessment_reasons
        )
        if not reasons:
            reasons = (
                '<li>R/G assessment is not owned by the current deterministic '
                'pipeline; evidence remains review support only.</li>'
            )
        source = " · ".join(_source(item) for item in entry.sources)
        graph_copy = (
            f'{len(inspection.structural_overlay.nodes)} graph nodes'
            if inspection.structural_overlay.nodes
            else _structural_focus_label(
                inspection.structural_disposition.state
            )
        )
        focus_empty_copy = _structural_focus_empty_label(
            inspection.structural_disposition.state
        )
        contradiction_copy = (
            f'{len(inspection.contradicting_evidence_ids)} contradicting'
            if inspection.contradicting_evidence_ids
            else "no contradictions"
        )
        rows.append(
            '<details class="verification-item" '
            f'data-verification-subject="{escape(entry.subject_id, quote=True)}"'
            f' data-structural-focus-message="{escape(focus_empty_copy, quote=True)}"'
            '><summary>'
            f'<span class="verification-id">{escape(entry.subject_id)}</span>'
            '<span class="verification-claim">'
            f'<span class="verification-title">{escape(entry.text)}</span>'
            + (
                f'<span class="verification-source">Source: {source}</span>'
                if source
                else ""
            )
            + '</span>'
            f'<span class="status-pill status-{escape(entry.status)}">'
            f'{escape(entry.status.replace("_", " "))}</span></summary>'
            '<div class="verification-detail">'
            '<div><span class="projection-heading">Observed</span>'
            + (
                observed_rows
                if observed_rows
                else '<p class="empty">No associated canonical evidence.</p>'
            )
            + '</div><div><span class="projection-heading">Assessment</span>'
            f'<ul class="assessment-reasons">{reasons}</ul>'
            '<span class="verification-coverage">'
            f'{len(inspection.supporting_evidence_ids)} supporting · '
            f'{escape(contradiction_copy)}'
            f' · {escape(graph_copy)}</span></div></div></details>'
        )
    empty = brief.overview.empty_review_message
    content = "".join(rows)
    return (
        '<div class="verification-accordion">'
        + (
            content
            if content
            else f'<p class="empty-state">{escape(empty or "No verification subject is available.")}</p>'
        )
        + "</div>"
    )


def _structural_focus_label(state: str) -> str:
    return {
        "projected": "structural focus projected",
        "not_applicable": "not applicable to the structural graph",
        "non_structural_only": "non-structural evidence only",
        "deferred": "structural focus deferred by a safety boundary",
        "unassociated": "no deterministic structural association",
        "unavailable": "structural evidence unavailable",
        "no_structural_evidence": "no structural evidence projected",
    }[state]


def _structural_focus_empty_label(state: str) -> str:
    if state == "projected":
        return (
            "Structural evidence exists outside the default change backbone."
        )
    return _structural_focus_label(state).capitalize() + "."


def _coverage_limits(brief: ReviewBrief) -> str:
    if not brief.overview.attention:
        return ""
    return (
        '<details class="coverage-limits"><summary>Coverage limits · '
        f'{len(brief.overview.attention)}</summary>'
        f'<div class="attention-list">{_attention(brief)}</div></details>'
    )


def _transformation_summary(brief: ReviewBrief) -> str:
    workspace = brief.projection.verification_workspace
    summary = workspace.transformation_summary
    if not summary.claim_ids:
        return ""
    entries = workspace.by_subject_id()

    def stage(label: str, claim_ids: tuple[str, ...]) -> str:
        claims = tuple(entries[item] for item in claim_ids)
        rows = "".join(
            '<button class="summary-claim" type="button" '
            f'data-summary-subject="{escape(item.subject_id, quote=True)}" '
            f'title="{escape(item.text, quote=True)}">'
            f'<span>{escape(item.subject_id)}</span>'
            f'<b>{escape(item.text)}</b>'
            f'<i class="status-pill status-{escape(item.status)}">'
            f'{escape(item.status.replace("_", " "))}</i></button>'
            for item in claims
        )
        return (
            '<div class="summary-stage">'
            f'<span class="eyebrow">{escape(label)}</span>'
            f'{rows or "<p class=\"empty\">Not declared.</p>"}</div>'
        )

    transition_ids = tuple(
        dict.fromkeys(
            (
                *summary.change_claim_ids,
                *summary.authority_claim_ids,
                *summary.production_path_claim_ids,
                *summary.migration_claim_ids,
                *summary.removal_claim_ids,
            )
        )
    )
    base_ids = tuple(
        dict.fromkeys(
            (*summary.before_state_claim_ids, *summary.before_topology_claim_ids)
        )
    )
    result_ids = tuple(
        dict.fromkeys(
            (
                *summary.after_state_claim_ids,
                *summary.after_topology_claim_ids,
                *summary.completion_condition_claim_ids,
            )
        )
    )
    limits = (
        f"{len(summary.selected_region_claim_ids)} region · "
        f"{len(summary.boundary_claim_ids)} boundary · "
        f"{len(summary.uncertainty_claim_ids)} uncertainty · "
        f"{len(summary.migration_component_claim_ids)} migration components · "
        f"{len(summary.unassociated_claim_ids)} unassociated · "
        f"{len(summary.base_topology_evidence_ids)} base facts · "
        f"{len(summary.head_topology_evidence_ids)} head facts"
    )
    return (
        '<section class="section transformation-summary">'
        '<h2>Transformation Summary</h2>'
        '<p class="section-intro">A compact index of authored transformation '
        'claims and their existing deterministic statuses. Select an item to '
        'open the canonical evidence inspector.</p>'
        '<div class="transformation-strip">'
        f'{stage("Base", base_ids)}'
        '<span class="summary-arrow" aria-hidden="true">→</span>'
        f'{stage("Change", transition_ids)}'
        '<span class="summary-arrow" aria-hidden="true">→</span>'
        f'{stage("Result", result_ids)}'
        '</div>'
        f'<span class="summary-limits">Coverage boundary · {escape(limits)}</span>'
        '</section>'
    )


def render_html(brief: ReviewBrief) -> str:
    packet = brief.packet
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
    llm_shadow_copy = f"LLM shadow: {brief.overview.llm_shadow.state}"
    pr_link = (
        _source(SourceRef(label=pr_label, url=packet.source_url))
        if packet.source_url
        else escape(pr_label)
    )
    review_graph = _review_graph(
        brief.projection.review_graph,
        brief.projection,
        brief,
    )
    verification_accordion = _verification_accordion(brief)
    transformation_summary = _transformation_summary(brief)
    coverage_limits = _coverage_limits(brief)
    brief_goals = _brief_goals(brief)
    primary_context = brief_goals or (
        f'<div class="intent">{escape(brief.intent.text)}</div>'
    )
    review_context = _review_context(brief)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(packet.title)} · RepoDelta</title>
<style>
:root{{color-scheme:dark;--bg:#080c0f;--panel:#10171b;--border:#26373f;--text:#edf3f0;--muted:#9eaaaf;--faint:#6f7d83;--green:#7be3ac;--amber:#e7ca7c;--red:#ef8f91;--blue:#9fcdf0;--shadow:0 22px 64px rgba(0,0,0,.28)}}*{{box-sizing:border-box}}body{{margin:0;color:var(--text);line-height:1.55;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:radial-gradient(circle at 18% -8%,rgba(69,167,118,.12),transparent 31rem),var(--bg)}}code{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}}.shell{{width:min(1180px,calc(100% - 40px));margin:30px auto 84px}}.topbar{{margin-bottom:22px;font-weight:720}}.brand-mark{{display:inline-block;width:14px;height:14px;margin-right:10px;border:2px solid white;transform:rotate(45deg);border-radius:3px}}.section{{border:2px solid var(--border);border-radius:18px;background:linear-gradient(180deg,rgba(17,24,28,.97),rgba(11,17,21,.98));box-shadow:var(--shadow);padding:28px;margin-bottom:22px}}h1{{font-size:31px;margin:0 0 14px}}h2{{font-size:22px;margin:0 0 14px}}h3{{font-size:16px;margin:0 0 8px}}.meta{{display:flex;flex-wrap:wrap;gap:9px;color:var(--muted);font-size:13px;margin-bottom:16px}}.intent{{max-width:850px;color:#d2dade;font-size:15px}}.source-link,.file-link{{color:#b9dfff;text-decoration:none}}.source-note,.projection-source,.context-source{{display:block;color:var(--faint);font-size:10px;line-height:1.45}}.projection-heading{{display:block;margin-bottom:9px;color:#89979d;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.045em}}.review-structural-graph{{margin-top:24px;padding:18px;border:1px solid rgba(111,128,135,.22);border-radius:12px;background:rgba(5,10,13,.24)}}.delta-graph-heading{{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}}.structural-coverage{{margin-bottom:3px;color:var(--muted);font-size:9px}}.structural-coverage.state-partial,.structural-coverage.state-stale,.structural-coverage.state-missing,.structural-coverage.state-invalid,.structural-coverage.state-error{{color:var(--amber)}}.subgraph-summary{{color:var(--muted);font-size:9px}}.delta-focus-controls{{display:flex;flex:1 1 560px;min-width:0;max-width:720px;flex-wrap:wrap;justify-content:flex-end;gap:5px}}.delta-focus{{border:1px solid rgba(111,128,135,.35);border-radius:999px;padding:4px 9px;background:transparent;color:var(--muted);font:700 9px inherit;cursor:pointer}}.delta-focus:hover,.delta-focus.active{{border-color:var(--green);background:rgba(54,118,87,.20);color:#c9efd6}}.delta-canvas-scroll{{margin-top:14px;overflow-x:auto;border:1px solid rgba(111,128,135,.16);border-radius:10px;background:rgba(3,7,9,.34)}}.delta-canvas{{display:block;min-width:100%;height:auto}}.delta-edge,.structural-container,.delta-node,.isolated-anchor{{transition:opacity .16s ease,filter .16s ease}}.delta-edge path{{fill:none;stroke-width:1.8}}.delta-edge-label-bg{{fill:rgba(3,7,9,.92);stroke:rgba(111,128,135,.24);stroke-width:.7}}.delta-edge-label{{font-size:8px;text-anchor:middle;paint-order:stroke;stroke:var(--bg);stroke-width:2px;stroke-linejoin:round}}.delta-edge.operation-added path{{stroke:var(--green)}}.delta-edge.operation-added text{{fill:var(--green)}}.delta-edge.operation-removed path{{stroke:var(--red);stroke-dasharray:6 5}}.delta-edge.operation-removed text{{fill:var(--red)}}.delta-edge.operation-retained path{{stroke:#73848c}}.delta-edge.operation-retained text{{fill:#94a2a8}}#arrow-added path{{fill:var(--green)}}#arrow-removed path{{fill:var(--red)}}#arrow-retained path{{fill:#73848c}}.structural-container{{fill:rgba(16,27,33,.42);stroke:#354a54;stroke-width:1.1}}.structural-container.operation-added{{stroke:rgba(123,227,172,.52);fill:rgba(54,118,87,.06)}}.structural-container.operation-removed{{stroke:rgba(239,143,145,.5);stroke-dasharray:6 4;fill:rgba(112,43,48,.05)}}.delta-node rect{{fill:#111a1f;stroke:#53656e;stroke-width:1.2}}.delta-node.operation-added rect{{stroke:var(--green);fill:rgba(54,118,87,.14)}}.delta-node.operation-modified rect{{stroke:var(--amber);fill:rgba(106,85,30,.13)}}.delta-node.operation-removed rect{{stroke:var(--red);stroke-dasharray:6 4;fill:rgba(112,43,48,.12)}}.delta-node-kind{{fill:var(--muted);font-size:8px;text-transform:uppercase}}.delta-node-name{{fill:var(--text);font-size:10px;font-weight:700}}.delta-node-path{{fill:var(--faint);font-size:8px}}.focus-muted{{opacity:.13}}.focus-context{{opacity:.7}}.structural-container.focus-context,.structural-container-header.focus-context{{filter:drop-shadow(0 0 2px rgba(159,205,240,.22))}}.focus-active{{opacity:1;filter:drop-shadow(0 0 5px rgba(123,227,172,.35))}}.delta-empty{{margin:14px 0 0;padding:18px;border:1px dashed rgba(111,128,135,.26);border-radius:10px;color:var(--faint);font-size:11px}}.isolated-anchors{{margin-top:12px;border-top:1px solid rgba(111,128,135,.18);padding-top:10px}}.isolated-anchors>summary{{cursor:pointer;color:var(--muted);font-size:10px}}.isolated-anchor-list{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin-top:9px}}.isolated-anchor{{display:grid;grid-template-columns:auto 1fr auto;gap:4px 7px;min-width:0;padding:8px;border:1px solid rgba(111,128,135,.16);border-left:2px solid var(--amber);border-radius:7px}}.isolated-anchor.operation-added{{border-left-color:var(--green)}}.isolated-anchor.operation-removed{{border-left-color:var(--red);border-style:dashed}}.isolated-anchor-focus,.isolated-anchor-operation,.isolated-anchor-kind{{color:var(--faint);font-size:8px}}.isolated-anchor-operation{{text-transform:uppercase}}.isolated-anchor-kind{{text-align:right}}.isolated-anchor-name{{grid-column:1/-1;overflow-wrap:anywhere;font-size:9px}}.isolated-anchor .projection-source{{grid-column:1/-1}}.context{{margin-bottom:12px;padding-bottom:12px;border-bottom:1px solid rgba(111,128,135,.24)}}.context>summary{{cursor:pointer;color:var(--muted);font-size:11px}}.context-row{{display:grid;grid-template-columns:48px minmax(0,1fr) 120px;gap:12px;padding:12px 0;border-bottom:1px solid rgba(111,128,135,.18)}}.context-id{{color:#9fcdf0;font:700 11px ui-monospace,SFMono-Regular,Menlo,monospace}}.context-copy{{font-size:12px}}.context-authority{{color:var(--muted);font-size:10px;text-align:right}}.context-source{{grid-column:2/-1}}.attention-list,.file-list{{border-top:1px solid rgba(111,128,135,.24)}}.attention-row{{display:grid;grid-template-columns:220px minmax(0,1fr);gap:18px;padding:14px 0;border-bottom:1px solid rgba(111,128,135,.24)}}.attention-kind{{color:var(--amber);font-size:10px;font-weight:700;text-transform:uppercase}}.attention-copy{{color:#cbd4d7;font-size:12px}}.file-row{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px;padding:14px 0;border-bottom:1px solid rgba(111,128,135,.24)}}.file-name{{font-size:13px;font-weight:650}}.file-path{{display:block;color:var(--faint);font-size:10px}}.file-state{{color:var(--muted);font-size:10px}}.empty,.empty-state{{color:var(--faint);font-size:12px}}.footer{{margin-top:26px;color:var(--faint);font-size:12px;text-align:center}}@media(max-width:950px){{.isolated-anchor-list{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}@media(max-width:600px){{.shell{{width:calc(100% - 18px);margin-top:16px}}.section{{padding:22px 20px}}.attention-row,.context-row{{grid-template-columns:1fr}}.delta-graph-heading{{display:block}}.delta-focus-controls{{max-width:none;justify-content:flex-start;margin-top:10px}}.isolated-anchor-list{{grid-template-columns:1fr}}}}@media print{{:root{{color-scheme:light;--bg:#fff;--panel:#fff;--text:#111;--muted:#444;--faint:#666;--border:#bbb}}body{{background:#fff}}.section{{box-shadow:none;break-inside:avoid}}.delta-focus-controls{{display:none}}.delta-canvas-scroll{{overflow:visible}}}}.delta-graph-heading{{flex-wrap:wrap}}.delta-node.operation-renamed rect{{stroke:var(--blue);stroke-dasharray:8 3;fill:rgba(48,83,110,.14)}}.isolated-anchor.operation-renamed{{border-left-color:var(--blue);border-style:dashed}}.delta-node.operation-retained rect{{stroke:#53656e;fill:#111a1f}}.delta-node.operation-unresolved rect{{stroke:var(--faint);stroke-dasharray:3 3;fill:rgba(111,125,131,.08)}}.isolated-anchor.operation-unresolved{{border-left-color:var(--faint);border-style:dashed}}.structural-container-header,.secondary-placement{{transition:opacity .16s ease,filter .16s ease}}.structural-container-header rect{{fill:#132027;stroke:#58707c;stroke-width:1.1}}.structural-container-header.operation-added rect{{stroke:var(--green);fill:rgba(54,118,87,.14)}}.structural-container-header.operation-modified rect{{stroke:var(--amber);fill:rgba(106,85,30,.13)}}.structural-container-header.operation-removed rect{{stroke:var(--red);stroke-dasharray:6 4;fill:rgba(112,43,48,.12)}}.structural-container-header.operation-unresolved rect{{stroke:var(--faint);stroke-dasharray:3 3}}.secondary-placement rect{{fill:rgba(48,83,110,.18);stroke:var(--blue);stroke-width:.8;stroke-dasharray:3 2}}.secondary-placement text{{fill:var(--blue);font-size:8px}}.delta-focus.no-visible-backbone{{border-style:dashed;color:var(--faint)}}.delta-focus-empty{{margin:12px 0 0;padding:9px 11px;border:1px dashed rgba(111,128,135,.3);border-radius:8px;color:var(--muted);font-size:10px}}
.delta-node-marker{{stroke-width:3;stroke-linecap:round}}
.delta-node.operation-added .delta-node-marker{{stroke:var(--green)}}
.delta-node.operation-modified .delta-node-marker{{stroke:var(--amber)}}
.delta-node.operation-removed .delta-node-marker{{stroke:var(--red)}}
.delta-node.operation-renamed .delta-node-marker{{stroke:var(--blue)}}
.delta-node.operation-retained .delta-node-marker,.delta-node.operation-unresolved .delta-node-marker{{stroke:var(--faint)}}
.delta-node.kind-function rect,.delta-node.kind-method rect,.delta-node.kind-variable rect,.delta-node.kind-import rect,.delta-node.kind-class rect{{fill:transparent;stroke:none}}
.delta-node.kind-function .delta-node-name,.delta-node.kind-method .delta-node-name{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:10px}}
.structural-container.kind-file,.structural-container.kind-class{{fill:transparent;stroke:none}}
.structural-container-header.kind-file rect,.structural-container-header.kind-class rect{{fill:transparent;stroke:none}}
.structural-container-divider{{stroke:rgba(111,128,135,.28);stroke-width:1}}
.structural-container-header.operation-added .structural-container-divider{{stroke:rgba(123,227,172,.55)}}
.structural-container-header.operation-modified .structural-container-divider{{stroke:rgba(231,202,124,.55)}}
.structural-container-header.operation-removed .structural-container-divider{{stroke:rgba(239,143,145,.55);stroke-dasharray:5 4}}
.structural-container-header.kind-class .delta-node-kind{{fill:var(--faint)}}
.relationship-inspector,.isolated-anchors{{margin-top:12px;border-top:1px solid rgba(111,128,135,.18);padding-top:10px}}
.relationship-inspector>summary,.isolated-anchors>summary{{cursor:pointer;color:var(--muted);font-size:10px}}
.standalone-explanation{{margin:8px 0 0;color:var(--faint);font-size:9px}}
.delta-edge[role="button"]{{cursor:pointer;outline:none}}
.delta-edge[role="button"]:focus path,.delta-edge.group-expanded path{{stroke-width:3}}
.relation-group-inspector{{display:grid;gap:7px;margin-top:10px}}
.relation-group-details{{border:1px solid rgba(111,128,135,.2);border-radius:8px;background:rgba(3,7,9,.28)}}
.relation-group-details>summary{{cursor:pointer;padding:8px 10px;color:var(--muted);font-size:9px}}
.relation-member-list{{padding:0 10px 8px}}
.relation-member{{display:grid;grid-template-columns:55px minmax(0,1fr) 20px minmax(0,1fr) 70px;gap:6px;align-items:center;padding:7px 0;border-top:1px solid rgba(111,128,135,.16);font-size:9px}}
.relation-member-node{{color:#b9dfff;text-decoration:none;overflow-wrap:anywhere}}
.relation-member-node.unavailable{{color:var(--faint)}}
.relation-member-node small{{display:block;font-size:7px}}
.relation-member-operation,.relation-member-kind{{color:var(--faint);text-transform:uppercase}}
.relation-member-arrow{{color:var(--muted);text-align:center}}
.eyebrow{{display:block;margin-bottom:4px;color:var(--green);font-size:9px;font-weight:760;text-transform:uppercase;letter-spacing:.09em}}
.section-intro{{margin:0 0 16px;color:var(--muted);font-size:10px}}
.brief-goals{{max-width:900px;margin-top:18px}}.brief-goals-heading{{margin-bottom:4px}}.brief-goals .context-row{{grid-template-columns:48px minmax(0,1fr);padding:10px 0;border-top:1px solid rgba(111,128,135,.16);border-bottom:0}}.brief-goals .context-copy{{color:#d2dade;font-size:15px}}.brief-goals .context-source{{grid-column:2}}
@media(max-width:600px){{.brief-goals .context-row{{grid-template-columns:1fr}}.brief-goals .context-source{{grid-column:1}}}}
.brief-context{{display:grid;gap:6px;margin-top:14px}}.brief-context .context{{margin:0;padding:0;border:0}}.brief-context .context>summary{{padding:7px 0;border-top:1px solid rgba(111,128,135,.16)}}
.architectural-chip{{cursor:pointer;outline:none}}
.architectural-chip rect{{fill:transparent;stroke:none}}
.architectural-chip text{{fill:#c9e8ff;font-size:7px;font-weight:760;text-anchor:middle;text-transform:uppercase}}
.architectural-chip:hover text,.architectural-chip:focus text,.architectural-chip.member-active text{{fill:var(--green)}}
.architectural-chip.layer-unclassified rect{{fill:transparent;stroke:none}}
.architectural-chip-html{{grid-column:1/-1;justify-self:start;border:1px solid rgba(159,205,240,.45);border-radius:999px;padding:2px 7px;background:rgba(48,83,110,.32);color:#c9e8ff;font:760 8px inherit;text-transform:uppercase;cursor:pointer}}
.architectural-chip-html.layer-unclassified{{border-style:dashed;color:var(--muted)}}
.member-muted{{opacity:.13}}.member-context{{opacity:.65}}.member-active{{opacity:1;filter:drop-shadow(0 0 5px rgba(123,227,172,.35))}}
.transformation-strip{{display:grid;grid-template-columns:minmax(0,1fr) 28px minmax(0,1.2fr) 28px minmax(0,1fr);gap:8px;align-items:stretch}}
.summary-stage{{min-width:0;padding:13px;border:1px solid rgba(111,128,135,.2);border-radius:10px;background:rgba(3,7,9,.2)}}
.summary-arrow{{display:grid;place-items:center;color:var(--faint);font-size:18px}}
.summary-claim{{display:grid;grid-template-columns:34px minmax(0,1fr) auto;gap:7px;align-items:center;width:100%;margin-top:7px;padding:8px;border:1px solid rgba(111,128,135,.18);border-radius:8px;background:rgba(16,24,28,.72);color:var(--text);font:inherit;text-align:left;cursor:pointer}}
.summary-claim:hover,.summary-claim:focus{{border-color:var(--green);outline:none}}.summary-claim>span{{color:var(--blue);font:700 8px ui-monospace,SFMono-Regular,Menlo,monospace}}.summary-claim>b{{overflow:hidden;font-size:9px;font-weight:620;text-overflow:ellipsis;white-space:nowrap}}.summary-claim>i{{font-style:normal}}
.summary-limits{{display:block;margin-top:12px;color:var(--faint);font-size:8px}}
.verification-accordion{{display:grid;gap:7px}}
.structural-graph-section .review-structural-graph{{margin:0;padding:0;border:0;background:transparent}}
.verification-group-label{{margin-top:8px;color:var(--faint);font-size:9px;font-weight:750;text-transform:uppercase;letter-spacing:.07em}}
.verification-item{{border:1px solid rgba(111,128,135,.2);border-radius:10px;overflow:hidden;background:rgba(3,7,9,.2)}}
.verification-item[open]{{border-color:rgba(123,227,172,.38)}}
.verification-item>summary{{display:grid;grid-template-columns:48px minmax(0,1fr) 105px;gap:10px;align-items:center;padding:12px;cursor:pointer;list-style:none}}
.verification-item>summary::-webkit-details-marker{{display:none}}
.verification-item>summary:hover{{background:rgba(54,118,87,.1)}}
.verification-id{{color:var(--green);font:760 10px ui-monospace,SFMono-Regular,Menlo,monospace}}
.verification-claim{{display:grid;gap:3px;min-width:0}}.verification-title{{font-size:11px;font-weight:620}}.verification-source{{color:var(--faint);font-size:8px}}
.status-pill{{display:inline-flex;justify-content:center;padding:4px 7px;border-radius:999px;font-size:8px;font-weight:750;text-transform:uppercase}}
.status-demonstrated{{background:rgba(54,118,87,.22);color:var(--green)}}.status-partial{{background:rgba(106,85,30,.2);color:var(--amber)}}
.status-contradicted{{background:rgba(112,43,48,.22);color:var(--red)}}.status-unverified,.status-not_assessed{{background:rgba(111,128,135,.14);color:var(--muted)}}
.verification-detail{{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);gap:9px;padding:0 12px 12px;border-top:1px solid rgba(111,128,135,.14)}}
.verification-detail>div{{min-width:0;margin-top:12px;padding:12px;border:1px solid rgba(111,128,135,.16);border-radius:9px}}
.verification-detail p{{font-size:10px}}
.verification-evidence{{display:grid;gap:3px;padding:7px 0;border-top:1px solid rgba(111,128,135,.12);font-size:9px}}
.evidence-kind{{color:var(--blue);font-size:8px;text-transform:uppercase}}
.assessment-reasons{{margin:0;padding-left:17px;color:var(--muted);font-size:9px}}.assessment-reasons li+li{{margin-top:7px}}
.verification-coverage,.display-boundary{{display:block;margin-top:10px;color:var(--faint);font-size:8px}}
.coverage-limits{{margin-top:14px;padding:0 12px;border:1px solid rgba(111,128,135,.2);border-radius:9px;background:rgba(3,7,9,.2)}}.coverage-limits>summary{{padding:10px 0;cursor:pointer;color:var(--amber);font-size:10px}}
@media(max-width:800px){{.transformation-strip{{grid-template-columns:1fr}}.summary-arrow{{transform:rotate(90deg)}}.verification-detail{{grid-template-columns:1fr}}.verification-item>summary{{grid-template-columns:42px minmax(0,1fr)}}.verification-item>summary .status-pill{{grid-column:2}}}}
</style></head><body><main class="shell">
<div class="topbar"><span class="brand-mark"></span>RepoDelta</div>
<section class="section"><div class="meta">{pr_link}<span>·</span><span>{escape(pr_state)}</span><span>·</span><span>{brief.overview.changed_file_count} changed files</span><span>·</span><span>{escape(ci_copy)}</span><span>·</span><span>{escape(llm_shadow_copy)}</span></div><h1>{escape(packet.title)}</h1>{primary_context}<span class="source-note">Source: {source_line}</span>{review_context}</section>
<section class="section structural-graph-section">{review_graph}</section>
{transformation_summary}
<section class="section verification-workspace"><h2>Verification</h2><p class="section-intro">Expand one R/G/T/CC subject to compare its authored claim, canonical observations, deterministic assessment, and structural coverage.</p>{verification_accordion}</section>
    {coverage_limits}
<div class="footer">RepoDelta · {escape(pr_label)} · Schema {escape(brief.schema_version)} · Generated by {escape(brief.generated_by)}</div>
</main><script>
const focusSurfaces = document.querySelectorAll(".review-structural-graph");
const clearMemberFocus = () => {{
  document.querySelectorAll(".member-muted, .member-context, .member-active").forEach((item) => {{
    item.classList.remove("member-muted", "member-context", "member-active");
  }});
}};
const activateFocus = (focus) => {{
  clearMemberFocus();
  document.querySelectorAll(".delta-focus").forEach((item) => {{
    item.classList.toggle("active", item.dataset.focusTarget === focus);
  }});
  focusSurfaces.forEach((surface) => {{
    let matched = false;
    surface.querySelectorAll("[data-focuses], [data-context-focuses]").forEach((item) => {{
      const direct = focus === "all" ||
        (item.dataset.focuses || "").split(/\\s+/).includes(focus);
      const contextual = focus !== "all" && !direct &&
        (item.dataset.contextFocuses || "").split(/\\s+/).includes(focus);
      if (focus !== "all" && (direct || contextual)) matched = true;
      item.classList.toggle("focus-muted", !direct && !contextual);
      item.classList.toggle("focus-context", contextual);
      item.classList.toggle("focus-active", focus !== "all" && direct);
    }});
    const empty = surface.querySelector(".delta-focus-empty");
    if (empty) {{
      const show = focus !== "all" && !matched;
      empty.hidden = !show;
      empty.textContent = show
        ? (document.querySelector(
            `.verification-item[data-verification-subject="${{focus}}"]`
          )?.dataset.structuralFocusMessage ||
          `${{focus}} has no structural evidence in the default change backbone.`)
        : "";
    }}
  }});
}};
const activateMembers = (trigger) => {{
  activateFocus("all");
  const nodeIds = new Set((trigger.dataset.memberNodeIds || "").split(/\\s+/).filter(Boolean));
  const contextNodeIds = new Set((trigger.dataset.contextNodeIds || "").split(/\\s+/).filter(Boolean));
  const groupIds = new Set((trigger.dataset.memberGroupIds || "").split(/\\s+/).filter(Boolean));
  const contextGroupIds = new Set((trigger.dataset.contextGroupIds || "").split(/\\s+/).filter(Boolean));
  document.querySelectorAll("[data-component-target]").forEach((item) => {{
    const active = item.dataset.componentTarget === trigger.dataset.componentTarget;
    item.classList.toggle("member-active", active);
    item.classList.toggle("member-muted", !active);
  }});
  document.querySelectorAll("[data-structural-node]").forEach((item) => {{
    const active = nodeIds.has(item.dataset.structuralNode);
    const contextual = !active && contextNodeIds.has(item.dataset.structuralNode);
    item.classList.toggle("member-active", active);
    item.classList.toggle("member-context", contextual);
    item.classList.toggle("member-muted", !active && !contextual);
  }});
  document.querySelectorAll("[data-group-target]").forEach((item) => {{
    const active = groupIds.has(item.dataset.groupTarget);
    const contextual = !active && contextGroupIds.has(item.dataset.groupTarget);
    item.classList.toggle("member-active", active);
    item.classList.toggle("member-context", contextual);
    item.classList.toggle("member-muted", !active && !contextual);
  }});
  const graph = document.querySelector(".review-structural-graph");
  if (graph) graph.scrollIntoView({{ behavior: "smooth", block: "center" }});
}};
document.querySelectorAll("[data-component-target]").forEach((item) => {{
  item.addEventListener("click", (event) => {{
    event.preventDefault();
    event.stopPropagation();
    activateMembers(item);
  }});
  item.addEventListener("keydown", (event) => {{
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    activateMembers(item);
  }});
}});
document.querySelectorAll(".review-structural-graph").forEach((graph) => {{
  const interaction = {{ expandedGroup: null }};
  graph.querySelectorAll(".delta-focus").forEach((button) => {{
    button.addEventListener("click", () =>
      activateFocus(button.dataset.focusTarget));
  }}
);
  const toggleGroup = (groupId) => {{
    interaction.expandedGroup =
      interaction.expandedGroup === groupId ? null : groupId;
    const inspector = graph.querySelector(".relationship-inspector");
    if (inspector && interaction.expandedGroup) inspector.open = true;
    graph.querySelectorAll("[data-group-target]").forEach((item) => {{
      const expanded = item.dataset.groupTarget === interaction.expandedGroup;
      item.classList.toggle("group-expanded", expanded);
      item.setAttribute("aria-expanded", String(expanded));
    }});
    graph.querySelectorAll(".relation-group-details").forEach((item) => {{
      item.open = item.dataset.groupId === interaction.expandedGroup;
    }});
  }};
  graph.querySelectorAll("[data-group-target]").forEach((group) => {{
    const toggle = () => toggleGroup(group.dataset.groupTarget);
    group.addEventListener("click", toggle);
    group.addEventListener("keydown", (event) => {{
      if (event.key === "Enter" || event.key === " ") {{
        event.preventDefault();
        toggle();
      }}
    }});
  }});
  graph.querySelectorAll(".relation-group-details").forEach((details) => {{
    details.addEventListener("toggle", () => {{
      if (details.open &&
        interaction.expandedGroup !== details.dataset.groupId) {{
        toggleGroup(details.dataset.groupId);
      }} else if (!details.open &&
        interaction.expandedGroup === details.dataset.groupId) {{
        toggleGroup(details.dataset.groupId);
      }}
    }});
  }});
}}
);
const verificationItems = document.querySelectorAll(
  ".verification-item[data-verification-subject]"
);
verificationItems.forEach((item) => {{
  item.addEventListener("toggle", () => {{
    if (!item.open) {{
      queueMicrotask(() => {{
        if (![...verificationItems].some((candidate) => candidate.open)) {{
          activateFocus("all");
        }}
      }});
      return;
    }}
    verificationItems.forEach((other) => {{
      if (other !== item) other.open = false;
    }});
    activateFocus(item.dataset.verificationSubject);
  }});
}});
activateFocus("all");
document.querySelectorAll("[data-summary-subject]").forEach((button) => {{
  button.addEventListener("click", () => {{
    const subject = button.dataset.summarySubject;
    const target = Array.from(document.querySelectorAll(
      ".verification-item[data-verification-subject]"
    )).find((item) => item.dataset.verificationSubject === subject);
    if (!target) return;
    target.open = true;
    target.scrollIntoView({{ behavior: "smooth", block: "center" }});
  }});
}});
</script></body></html>"""


def write_html(brief: ReviewBrief, output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(brief), encoding="utf-8")
    return path
