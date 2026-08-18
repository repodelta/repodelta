from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from html import escape
from pathlib import Path
import re
from urllib.parse import quote, urlparse, urlunparse

from repodelta.model.contracts import (
    ArchitecturalComponent,
    EvidenceCatalog,
    EvidenceItem,
    ReviewBrief,
    ReviewProjection,
    ReviewStatement,
    ReviewStructuralGraph,
    SourceRef,
    StructuralGraphEdge,
    StructuralGraphNode,
    StructuralGraphPlacement,
    StructuralFocusMembership,
    StructuralFocusOverlay,
    StructuralNavigationTarget,
    StructuralOverviewProjection,
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


@dataclass(frozen=True)
class _EvidencePathSegment:
    id: str
    focus_ids: tuple[str, ...]
    kind: str
    node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    membership_counts: tuple[tuple[str, int], ...]


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


def _focus_controls(workspace: object, visible_subject_ids: frozenset[str]) -> str:
    focus_buttons: dict[str, list[str]] = {
        "R": [], "G": [], "T": [], "CC": []
    }
    for entry in getattr(workspace, "matrix", ()):
        family = "CC" if entry.subject_id.startswith("CC") else entry.subject_id[:1]
        if family not in focus_buttons:
            continue
        focus_buttons[family].append(
            '<button class="delta-focus'
            + ("" if entry.subject_id in visible_subject_ids else " no-visible-backbone")
            + '" type="button" '
            f'data-focus-target="{escape(entry.subject_id, quote=True)}" '
            f'data-overview-visible="{str(entry.subject_id in visible_subject_ids).lower()}" '
            f'title="Inspect {escape(entry.subject_id, quote=True)}">'
            f'{escape(entry.subject_id)}</button>'
        )
    family_labels = {
        "R": "Requirements",
        "G": "Guardrails",
        "T": "Transformations",
        "CC": "Completion",
    }
    focus_families = "".join(
        '<div class="delta-focus-family">'
        f'<span>{escape(family_labels[family])}</span>'
        f'<div>{"".join(focus_buttons[family])}</div></div>'
        for family in ("R", "G", "T", "CC")
        if focus_buttons[family]
    )
    return (
        '<div class="delta-focus-controls" role="group" '
        'aria-label="Structural graph focus">'
        '<div class="delta-focus-primary">'
        '<button class="delta-focus active" type="button" '
        'data-focus-target="overview" data-overview-visible="true">Overview</button>'
        '</div>'
        f'<div class="delta-focus-families">{focus_families}</div></div>'
    )


def _review_graph(
    graph: ReviewStructuralGraph,
    projection: ReviewProjection,
    brief: ReviewBrief,
) -> str:
    workspace = projection.verification_workspace
    if not graph.nodes:
        controls = _focus_controls(workspace, frozenset())
        assessment_inspector = _focus_assessment_inspector(
            workspace,
            brief.evidence_catalog,
            getattr(brief.overview, "empty_review_message", ""),
        )
        return (
            '<div class="review-structural-graph">'
            '<div class="delta-graph-heading"><div>'
            '<h3>Structural delta overview</h3></div>'
            f'{controls}</div>'
            f'{assessment_inspector}'
            '<p class="delta-focus-empty" hidden></p>'
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
    node_focus: dict[
        str, list[tuple[str, StructuralFocusMembership]]
    ] = {}
    edge_focus: dict[str, list[str]] = {}
    relation_group_focus: dict[str, list[str]] = {}
    ownership_edge_focus: dict[str, list[str]] = {}
    placement_focus: dict[str, list[str]] = {}
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
                (focus_id, node)
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
            for focus_id, membership in node_focus.get(container.node_id, ())
            if membership.is_direct_mapping
        )
        contextual_focuses = tuple(
            dict.fromkeys(
                focus_id
                for focus_id in (
                    *(
                        item_focus_id
                        for item_focus_id, membership in node_focus.get(
                            container.node_id, ()
                        )
                        if not membership.is_direct_mapping
                    ),
                    *(
                        item_focus_id
                        for node_id in container.descendant_node_ids
                        for item_focus_id, _membership in node_focus.get(node_id, ())
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
            f'data-focus-memberships="{escape(_focus_membership_data(node_focus.get(container.node_id, ())), quote=True)}" '
            f'x="{container.x}" y="{container.y}" '
            f'width="{container.width}" height="{container.height}" rx="14">'
            f"<title>{escape(parent_node.review_symbol_id)} ownership container</title>"
            "</rect>"
        )
        header = (
            f'<g class="structural-container-header {kind_class} '
            f'operation-{escape(parent_node.delta)}" '
            f'data-structural-node="{escape(parent_node.id, quote=True)}" '
            f'data-focuses="{escape(" ".join(direct_focuses), quote=True)}" '
            f'data-context-focuses="{escape(" ".join(contextual_focuses), quote=True)}" '
            f'data-focus-memberships="{escape(_focus_membership_data(node_focus.get(container.node_id, ())), quote=True)}" '
            f'transform="translate({container.x + 12} {container.y + 12})">'
            f'<rect width="{container.width - 24}" height="42" rx="8"/>'
            f'<text class="delta-node-kind" x="11" y="15">'
            f'{escape(kind)} · {escape(parent_node.delta)}</text>'
            f'<text class="delta-node-name" x="11" y="32">'
            f'{escape(name_label or path_label)}</text>'
            f'{_architectural_chip(architectural_components[parent_node.id], container.width - 24)}'
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
            for focus_id, membership in node_focus.get(node.id, ())
            if membership.is_direct_mapping
        )
        contextual_focuses = " ".join(
            focus_id
            for focus_id, membership in node_focus.get(node.id, ())
            if not membership.is_direct_mapping
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
            f'data-focus-memberships="{escape(_focus_membership_data(node_focus.get(node.id, ())), quote=True)}" '
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
            f'{_architectural_chip(architectural_components[node.id], 210)}'
            f"<title>{escape(full_name)}</title></g>"
        )
        href = _structural_node_href(node, graph.navigation_targets)
        node_shapes.append(
            f'<a href="{escape(href, quote=True)}" target="_blank" '
            f'rel="noopener">{content}</a>'
            if href
            else content
        )

    isolated_nodes = tuple(
        node
        for node in backbone_nodes.values()
        if node.id not in connected_node_ids and node.delta != "retained"
    )
    isolated_rows = []
    for node in isolated_nodes:
        fact = _structural_display_fact(node, evidence)
        if fact.metadata.get("symbol_kind") == "file":
            continue
        sources = _sources(fact, brief)
        direct_focuses, contextual_focuses = _aggregate_node_focus(
            (node.id,), node_focus
        )
        focuses = ", ".join(
            dict.fromkeys((*direct_focuses, *contextual_focuses))
        )
        kind = str(fact.metadata.get("symbol_kind", "symbol")).replace("_", " ")
        isolated_rows.append(
            f'<div class="isolated-anchor operation-{escape(node.delta)}" '
            f'data-structural-node="{escape(node.id, quote=True)}" '
            f'data-focuses="{escape(" ".join(direct_focuses), quote=True)}" '
            f'data-context-focuses="{escape(" ".join(contextual_focuses), quote=True)}" '
            f'data-focus-memberships="{escape(_focus_membership_data(node_focus.get(node.id, ())), quote=True)}">'
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

    visible_focus_ids = {
        focus.subject_id
        for focus in projection.structural_overview.focuses
        if focus.direct_file_node_ids
        or focus.context_file_node_ids
        or focus.relation_ids
    }
    controls = _focus_controls(workspace, frozenset(visible_focus_ids))
    canvas = (
        '<div class="delta-canvas-scroll"><svg class="delta-canvas" '
        f'viewBox="0 0 {canvas_width} {canvas_height}" '
        f'data-original-view-box="0 0 {canvas_width} {canvas_height}" '
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
    file_overview = _file_structural_overview(
        overview=projection.structural_overview,
        backbone_nodes=backbone_nodes,
        evidence=evidence,
    )
    evidence_paths = _evidence_paths(
        graph=graph,
        backbone_nodes=backbone_nodes,
        backbone_edges=backbone_edges,
        placements=placements,
        evidence=evidence,
        architectural_components=architectural_components,
        workspace=workspace,
    )
    member_graph = _file_member_graph(
        graph=graph,
        backbone_nodes=backbone_nodes,
        backbone_edges=backbone_edges,
        backbone_relation_groups=backbone_relation_groups,
        placements=placements,
        evidence=evidence,
        architectural_components=architectural_components,
        node_focus=node_focus,
        edge_focus=edge_focus,
        relation_group_focus=relation_group_focus,
    )
    audit_graph = member_graph or f"{canvas}{relationship_inspector}"
    audit = (
        '<details class="structural-audit"><summary>Full structural audit · '
        f'{len(backbone_nodes)} symbols · {len(backbone_edges)} relations</summary>'
        '<p class="structural-audit-intro">Canonical members, exact relationships, '
        'ownership, unresolved context, and standalone changes.</p>'
        f'{audit_graph}{isolated}</details>'
        if audit_graph or isolated
        else ""
    )
    assessment_inspector = _focus_assessment_inspector(
        workspace,
        brief.evidence_catalog,
        getattr(brief.overview, "empty_review_message", ""),
    )
    return (
        '<div class="review-structural-graph">'
        '<div class="delta-graph-heading"><div>'
        '<h3>Structural delta overview</h3>'
        f'<div class="structural-coverage state-{escape(coverage_state)}">'
        f"{escape(coverage_copy)}</div>"
        f'<div class="subgraph-summary">{len(backbone_nodes)} backbone nodes · '
        f'{len(graph.nodes) - len(backbone_nodes)} support nodes · '
        f'{len(backbone_relation_groups)} backbone relation groups · '
        f'{len(backbone_edges)} canonical executable edges · '
        f'{len(placements)} structural placements · '
        f'{len(backbone_ownership_edges)} ownership deltas · '
        f'{len(isolated_nodes)} isolated changed anchors · '
        f'{len(graph.path_evidence_ids)} support refs</div></div>'
        f'{controls}</div>'
        f'{assessment_inspector}'
        '<p class="delta-focus-empty" hidden></p>'
        '<div class="unified-graph-stage">'
        f'{file_overview}{evidence_paths}</div>{audit}'
        "</div>"
    )


def _file_structural_overview(
    *,
    overview: StructuralOverviewProjection,
    backbone_nodes: dict[str, StructuralGraphNode],
    evidence: dict[str, EvidenceItem],
) -> str:
    """Render the canonical compact structural overview without re-projecting it."""

    facts = {
        node_id: _structural_display_fact(node, evidence)
        for node_id, node in backbone_nodes.items()
    }
    overview_files = overview.files_by_id()
    visible_files = {
        file_id: item
        for file_id, item in overview_files.items()
        if item.role != "retained_context"
    }
    if not visible_files:
        return (
            '<div class="file-graph-layer"><p class="file-overview-empty">'
            'No changed file-level structure is available. Retained context '
            'remains in the full structural audit.</p></div>'
        )
    file_node_ids = tuple(visible_files)
    members_by_file = {
        file_id: visible_files[file_id].member_node_ids for file_id in file_node_ids
    }

    alphabetic_files = tuple(sorted(
        file_node_ids,
        key=lambda item: _structural_standalone_name(facts[item]),
    ))
    verification_file_ids = {
        file_id
        for file_id in alphabetic_files
        if visible_files[file_id].lane == "verification"
    }
    relation_file_pairs = {
        (source_file, target_file)
        for relation in overview.relations
        for source_file in relation.source_file_node_ids
        for target_file in (relation.target_file_node_id,)
    }

    def topology_order(file_ids: set[str]) -> tuple[str, ...]:
        pairs = {
            (source_id, target_id)
            for source_id, target_id in relation_file_pairs
            if source_id in file_ids and target_id in file_ids
        }
        connected_ids = {
            node_id for pair in pairs for node_id in pair
        }
        outgoing: dict[str, set[str]] = {node_id: set() for node_id in file_ids}
        indegree = {node_id: 0 for node_id in file_ids}
        for source_id, target_id in pairs:
            if target_id in outgoing[source_id]:
                continue
            outgoing[source_id].add(target_id)
            indegree[target_id] += 1

        def sort_key(node_id: str) -> tuple[bool, str]:
            return (
                node_id not in connected_ids,
                _structural_standalone_name(facts[node_id]),
            )

        ready = sorted(
            (node_id for node_id, count in indegree.items() if count == 0),
            key=sort_key,
        )
        ordered: list[str] = []
        while ready:
            node_id = ready.pop(0)
            ordered.append(node_id)
            for target_id in sorted(outgoing[node_id], key=sort_key):
                indegree[target_id] -= 1
                if indegree[target_id] == 0:
                    ready.append(target_id)
                    ready.sort(key=sort_key)
        ordered.extend(sorted(file_ids - set(ordered), key=sort_key))
        return tuple(ordered)

    verification_files = topology_order(verification_file_ids)
    production_files = topology_order(
        set(file_node_ids) - verification_file_ids
    )
    ordered_files = (*production_files, *verification_files)
    cell_width, cell_height = 300, 142
    node_width, node_height = 250, 84
    columns = min(3, max(1, len(production_files)))
    canvas_width = max(600, columns * cell_width)
    positions: dict[str, tuple[int, int]] = {}
    production_rows = max(
        1,
        (len(production_files) + columns - 1) // columns,
    )
    for index, file_id in enumerate(production_files):
        positions[file_id] = (
            30 + (index % columns) * cell_width,
            45 + (index // columns) * cell_height,
        )
    verification_start = 55 + production_rows * cell_height
    verification_columns = min(2, max(1, len(verification_files)))
    verification_gap = 12
    verification_inner_width = canvas_width - 80
    verification_node_width = (
        verification_inner_width
        - verification_gap * (verification_columns - 1)
    ) / verification_columns
    verification_node_height = 42
    for index, file_id in enumerate(verification_files):
        column = index % verification_columns
        row = index // verification_columns
        positions[file_id] = (
            40 + column * (verification_node_width + verification_gap),
            verification_start + 46 + row * (verification_node_height + 8),
        )
    verification_rows = (
        (len(verification_files) + verification_columns - 1)
        // verification_columns
        if verification_files
        else 0
    )
    canvas_height = (
        65
        + production_rows * cell_height
        + (
            72 + verification_rows * (verification_node_height + 8)
            if verification_files
            else 0
        )
    )

    def file_size(file_id: str) -> tuple[float, float]:
        return (
            (verification_node_width, verification_node_height)
            if file_id in verification_file_ids
            else (node_width, node_height)
        )

    edge_shapes = []
    focuses = overview.focuses_by_subject_id()
    for relation in overview.relations:
        source_files = relation.source_file_node_ids
        target_file = relation.target_file_node_id
        operation = relation.operation
        group_ids = relation.relation_group_ids
        visual_source = (
            "__verification__"
            if all(source in verification_file_ids for source in source_files)
            and target_file not in verification_file_ids
            else source_files[0]
        )
        source_x, source_y = (
            (canvas_width / 2, verification_start + 8)
            if visual_source == "__verification__"
            else positions[visual_source]
        )
        target_x, target_y = positions[target_file]
        source_width, source_height = (
            (0, 0)
            if visual_source == "__verification__"
            else file_size(visual_source)
        )
        target_width, target_height = file_size(target_file)
        source_center = (
            source_x + source_width / 2,
            source_y + source_height / 2,
        )
        target_center = (
            target_x + target_width / 2,
            target_y + target_height / 2,
        )
        delta_x = target_center[0] - source_center[0]
        delta_y = target_center[1] - source_center[1]
        source_boundary_scale = min(
            source_width / 2 / abs(delta_x) if delta_x else float("inf"),
            source_height / 2 / abs(delta_y) if delta_y else float("inf"),
        )
        if visual_source == "__verification__":
            source_boundary_scale = 0
        target_boundary_scale = min(
            target_width / 2 / abs(delta_x) if delta_x else float("inf"),
            target_height / 2 / abs(delta_y) if delta_y else float("inf"),
        )
        x1 = source_center[0] + delta_x * source_boundary_scale
        y1 = source_center[1] + delta_y * source_boundary_scale
        x2 = target_center[0] - delta_x * target_boundary_scale
        y2 = target_center[1] - delta_y * target_boundary_scale
        mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2
        horizontal = abs(delta_y) < 1
        label_rect_y = (
            min(source_y, target_y) - 18
            if horizontal
            else mid_y - 25
        )
        label_text_y = label_rect_y + 12
        relation_title = " + ".join(relation.relations)
        exact_edge_count = len(relation.member_edge_ids)
        operation_label = "existing" if operation == "retained" else operation
        label = f"{operation_label} {relation_title}"
        if len(source_files) > 1 or exact_edge_count > 1:
            label += f" ×{exact_edge_count}"
        label_width = min(224, max(128, len(label) * 4.5 + 18))
        relation_focuses = tuple(
            focus.subject_id
            for focus in overview.focuses
            if relation.id in focus.relation_ids
        )
        edge_shapes.append(
            f'<g class="file-delta-edge operation-{escape(operation)}" '
            f'data-source-file="{escape(source_files[0], quote=True)}" '
            f'data-source-file-ids="{escape(" ".join(source_files), quote=True)}" '
            f'data-target-file="{escape(target_file, quote=True)}" '
            f'data-group-ids="{escape(" ".join(group_ids), quote=True)}" '
            f'data-overview-relation="{escape(relation.id, quote=True)}" '
            f'data-focuses="{escape(" ".join(relation_focuses), quote=True)}">'
            f'<title>{escape(relation_title)} · {escape(operation)}</title>'
            + (
                f'<circle class="file-edge-bus" cx="{x1}" cy="{y1}" r="3"/>'
                if visual_source == "__verification__"
                else ""
            )
            +
            f'<path d="M{x1} {y1} Q{mid_x} {mid_y - 28} {x2} {y2}" '
            f'marker-end="url(#file-arrow-{escape(operation)})"/>'
            f'<rect x="{mid_x - label_width / 2}" y="{label_rect_y}" '
            f'width="{label_width}" '
            'height="17" rx="4"/>'
            f'<text x="{mid_x}" y="{label_text_y}">{escape(label)}</text></g>'
        )

    file_shapes = []
    for file_id in ordered_files:
        file_node = backbone_nodes[file_id]
        file_fact = facts[file_id]
        member_ids = tuple(
            sorted(
                members_by_file[file_id],
                key=lambda item: (
                    str(facts[item].metadata.get("symbol_kind", "symbol")),
                    _structural_name(facts[item]),
                ),
            )
        )
        counts = Counter(
            str(facts[node_id].metadata.get("symbol_kind", "symbol"))
            for node_id in member_ids
        )
        count_copy = " · ".join(
            f"{count} {_structural_kind_count_label(kind, count)}"
            for kind, count in sorted(counts.items())
        ) or "No contained symbol was projected"
        direct_focuses = tuple(
            focus.subject_id
            for focus in overview.focuses
            if file_id in focus.direct_file_node_ids
        )
        context_focuses = tuple(
            focus.subject_id
            for focus in overview.focuses
            if file_id in focus.context_file_node_ids
            and focus.subject_id not in direct_focuses
        )
        file_name = _structural_standalone_name(file_fact)
        overview_file = visible_files[file_id]
        layer = overview_file.architectural_layer
        x, y = positions[file_id]
        width, height = file_size(file_id)
        is_verification = file_id in verification_file_ids
        is_retained_bridge = overview_file.role == "retained_bridge"
        file_shapes.append(
            '<g class="file-graph-node'
            + (" verification-row" if is_verification else "")
            + (" retained-bridge" if is_retained_bridge else "")
            + '" tabindex="0" role="button" '
            f'data-structural-node="{escape(file_id, quote=True)}" '
            f'data-file-node="{escape(file_id, quote=True)}" '
            f'data-focuses="{escape(" ".join(direct_focuses), quote=True)}" '
            f'data-context-focuses="{escape(" ".join(context_focuses), quote=True)}" '
            f'data-member-node-ids="{escape(" ".join((file_id, *member_ids)), quote=True)}" '
            f'data-context-node-ids="{escape(" ".join(overview_file.context_file_node_ids), quote=True)}" '
            f'data-member-group-ids="{escape(" ".join(overview_file.relation_group_ids), quote=True)}" '
            f'transform="translate({x} {y})">'
            f'<rect width="{width}" height="{height}" rx="{7 if is_verification else 11}"/>'
            + (
                f'<circle class="verification-change-dot" cx="13" cy="21" r="3"/>'
                f'<text class="file-node-name" x="23" y="24">{escape(_truncate_label(file_name, 27))}</text>'
                f'<text class="file-node-operation" x="{width - 13}" y="24" text-anchor="end">{escape(file_node.delta)}</text>'
                if is_verification
                else (
                    f'<text class="file-node-operation" x="13" y="19">{escape(file_node.delta)}</text>'
                    f'<text class="file-node-layer" x="{width - 13}" y="19">{escape(layer)}</text>'
                    f'<text class="file-node-name" x="13" y="43">{escape(_truncate_label(file_name, 39))}</text>'
                    f'<text class="file-node-counts" x="13" y="66">{escape("Existing path bridge" if is_retained_bridge else _truncate_label(count_copy, 48))}</text>'
                )
            )
            + f'<title>{escape(file_name)} · select related focused structure</title></g>'
        )

    lane_shapes = (
        '<text class="file-lane-label" x="30" y="25">Production change</text>'
        + (
            f'<line class="file-lane-divider" x1="20" y1="{verification_start + 3}" '
            f'x2="{canvas_width - 20}" y2="{verification_start + 3}"/>'
            f'<rect class="verification-lane-container" x="20" '
            f'y="{verification_start + 8}" width="{canvas_width - 40}" '
            f'height="{canvas_height - verification_start - 18}" rx="10"/>'
            f'<text class="file-lane-label verification" x="40" '
            f'y="{verification_start + 32}">Verification changes · '
            f'{len(verification_files)} '
            f'{"file" if len(verification_files) == 1 else "files"}</text>'
            if verification_files
            else ""
        )
    )
    retained_context = ""
    retained_context_files = tuple(
        item for item in overview.files if item.role == "retained_context"
    )
    if retained_context_files:
        context_chips = "".join(
            '<span class="retained-context-chip" '
            f'data-context-file="{escape(item.file_node_id, quote=True)}" '
            f'data-focuses="{escape(" ".join(focus.subject_id for focus in overview.focuses if item.file_node_id in focus.direct_file_node_ids), quote=True)}">'
            f'{escape(_structural_standalone_name(facts[item.file_node_id]))}'
            f'<small>{len(item.relation_group_ids)} boundary relation'
            f'{"s" if len(item.relation_group_ids) != 1 else ""}</small></span>'
            for item in sorted(
                retained_context_files,
                key=lambda value: _structural_standalone_name(
                    facts[value.file_node_id]
                ),
            )
        )
        retained_context = (
            '<details class="retained-boundary-context"><summary>'
            f'Existing context · {len(retained_context_files)} '
            f'{"file" if len(retained_context_files) == 1 else "files"}</summary>'
            '<p>Retained dependencies adjacent to this PR’s changed files. '
            'Exact relationships remain in the full structural audit.</p>'
            f'<div>{context_chips}</div></details>'
        )
    return (
        '<div class="file-graph-layer">'
        '<p class="file-overview-intro">Changed files and the retained bridge '
        'files required to keep their structural paths continuous. Other '
        'retained context stays outside the primary map.</p>'
        '<div class="delta-canvas-scroll"><svg class="file-delta-canvas" '
        f'viewBox="0 0 {canvas_width} {canvas_height}" role="img" '
        'aria-label="File-level structural delta graph"><defs>'
        '<marker id="file-arrow-added" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path fill="#7be3ac" d="M0,0 L0,6 L8,3 z"/></marker>'
        '<marker id="file-arrow-removed" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path fill="#ef8f91" d="M0,0 L0,6 L8,3 z"/></marker>'
        '<marker id="file-arrow-retained" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path fill="#71848d" d="M0,0 L0,6 L8,3 z"/></marker>'
        '</defs>'
        f'{lane_shapes}{"".join(edge_shapes)}{"".join(file_shapes)}</svg></div>'
        f'{retained_context}</div>'
    )


def _evidence_paths(
    *,
    graph: ReviewStructuralGraph,
    backbone_nodes: dict[str, StructuralGraphNode],
    backbone_edges: tuple[StructuralGraphEdge, ...],
    placements: tuple[StructuralGraphPlacement, ...],
    evidence: dict[str, EvidenceItem],
    architectural_components: dict[str, ArchitecturalComponent],
    workspace: object,
) -> str:
    """Render focus-owned exact relations as selectable structural classes."""

    if not getattr(workspace, "inspections", ()):  # no authored focus exists
        return ""
    facts = {
        node_id: _structural_display_fact(node, evidence)
        for node_id, node in backbone_nodes.items()
    }
    file_ids = {
        node_id
        for node_id, fact in facts.items()
        if fact.metadata.get("symbol_kind") == "file"
    }
    primary_ids = set(graph.primary_placement_ids)
    parent_by_child = {
        placement.child_node_id: placement.parent_node_id
        for placement in placements
        if placement.id in primary_ids
    }

    def owning_file(node_id: str) -> str | None:
        current = node_id
        visited: set[str] = set()
        while current not in visited:
            visited.add(current)
            if current in file_ids:
                return current
            current = parent_by_child.get(current, "")
            if not current:
                return None
        return None

    file_by_node = {
        node_id: file_id
        for node_id in backbone_nodes
        if (file_id := owning_file(node_id)) is not None
    }
    edge_by_id = {item.id: item for item in backbone_edges}
    group_ids_by_edge = {
        edge_id: group.id
        for group in graph.relation_groups
        if group.id in set(graph.backbone_relation_group_ids)
        for edge_id in group.member_edge_ids
    }
    segments: list[_EvidencePathSegment] = []

    def edge_kind(edge: StructuralGraphEdge) -> str:
        node_ids = (edge.source_node_id, edge.target_node_id)
        if any(backbone_nodes[node_id].delta == "unresolved" for node_id in node_ids):
            return "unresolved"
        if any(
            facts[node_id].classification == "test"
            or facts[node_id].profile in {"test", "verification"}
            or architectural_components.get(node_id) is not None
            and architectural_components[node_id].layer == "verification"
            for node_id in node_ids
        ):
            return "verification"
        if edge.relation not in {"calls", "instantiates"}:
            return "context"
        return "change"

    for inspection in workspace.inspections:
        focus_id = inspection.subject_id
        overlay = inspection.structural_overlay
        selected_edges = tuple(
            edge_by_id[edge_id]
            for edge_id in overlay.edge_ids
            if edge_id in edge_by_id
        )
        edges_by_kind: dict[str, list[StructuralGraphEdge]] = {}
        for edge in selected_edges:
            edges_by_kind.setdefault(edge_kind(edge), []).append(edge)

        covered_node_ids = {
            node_id
            for edge in selected_edges
            for node_id in (edge.source_node_id, edge.target_node_id)
        }
        standalone_nodes_by_kind: dict[str, list[str]] = {}
        for focus_node in overlay.nodes:
            if (
                focus_node.node_id not in backbone_nodes
                or focus_node.node_id in covered_node_ids
                or focus_node.structural_role in {
                    "connector",
                    "relation_endpoint",
                    "placement_ancestor",
                    "ownership_ancestor",
                }
            ):
                continue
            node_id = focus_node.node_id
            node = backbone_nodes[node_id]
            fact = facts[node_id]
            component = architectural_components.get(node_id)
            if node.delta == "unresolved":
                kind = "unresolved"
            elif (
                fact.classification == "test"
                or fact.profile in {"test", "verification"}
                or component is not None and component.layer == "verification"
            ):
                kind = "verification"
            else:
                kind = "context"
            standalone_nodes_by_kind.setdefault(kind, []).append(node_id)

        for kind in ("change", "verification", "context", "unresolved"):
            selected_kind_edges = tuple(edges_by_kind.get(kind, ()))
            node_ids = tuple(dict.fromkeys((
                *(
                    node_id
                    for edge in selected_kind_edges
                    for node_id in (edge.source_node_id, edge.target_node_id)
                ),
                *standalone_nodes_by_kind.get(kind, ()),
            )))
            if not node_ids:
                continue
            segment_node_ids = set(node_ids)
            segment_edge_ids = {
                edge.id for edge in selected_kind_edges
            }
            membership_counts = Counter(
                membership.membership_class
                for membership in overlay.memberships
                if (
                    membership.member_kind == "node"
                    and membership.member_id in segment_node_ids
                )
                or (
                    membership.member_kind == "edge"
                    and membership.member_id in segment_edge_ids
                )
            )
            segments.append(
                _EvidencePathSegment(
                    id=f"{focus_id}:{kind}",
                    focus_ids=(focus_id,),
                    kind=kind,
                    node_ids=node_ids,
                    edge_ids=tuple(edge.id for edge in selected_kind_edges),
                    membership_counts=tuple(
                        (membership_class, membership_counts[membership_class])
                        for membership_class in (
                            "asserted",
                            "matched",
                            "suggested",
                            "context",
                            "unresolved",
                        )
                        if membership_counts[membership_class]
                    ),
                )
            )

    if not segments:
        return (
            '<section class="evidence-paths" hidden>'
            '<p class="evidence-path-empty">No exact focused structure '
            'is available. Use the full audit for collected facts.'
            '</p></section>'
        )

    def node_label(node_id: str) -> str:
        fact = facts[node_id]
        _path, separator, name = _structural_name(fact).partition(" · ")
        return _structural_symbol_label(fact, name if separator else _path)

    def step_html(node_id: str) -> str:
        node = backbone_nodes[node_id]
        label = escape(node_label(node_id))
        file_id = file_by_node.get(node_id)
        file_label = (
            _structural_standalone_name(facts[file_id])
            if file_id is not None
            else str(facts[node_id].metadata.get("path", "Unowned structural node"))
        )
        href = _structural_node_href(node, graph.navigation_targets)
        symbol = (
            f'<a href="{escape(href, quote=True)}" target="_blank" '
            f'rel="noopener">{label}</a>'
            if href
            else f"<b>{label}</b>"
        )
        return (
            '<span class="path-trace-step" '
            f'data-structural-node="{escape(node_id, quote=True)}">'
            f'{symbol}<small>{escape(file_label)}</small></span>'
        )

    def trace_html(segment: _EvidencePathSegment, *, reverse: bool) -> str:
        oriented: list[tuple[StructuralGraphEdge, str, str]] = []
        for edge_id in segment.edge_ids:
            edge = edge_by_id[edge_id]
            source_id, target_id = (
                (edge.target_node_id, edge.source_node_id)
                if reverse
                else (edge.source_node_id, edge.target_node_id)
            )
            oriented.append((edge, source_id, target_id))
        outgoing: dict[
            str, list[tuple[StructuralGraphEdge, str, str]]
        ] = {}
        target_ids: set[str] = set()
        for item in oriented:
            outgoing.setdefault(item[1], []).append(item)
            target_ids.add(item[2])
        for values in outgoing.values():
            values.sort(
                key=lambda item: (
                    item[0].relation,
                    _structural_name(facts[item[2]]),
                )
            )
        roots = sorted(
            (node_id for node_id in outgoing if node_id not in target_ids),
            key=lambda node_id: _structural_name(facts[node_id]),
        )
        if not roots:
            roots = sorted(
                outgoing,
                key=lambda node_id: _structural_name(facts[node_id]),
            )
        rendered_edges: set[str] = set()
        expanded_nodes: set[str] = set()

        def render_tree(node_id: str, trail: frozenset[str]) -> str:
            expanded_nodes.add(node_id)
            children = []
            for edge, _source_id, target_id in outgoing.get(node_id, ()):
                if edge.id in rendered_edges:
                    continue
                rendered_edges.add(edge.id)
                if target_id in trail:
                    target = (
                        '<span class="path-tree-reference">'
                        f'↳ {escape(node_label(target_id))}</span>'
                    )
                else:
                    target = render_tree(target_id, trail | {node_id})
                children.append(
                    '<li><span class="path-tree-relation">'
                    f'{escape(edge.relation)} · {escape(edge.operation)} '
                    '<b aria-hidden="true">→</b></span>'
                    f'{target}</li>'
                )
            return (
                '<div class="path-tree-node">'
                f'{step_html(node_id)}'
                + (
                    f'<ul>{"".join(children)}</ul>'
                    if children
                    else ""
                )
                + '</div>'
            )

        forest = [render_tree(root, frozenset()) for root in roots]
        for edge, source_id, _target_id in oriented:
            if edge.id not in rendered_edges:
                forest.append(render_tree(source_id, frozenset()))
        for node_id in segment.node_ids:
            if node_id not in expanded_nodes:
                forest.append(render_tree(node_id, frozenset()))
        direction = "reverse" if reverse else "forward"
        return (
            f'<div class="path-trace-order" data-path-direction="{direction}"'
            + (" hidden" if reverse else "")
            + f'><div class="path-tree-forest">{"".join(forest)}</div></div>'
        )

    labels = {
        "change": "Runtime change",
        "verification": "Verification",
        "context": "Structural context",
        "unresolved": "Unresolved context",
    }
    membership_labels = {
        "asserted": "Asserted",
        "matched": "Matched",
        "suggested": "Suggested",
        "context": "Context",
        "unresolved": "Unresolved",
    }
    rows = []
    traces = []
    for segment in segments:
        file_node_ids = tuple(dict.fromkeys(
            file_id
            for node_id in segment.node_ids
            if (file_id := file_by_node.get(node_id)) is not None
        ))
        group_ids = tuple(dict.fromkeys(
            group_ids_by_edge[edge_id]
            for edge_id in segment.edge_ids
            if edge_id in group_ids_by_edge
        ))
        selected_edges = tuple(edge_by_id[edge_id] for edge_id in segment.edge_ids)
        target_node_ids = {edge.target_node_id for edge in selected_edges}
        root_node_ids = tuple(dict.fromkeys(
            edge.source_node_id
            for edge in selected_edges
            if edge.source_node_id not in target_node_ids
        )) or tuple(dict.fromkeys(
            edge.source_node_id for edge in selected_edges
        ))
        if not root_node_ids:
            root_node_ids = segment.node_ids[:1]
        root_labels = [node_label(node_id) for node_id in root_node_ids[:2]]
        summary_parts = []
        for index, label in enumerate(root_labels):
            summary_parts.append(f"<code>{escape(label)}</code>")
            if index < len(root_labels) - 1:
                summary_parts.append(
                    '<span class="evidence-path-plus">+</span>'
                )
        if segment.edge_ids:
            summary_parts.append('<span class="evidence-path-arrow">→</span>')
            summary_parts.append('<code>…</code>')
        membership_chips = "".join(
            '<span class="focus-membership-chip '
            f'membership-{escape(membership_class)}">'
            f'{escape(membership_labels[membership_class])} · {count}</span>'
            for membership_class, count in segment.membership_counts
        )
        rows.append(
            '<button class="evidence-path-row" type="button" '
            f'data-path-id="{escape(segment.id, quote=True)}" '
            f'data-path-kind="{escape(segment.kind, quote=True)}" '
            f'data-membership-classes="{escape(" ".join(item[0] for item in segment.membership_counts), quote=True)}" '
            f'data-focuses="{escape(" ".join(segment.focus_ids), quote=True)}" '
            f'data-file-node-ids="{escape(" ".join(file_node_ids), quote=True)}" '
            f'data-group-ids="{escape(" ".join(group_ids), quote=True)}" '
            'aria-pressed="false">'
            f'<span class="evidence-path-kind">{labels[segment.kind]}</span>'
            f'<span class="evidence-path-main">{"".join(summary_parts)}'
            f'<span class="focus-membership-chips">{membership_chips}</span></span>'
            '<span class="evidence-path-action">Inspect</span></button>'
        )
        relations = tuple(edge_by_id[edge_id].relation for edge_id in segment.edge_ids)
        direction_mode = (
            "calls"
            if relations and all(item in {"calls", "instantiates"} for item in relations)
            else "path"
        )
        traces.append(
            '<div class="evidence-path-trace" '
            f'data-path-trace="{escape(segment.id, quote=True)}" '
            f'data-direction-mode="{direction_mode}" hidden>'
            f'{trace_html(segment, reverse=False)}'
            f'{trace_html(segment, reverse=True)}</div>'
        )

    return (
        '<section class="evidence-paths" hidden>'
        '<div class="evidence-path-heading"><div><h4>Focused structure</h4>'
        '<p>Select one evidence class. Runtime, verification, context, and '
        'unresolved structure remain visibly separate.</p></div></div>'
        f'<div class="evidence-path-list">{"".join(rows)}</div>'
        '<div class="evidence-path-inspector" hidden>'
        '<div class="evidence-path-inspector-heading">'
        '<b>Selected structure</b><div class="path-direction-controls" '
        'role="group" aria-label="Path direction">'
        '<button type="button" data-path-direction-target="forward" '
        'aria-pressed="true">Callees</button>'
        '<button type="button" data-path-direction-target="reverse" '
        'aria-pressed="false">Callers</button></div></div>'
        f'{"".join(traces)}</div>'
        '<p class="evidence-path-empty" hidden>No exact focused structure '
        'is available. Use the full audit for collected facts.'
        '</p></section>'
    )


def _aggregate_node_focus(
    node_ids: tuple[str, ...],
    node_focus: dict[
        str, list[tuple[str, StructuralFocusMembership]]
    ],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    direct = {
        focus_id
        for node_id in node_ids
        for focus_id, membership in node_focus.get(node_id, ())
        if membership.is_direct_mapping
    }
    contextual = {
        focus_id
        for node_id in node_ids
        for focus_id, membership in node_focus.get(node_id, ())
        if not membership.is_direct_mapping and focus_id not in direct
    }
    return tuple(sorted(direct)), tuple(sorted(contextual))


def _focus_membership_data(
    values: tuple[tuple[str, StructuralFocusMembership], ...]
    | list[tuple[str, StructuralFocusMembership]],
) -> str:
    return " ".join(
        f"{focus_id}:{membership.membership_class}"
        for focus_id, membership in values
    )


def _structural_kind_count_label(kind: str, count: int) -> str:
    if count == 1:
        return kind
    return {
        "class": "classes",
        "property": "properties",
    }.get(kind, f"{kind}s")


def _file_member_graph(
    *,
    graph: ReviewStructuralGraph,
    backbone_nodes: dict[str, StructuralGraphNode],
    backbone_edges: tuple[StructuralGraphEdge, ...],
    backbone_relation_groups: tuple[StructuralRelationGroup, ...],
    placements: tuple[StructuralGraphPlacement, ...],
    evidence: dict[str, EvidenceItem],
    architectural_components: dict[str, ArchitecturalComponent],
    node_focus: dict[
        str, list[tuple[str, StructuralFocusMembership]]
    ],
    edge_focus: dict[str, list[str]],
    relation_group_focus: dict[str, list[str]],
) -> str:
    """Render canonical detail as readable file lanes rather than nested boxes."""

    facts = {
        node_id: _structural_display_fact(node, evidence)
        for node_id, node in backbone_nodes.items()
    }
    file_ids = {
        node_id
        for node_id, fact in facts.items()
        if fact.metadata.get("symbol_kind") == "file"
    }
    if not file_ids:
        return ""
    primary_ids = set(graph.primary_placement_ids)
    parent_by_child = {
        placement.child_node_id: placement.parent_node_id
        for placement in placements
        if placement.id in primary_ids
    }

    def owning_file(node_id: str) -> str | None:
        current = node_id
        visited: set[str] = set()
        while current not in visited:
            visited.add(current)
            if current in file_ids:
                return current
            current = parent_by_child.get(current, "")
            if not current:
                return None
        return None

    file_by_node = {
        node_id: file_id
        for node_id in backbone_nodes
        if (file_id := owning_file(node_id)) is not None
    }
    members_by_file: dict[str, list[str]] = {file_id: [] for file_id in file_ids}
    for node_id, file_id in file_by_node.items():
        if node_id != file_id:
            members_by_file[file_id].append(node_id)

    group_by_edge_id = {
        edge_id: group
        for group in backbone_relation_groups
        for edge_id in group.member_edge_ids
    }
    ungrouped_edge_ids = sorted(
        edge.id for edge in backbone_edges if edge.id not in group_by_edge_id
    )
    if ungrouped_edge_ids:
        raise ValueError(
            "file member graph requires one relation group for every backbone "
            f'exact edge: {", ".join(ungrouped_edge_ids)}'
        )

    def edge_focuses(edge: StructuralGraphEdge) -> tuple[str, ...]:
        group = group_by_edge_id[edge.id]
        return tuple(dict.fromkeys((
            *edge_focus.get(edge.id, ()),
            *relation_group_focus.get(group.id, ()),
        )))

    outgoing: dict[str, list[StructuralGraphEdge]] = {}
    edge_focus_by_node: dict[str, list[str]] = {}
    relation_endpoint_ids: set[str] = set()
    for edge in backbone_edges:
        outgoing.setdefault(edge.source_node_id, []).append(edge)
        relation_endpoint_ids.update((edge.source_node_id, edge.target_node_id))
        for node_id in (edge.source_node_id, edge.target_node_id):
            edge_focus_by_node.setdefault(node_id, []).extend(
                edge_focuses(edge)
            )
    navigation_targets = {item.id: item for item in graph.navigation_targets}

    def target_presentation(
        edge: StructuralGraphEdge,
        source_file_id: str,
    ) -> tuple[str, str, str]:
        target = facts[edge.target_node_id]
        _target_path, target_separator, raw_target_name = (
            _structural_name(target).partition(" · ")
        )
        target_name = raw_target_name if target_separator else _target_path
        target_label = _structural_symbol_label(target, target_name)
        target_file_id = file_by_node.get(edge.target_node_id)
        target_file_label = (
            _structural_standalone_name(facts[target_file_id])
            if target_file_id
            else str(target.metadata.get("path", "external"))
        )
        file_badge = (
            "this file"
            if target_file_id == source_file_id
            else target_file_label.rsplit("/", 1)[-1]
        )
        navigation = navigation_targets.get(edge.target_navigation_target_id)
        target_html = (
            f'<a class="relation-target-symbol" '
            f'href="{escape(navigation.url, quote=True)}" target="_blank" '
            f'rel="noopener">{escape(target_label)}</a>'
            if navigation is not None
            and navigation.state == "available"
            and navigation.url
            else f'<b class="relation-target-symbol">{escape(target_label)}</b>'
        )
        return file_badge, target_file_label, target_html

    def render_member_relation(
        edge: StructuralGraphEdge,
        source_file_id: str,
    ) -> str:
        file_badge, target_file_label, target_html = target_presentation(
            edge, source_file_id
        )
        focuses = edge_focuses(edge)
        operation_symbol = {
            "added": "+",
            "removed": "−",
            "retained": "=",
        }[edge.operation]
        return (
            '<div class="member-relation" tabindex="0" '
            f'data-edge-id="{escape(edge.id, quote=True)}" '
            f'data-source-node="{escape(edge.source_node_id, quote=True)}" '
            f'data-target-node="{escape(edge.target_node_id, quote=True)}" '
            f'data-relation-group="{escape(group_by_edge_id[edge.id].id, quote=True)}" '
            f'data-focuses="{escape(" ".join(focuses), quote=True)}" '
            f'title="{len(edge.path_evidence_ids)} support references">'
            f'<span class="relation-kind">{escape(edge.relation)}</span>'
            f'<span class="relation-operation operation-{escape(edge.operation)}">'
            f'{operation_symbol}</span>'
            f'<span class="relation-target-file" title="{escape(target_file_label, quote=True)}">'
            f'{escape(file_badge)}</span>'
            f'<span class="relation-arrow">→</span>{target_html}</div>'
        )

    def render_file_relations(file_id: str) -> str:
        file_edges = tuple(outgoing.get(file_id, ()))
        if not file_edges:
            return ""
        grouped: dict[tuple[str, str, str], list[StructuralGraphEdge]] = {}
        for edge in file_edges:
            target_file_id = file_by_node.get(edge.target_node_id)
            target_file = (
                _structural_standalone_name(facts[target_file_id])
                if target_file_id
                else str(facts[edge.target_node_id].metadata.get("path", "external"))
            )
            grouped.setdefault(
                (edge.relation, edge.operation, target_file), []
            ).append(edge)
        rows = []
        for (relation, operation, target_file), grouped_edges in sorted(
            grouped.items()
        ):
            operation_symbol = {
                "added": "+",
                "removed": "−",
                "retained": "=",
            }[operation]
            focuses = tuple(dict.fromkeys(
                focus_id
                for edge in grouped_edges
                for focus_id in edge_focuses(edge)
            ))
            exact_targets = "".join(
                f'<li class="file-relation-target" '
                f'data-edge-id="{escape(edge.id, quote=True)}" '
                f'data-source-node="{escape(edge.source_node_id, quote=True)}" '
                f'data-target-node="{escape(edge.target_node_id, quote=True)}">'
                + target_presentation(edge, file_id)[2]
                + '</li>'
                for edge in grouped_edges
            )
            rows.append(
                '<details class="file-relation-group" '
                f'data-focuses="{escape(" ".join(focuses), quote=True)}">'
                '<summary>'
                f'<span class="relation-kind">{escape(relation)}</span>'
                f'<span class="relation-operation operation-{escape(operation)}">'
                f'{operation_symbol}</span>'
                f'<span class="relation-target-file" title="{escape(target_file, quote=True)}">'
                f'{escape(target_file.rsplit("/", 1)[-1])}</span>'
                f'<b>{len(grouped_edges)} exact target'
                f'{"s" if len(grouped_edges) != 1 else ""}</b></summary>'
                f'<ul>{exact_targets}</ul></details>'
            )
        return (
            '<div class="file-relations"><span>File relationships</span>'
            + "".join(rows)
            + "</div>"
        )

    panels = []
    for file_id in sorted(
        file_ids,
        key=lambda item: _structural_standalone_name(facts[item]),
    ):
        file_member_ids = set(members_by_file[file_id])
        children_by_parent: dict[str, list[str]] = {}
        for child_id in file_member_ids:
            children_by_parent.setdefault(
                parent_by_child.get(child_id, file_id), []
            ).append(child_id)
        member_ids: list[str] = []
        member_depth: dict[str, int] = {}

        def append_children(parent_id: str, depth: int) -> None:
            for child_id in sorted(
                children_by_parent.get(parent_id, ()),
                key=lambda item: _structural_name(facts[item]),
            ):
                if child_id in member_depth:
                    continue
                member_depth[child_id] = depth
                member_ids.append(child_id)
                append_children(child_id, depth + 1)

        append_children(file_id, 0)
        for member_id in sorted(
            file_member_ids - set(member_ids),
            key=lambda item: _structural_name(facts[item]),
        ):
            member_depth[member_id] = 0
            member_ids.append(member_id)
        node_direct_focuses, context_focuses = _aggregate_node_focus(
            (file_id, *member_ids), node_focus
        )
        direct_focuses = node_direct_focuses
        context_focuses = tuple(dict.fromkeys((
            *context_focuses,
            *(
                focus_id
                for node_id in (file_id, *member_ids)
                for focus_id in edge_focus_by_node.get(node_id, ())
                if focus_id not in node_direct_focuses
            ),
        )))
        rows = []
        for node_id in member_ids:
            node = backbone_nodes[node_id]
            fact = facts[node_id]
            kind = str(fact.metadata.get("symbol_kind", "symbol"))
            _path, separator, raw_name = _structural_name(fact).partition(" · ")
            name = raw_name if separator else _path
            label = _structural_symbol_label(fact, name)
            parent_id = parent_by_child.get(node_id)
            parent_label = ""
            if parent_id and parent_id != file_id and parent_id in facts:
                if "::" in name:
                    name = name.rsplit("::", 1)[-1]
                    label = _structural_symbol_label(fact, name)
                _parent_path, parent_separator, raw_parent_name = (
                    _structural_name(facts[parent_id]).partition(" · ")
                )
                parent_name = (
                    raw_parent_name if parent_separator else _parent_path
                )
                if "::" in parent_name:
                    parent_name = parent_name.rsplit("::", 1)[-1]
                parent_label = _structural_symbol_label(
                    facts[parent_id], parent_name
                )
            node_direct, contextual = _aggregate_node_focus(
                (node_id,), node_focus
            )
            direct = node_direct
            contextual = tuple(dict.fromkeys((
                *contextual,
                *(
                    focus_id
                    for focus_id in edge_focus_by_node.get(node_id, ())
                    if focus_id not in node_direct
                ),
            )))
            relations = "".join(
                render_member_relation(edge, file_id)
                for edge in outgoing.get(node_id, ())
            )
            node_href = _structural_node_href(node, graph.navigation_targets)
            node_label = (
                f'<a class="member-node-link" href="{escape(node_href, quote=True)}" '
                f'target="_blank" rel="noopener">{escape(label)}</a>'
                if node_href
                else f'<b>{escape(label)}</b>'
            )
            inherited_operation = node.delta == backbone_nodes[file_id].delta
            operation = (
                '<span class="member-operation inherited" aria-hidden="true"></span>'
                if inherited_operation
                else (
                    f'<span class="member-operation operation-{escape(node.delta)}">'
                    f'{escape(node.delta)}</span>'
                )
            )
            nested = bool(parent_label)
            aria_label = (
                f'{label}, {kind}, nested in {parent_label}'
                if nested
                else f'{label}, {kind}'
            )
            rows.append(
                '<div class="file-member-line'
                f'{" is-nested" if nested else ""}" '
                f'style="--member-depth:{min(member_depth[node_id], 3)}" '
                f'data-structural-node="{escape(node_id, quote=True)}" '
                f'data-parent-node="{escape(parent_id or "", quote=True)}" '
                f'data-focuses="{escape(" ".join(direct), quote=True)}" '
                f'data-context-focuses="{escape(" ".join(contextual), quote=True)}" '
                f'data-focus-memberships="{escape(_focus_membership_data(node_focus.get(node_id, ())), quote=True)}" '
                f'aria-label="{escape(aria_label, quote=True)}">'
                '<div class="member-line-main">'
                f'{operation}{node_label}'
                f'<small>{escape(kind.replace("_", " "))}</small>'
                f'</div>{relations}</div>'
            )
        panel_node_ids = {file_id, *member_ids}
        isolated_file = not bool(panel_node_ids & relation_endpoint_ids)
        file_node = backbone_nodes[file_id]
        file_href = _structural_node_href(file_node, graph.navigation_targets)
        file_label = escape(_structural_standalone_name(facts[file_id]))
        file_heading = (
            f'<a class="file-node-link" href="{escape(file_href, quote=True)}" '
            f'target="_blank" rel="noopener">{file_label}</a>'
            if file_href
            else f'<b>{file_label}</b>'
        )
        component = architectural_components[file_id]
        file_relations = render_file_relations(file_id)
        panels.append(
            '<section class="file-member-panel" '
            f'data-structural-node="{escape(file_id, quote=True)}" '
            f'data-focuses="{escape(" ".join(direct_focuses), quote=True)}" '
            f'data-context-focuses="{escape(" ".join(context_focuses), quote=True)}" '
            f'data-focus-memberships="{escape(_focus_membership_data(tuple(item for node_id in (file_id, *member_ids) for item in node_focus.get(node_id, ()))), quote=True)}">'
            '<header><div class="file-header-meta"><span>file · '
            f'{escape(backbone_nodes[file_id].delta)}'
            f'{" · isolated" if isolated_file else ""}</span>'
            f'{_architectural_chip_html(component)}</div>'
            f'{file_heading}</header>{file_relations}'
            f'<div class="file-member-lines">{"".join(rows)}</div></section>'
        )
    return '<div class="file-member-graph">' + "".join(panels) + "</div>"


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



def _focus_assessment_inspector(
    workspace: object,
    evidence_catalog: EvidenceCatalog,
    empty_review_message: str = "",
) -> str:
    """Render canonical verification detail inside the structural investigation."""
    if not getattr(workspace, "matrix", ()):
        return ""
    if not hasattr(workspace, "inspections_by_subject_id"):
        return ""
    evidence = evidence_catalog.by_id()
    inspections = workspace.inspections_by_subject_id()
    rows = []
    for entry in workspace.matrix:
        inspection = inspections[entry.subject_id]
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
        exceptional_reasons = tuple(
            item.kind.replace("_", " ")
            for item in inspection.assessment_reasons
            if entry.status != "demonstrated"
        )
        exception_chips = "".join(
            f'<span>{escape(item)}</span>' for item in dict.fromkeys(exceptional_reasons)
        )
        if inspection.contradicting_evidence_ids:
            exception_chips += '<span>contradicting evidence</span>'
        if not observed:
            exception_chips += '<span>no associated evidence</span>'
        if inspection.structural_disposition.state != "projected":
            exception_chips += (
                f'<span>{escape(_structural_focus_label(inspection.structural_disposition.state))}</span>'
            )
        membership_summary = _focus_membership_summary(
            inspection.structural_overlay
        )
        rows.append(
            '<article class="focus-assessment" hidden '
            f'data-verification-subject="{escape(entry.subject_id, quote=True)}"'
            f' data-structural-focus-message="{escape(focus_empty_copy, quote=True)}"'
            '><div class="focus-assessment-heading">'
            '<span class="focus-assessment-identity">'
            f'<b>{escape(entry.subject_id)}</b>'
            f'<span>{escape(entry.text)}</span>'
            + (
                f'<small>Source: {source}</small>'
                if source
                else ""
            )
            + '</span>'
            f'<span class="status-pill status-{escape(entry.status)}">'
            f'{escape(entry.status.replace("_", " "))}</span></div>'
            f'{membership_summary}'
            + (
                f'<div class="focus-exceptions" aria-label="Visible review exceptions">{exception_chips}</div>'
                if exception_chips
                else ""
            )
            + '<details class="focus-assessment-detail"><summary>Assessment &amp; evidence'
            f'<span>{len(inspection.supporting_evidence_ids)} supporting · '
            f'{escape(contradiction_copy)} · {escape(graph_copy)}</span></summary>'
            '<div class="verification-detail">'
            '<div><span class="projection-heading">Canonical observations</span>'
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
            f' · {escape(graph_copy)}</span></div></div></details></article>'
        )
    content = "".join(rows)
    return (
        '<section class="focus-assessment-inspector" hidden '
        'aria-live="polite"><h4>Assessment &amp; evidence</h4>'
        + (
            content
            if content
            else f'<p class="empty-state">{escape(empty_review_message or "No verification subject is available.")}</p>'
        )
        + "</section>"
    )


def _focus_membership_summary(overlay: StructuralFocusOverlay) -> str:
    labels = {
        "asserted": "Asserted mapping",
        "matched": "Deterministic match",
        "suggested": "Heuristic suggestion",
        "context": "Structural context",
        "unresolved": "Unresolved",
    }
    chips = []
    for membership_class in (
        "asserted",
        "matched",
        "suggested",
        "context",
        "unresolved",
    ):
        memberships = tuple(
            item
            for item in overlay.memberships
            if item.membership_class == membership_class
        )
        if not memberships:
            continue
        producers = tuple(dict.fromkeys(
            provenance.producer
            for item in memberships
            for provenance in item.provenance
            if provenance.admission_class == membership_class
        ))
        source_ids = tuple(dict.fromkeys(
            source_id
            for item in memberships
            for provenance in item.provenance
            if provenance.admission_class == membership_class
            for source_id in provenance.source_ids
        ))
        title = (
            f'Producer: {", ".join(producers)} · '
            f'Sources: {", ".join(source_ids)}'
        )
        chips.append(
            '<span class="focus-membership-chip '
            f'membership-{escape(membership_class)}" '
            f'title="{escape(title, quote=True)}">'
            f'{escape(labels[membership_class])} · {len(memberships)}</span>'
        )
    if not chips:
        return ""
    return (
        '<div class="focus-membership-summary" '
        'aria-label="Canonical focus membership">'
        '<small>Focus membership</small>'
        f'<span class="focus-membership-chips">{"".join(chips)}</span></div>'
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
.delta-node.kind-function rect,.delta-node.kind-method rect,.delta-node.kind-variable rect,.delta-node.kind-import rect{{fill:transparent;stroke:none}}
.delta-node.kind-function .delta-node-name,.delta-node.kind-method .delta-node-name{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:10px}}
.structural-container.kind-class{{fill:rgba(8,12,15,.12);stroke:rgba(111,128,135,.28)}}
.structural-container-header.kind-class rect{{fill:transparent;stroke:rgba(111,128,135,.26)}}
.relationship-inspector,.isolated-anchors{{margin-top:12px;border-top:1px solid rgba(111,128,135,.18);padding-top:10px}}
.relationship-inspector>summary,.isolated-anchors>summary{{cursor:pointer;color:var(--muted);font-size:10px}}
.standalone-explanation{{margin:8px 0 0;color:var(--faint);font-size:9px}}
.file-overview-intro{{margin:0 0 12px;color:var(--muted);font-size:10px}}
.unified-graph-stage{{margin-top:14px}}
.file-delta-canvas{{display:block;width:100%;min-width:720px;height:auto}}
.file-graph-node{{cursor:pointer;outline:none}}
.file-graph-node rect{{fill:#111a1f;stroke:#53656e;stroke-width:1.2}}
.file-graph-node:hover rect,.file-graph-node:focus rect{{stroke:var(--green);fill:rgba(54,118,87,.14)}}
.verification-lane-container{{fill:rgba(48,83,110,.06);stroke:rgba(159,205,240,.22);stroke-width:1}}
.file-graph-node.verification-row rect{{fill:rgba(9,15,19,.78);stroke:rgba(159,205,240,.28)}}
.file-graph-node.verification-row .file-node-operation{{fill:var(--muted)}}
.file-graph-node.retained-bridge rect{{fill:rgba(113,132,141,.06);stroke:#71848d;stroke-dasharray:5 4}}
.file-graph-node.retained-bridge .file-node-operation{{fill:#94a2a8}}
.verification-change-dot{{fill:var(--blue)}}
.file-node-operation{{fill:var(--green);font-size:8px;text-transform:uppercase}}
.file-node-name{{fill:var(--text);font-size:10px;font-weight:700}}
.file-node-counts{{fill:var(--faint);font-size:8px}}
.file-delta-edge>path{{fill:none;stroke:#71848d;stroke-width:1.8}}
.file-edge-bus{{fill:var(--blue);stroke:#0b1115;stroke-width:1}}
.file-delta-edge.operation-added>path{{stroke:var(--green)}}
.file-delta-edge.operation-removed>path{{stroke:var(--red);stroke-dasharray:5 4}}
.file-delta-edge rect{{fill:#10171b;stroke:rgba(111,128,135,.24)}}
.file-delta-edge text{{fill:var(--muted);font-size:7px;text-anchor:middle}}
.retained-boundary-context{{margin-top:10px;padding-top:9px;border-top:1px solid rgba(111,128,135,.18)}}
.retained-boundary-context>summary{{cursor:pointer;color:var(--muted);font-size:9px}}
.retained-boundary-context>p{{margin:6px 0;color:var(--faint);font-size:8px}}
.retained-boundary-context>div{{display:flex;flex-wrap:wrap;gap:5px}}
.retained-context-chip{{display:inline-flex;gap:6px;align-items:center;padding:4px 7px;border:1px solid rgba(111,128,135,.22);border-radius:999px;color:var(--muted);font:650 8px ui-monospace,SFMono-Regular,Menlo,monospace}}
.retained-context-chip small{{color:var(--faint);font:7px Inter,ui-sans-serif,system-ui,sans-serif}}
.file-member-graph{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:14px;align-items:start}}
.file-member-panel{{min-width:0;border:1px solid rgba(111,128,135,.28);border-radius:11px;background:rgba(5,10,13,.34);overflow:hidden}}
.file-member-panel>header{{display:grid;gap:3px;padding:11px 13px;border-bottom:1px solid rgba(111,128,135,.22);background:rgba(16,27,33,.5)}}
.file-header-meta{{display:flex;justify-content:space-between;gap:8px;align-items:center}}
.file-header-meta>span{{color:var(--green);font-size:8px;text-transform:uppercase}}
.file-member-panel>header b,.file-node-link{{overflow-wrap:anywhere;font-size:10px}}
.file-node-link,.member-node-link,.member-relation a{{color:inherit;text-decoration:none}}
.file-node-link:hover,.member-node-link:hover,.member-relation a:hover{{color:var(--blue);text-decoration:underline}}
.file-member-lines{{padding:4px 12px 9px}}
.file-member-line{{padding:8px 0}}
.file-member-line.is-nested{{margin-left:calc(var(--member-depth,0) * 12px);padding-left:10px;border-left:1px solid rgba(111,128,135,.24)}}
.file-member-line+.file-member-line{{border-top:1px solid rgba(111,128,135,.12)}}
.member-line-main{{display:grid;grid-template-columns:52px minmax(0,1fr) 58px;gap:8px;align-items:center}}
.member-line-main b,.member-node-link{{overflow-wrap:anywhere;font:650 9px ui-monospace,SFMono-Regular,Menlo,monospace}}
.member-line-main small,.member-operation{{color:var(--faint);font-size:7px;text-transform:uppercase}}
.member-line-main small{{text-align:right}}
.member-operation.inherited{{min-height:1px}}
.member-relation{{display:grid;grid-template-columns:74px 18px 78px 12px minmax(0,1fr);gap:5px;align-items:center;margin:5px 0 0 60px;padding:4px 6px;border-left:2px solid rgba(123,227,172,.48);background:rgba(54,118,87,.05);font-size:7px;outline:none}}
.member-relation:focus{{background:rgba(54,118,87,.14);border-left-color:var(--green)}}
.relation-kind{{color:var(--green);font-weight:720;text-transform:uppercase}}
.relation-operation{{font-size:10px;font-weight:800;text-align:center}}
.relation-operation.operation-added{{color:var(--green)}}
.relation-operation.operation-removed{{color:var(--red)}}
.relation-operation.operation-retained{{color:var(--faint)}}
.relation-target-file{{overflow:hidden;padding:1px 5px;border:1px solid rgba(159,205,240,.28);border-radius:999px;color:var(--blue);text-overflow:ellipsis;white-space:nowrap}}
.relation-arrow{{color:var(--faint);text-align:center}}
.relation-target-symbol{{min-width:0;overflow-wrap:anywhere;color:var(--muted);font-weight:550}}
.file-relations{{padding:8px 12px;border-bottom:1px solid rgba(111,128,135,.16);background:rgba(3,7,9,.18)}}
.file-relations>span{{display:block;margin-bottom:5px;color:var(--faint);font-size:7px;font-weight:750;text-transform:uppercase;letter-spacing:.06em}}
.file-relation-group{{border-top:1px solid rgba(111,128,135,.1)}}
.file-relation-group>summary{{display:grid;grid-template-columns:74px 18px 78px minmax(0,1fr);gap:5px;align-items:center;padding:5px 0;cursor:pointer;font-size:7px}}
.file-relation-group>summary b{{color:var(--muted);font-weight:550}}
.file-relation-group ul{{display:flex;flex-wrap:wrap;gap:5px;margin:0 0 6px;padding:0;list-style:none}}
.file-relation-group li{{padding:2px 6px;border-radius:5px;background:rgba(159,205,240,.07);font-size:7px}}
.file-member-line.related-target{{border-radius:5px;background:rgba(159,205,240,.09);box-shadow:inset 2px 0 var(--blue)}}
.delta-focus-controls{{display:grid;flex:1 1 100%;max-width:none;gap:10px;margin-top:12px}}
.delta-focus-primary{{display:flex;gap:7px;align-items:center}}
.delta-focus-families{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px 18px}}
.delta-focus-family{{display:grid;grid-template-columns:96px minmax(0,1fr);gap:9px;align-items:start}}
.delta-focus-family>span{{padding-top:5px;color:var(--faint);font-size:8px;font-weight:750;text-transform:uppercase;letter-spacing:.06em}}
.delta-focus-family>div{{display:flex;flex-wrap:wrap;gap:5px}}
.file-overview-empty{{margin:14px 0 0;padding:12px;border:1px dashed rgba(111,128,135,.26);border-radius:8px;color:var(--faint);font-size:10px}}
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
.architectural-chip rect{{fill:rgba(48,83,110,.8);stroke:rgba(159,205,240,.65);stroke-width:.8}}
.architectural-chip text{{fill:#c9e8ff;font-size:7px;font-weight:760;text-anchor:middle;text-transform:uppercase}}
.architectural-chip:hover rect,.architectural-chip:focus rect,.architectural-chip.member-active rect{{stroke:var(--green);fill:rgba(54,118,87,.55)}}
.architectural-chip.layer-unclassified rect{{stroke-dasharray:3 2;fill:rgba(111,128,135,.24)}}
.architectural-chip-html{{grid-column:1/-1;justify-self:start;border:1px solid rgba(159,205,240,.45);border-radius:999px;padding:2px 7px;background:rgba(48,83,110,.32);color:#c9e8ff;font:760 8px inherit;text-transform:uppercase;cursor:pointer}}
.architectural-chip-html.layer-unclassified{{border-style:dashed;color:var(--muted)}}
.file-header-meta .architectural-chip-html{{grid-column:auto;justify-self:auto;padding:1px 6px;font-size:7px}}
.member-muted{{opacity:.13}}.member-context{{opacity:.65}}.member-active{{opacity:1;filter:drop-shadow(0 0 5px rgba(123,227,172,.35))}}
.transformation-strip{{display:grid;grid-template-columns:minmax(0,1fr) 28px minmax(0,1.2fr) 28px minmax(0,1fr);gap:8px;align-items:stretch}}
.summary-stage{{min-width:0;padding:13px;border:1px solid rgba(111,128,135,.2);border-radius:10px;background:rgba(3,7,9,.2)}}
.summary-arrow{{display:grid;place-items:center;color:var(--faint);font-size:18px}}
.summary-claim{{display:grid;grid-template-columns:34px minmax(0,1fr) auto;gap:7px;align-items:center;width:100%;margin-top:7px;padding:8px;border:1px solid rgba(111,128,135,.18);border-radius:8px;background:rgba(16,24,28,.72);color:var(--text);font:inherit;text-align:left;cursor:pointer}}
.summary-claim:hover,.summary-claim:focus{{border-color:var(--green);outline:none}}.summary-claim>span{{color:var(--blue);font:700 8px ui-monospace,SFMono-Regular,Menlo,monospace}}.summary-claim>b{{overflow:hidden;font-size:9px;font-weight:620;text-overflow:ellipsis;white-space:nowrap}}.summary-claim>i{{font-style:normal}}
.summary-limits{{display:block;margin-top:12px;color:var(--faint);font-size:8px}}
.structural-graph-section .review-structural-graph{{margin:0;padding:0;border:0;background:transparent}}
.focus-assessment-inspector{{margin-top:12px;padding:12px;border:1px solid rgba(111,128,135,.22);border-left:2px solid var(--green);background:rgba(3,7,9,.22)}}
.focus-assessment-inspector[hidden],.focus-assessment[hidden]{{display:none}}.focus-assessment-inspector>h4{{margin:0 0 9px;color:var(--muted);font-size:9px;text-transform:uppercase;letter-spacing:.05em}}
.focus-assessment-heading{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:start}}
.focus-assessment-identity{{display:grid;grid-template-columns:34px minmax(0,1fr);gap:3px 8px;min-width:0}}.focus-assessment-identity b{{grid-row:1/3;color:var(--green);font:760 10px ui-monospace,SFMono-Regular,Menlo,monospace}}.focus-assessment-identity span{{font-size:11px;font-weight:620}}.focus-assessment-identity small{{color:var(--faint);font-size:8px}}
.focus-membership-summary{{display:flex;gap:9px;align-items:center;margin-top:9px;color:var(--faint)}}
.focus-membership-summary>small{{font-size:8px;white-space:nowrap}}
.focus-membership-chips{{display:flex;min-width:0;gap:5px;align-items:center;flex-wrap:wrap}}
.focus-membership-chip{{display:inline-flex;align-items:center;padding:2px 6px;border:1px solid rgba(111,128,135,.28);border-radius:999px;color:var(--muted);font-size:7px;line-height:1.3;white-space:nowrap}}
.focus-membership-chip.membership-asserted{{border-color:rgba(123,227,172,.58);color:var(--green)}}
.focus-membership-chip.membership-matched{{border-color:rgba(114,181,255,.55);color:var(--blue)}}
.focus-membership-chip.membership-suggested{{border-style:dashed;border-color:rgba(225,190,105,.52);color:#e1be69}}
.focus-membership-chip.membership-unresolved{{border-style:dashed;color:var(--faint)}}
.focus-exceptions{{display:flex;flex-wrap:wrap;gap:5px;margin-top:9px}}.focus-exceptions span{{padding:3px 7px;border:1px solid rgba(231,202,124,.34);border-radius:999px;background:rgba(106,85,30,.12);color:var(--amber);font-size:8px}}
.focus-assessment-detail{{margin-top:10px;border-top:1px solid rgba(111,128,135,.18);padding-top:8px}}.focus-assessment-detail>summary{{display:flex;justify-content:space-between;gap:12px;cursor:pointer;color:var(--muted);font-size:9px}}.focus-assessment-detail>summary span{{color:var(--faint);font-size:8px;text-align:right}}
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
@media(max-width:800px){{.transformation-strip{{grid-template-columns:1fr}}.summary-arrow{{transform:rotate(90deg)}}.verification-detail{{grid-template-columns:1fr}}.focus-assessment-heading{{grid-template-columns:1fr}}}}
@media(max-width:760px){{.file-delta-canvas{{min-width:680px}}.file-member-graph{{grid-template-columns:1fr}}.delta-focus-families{{grid-template-columns:1fr}}.delta-focus-family{{grid-template-columns:82px minmax(0,1fr)}}}}
.file-graph-node,.file-delta-edge,.retained-context-chip{{transition:opacity .16s ease,filter .16s ease}}
.file-graph-node.focus-hidden,.file-delta-edge.focus-hidden,.retained-context-chip.focus-hidden{{display:none}}
.file-graph-node.focus-muted,.file-delta-edge.focus-muted{{opacity:.12}}
.file-graph-node.focus-context,.file-delta-edge.focus-context{{opacity:.52}}
.file-graph-node.focus-active{{opacity:1;filter:drop-shadow(0 0 5px rgba(123,227,172,.25))}}
.file-delta-edge.focus-active{{opacity:1;filter:drop-shadow(0 0 3px rgba(123,227,172,.25))}}
.file-graph-layer.focus-no-map .delta-canvas-scroll,.file-graph-layer.focus-no-map .retained-boundary-context{{display:none}}
.file-node-layer{{fill:var(--blue);font-size:7px;text-anchor:end;text-transform:uppercase}}
.file-lane-label{{fill:var(--faint);font-size:8px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}}
.file-lane-label.verification{{fill:var(--blue)}}
.file-lane-divider{{stroke:rgba(111,128,135,.24);stroke-width:1}}
.evidence-paths{{margin-top:18px}}
.evidence-paths[hidden]{{display:none}}
.evidence-path-heading{{display:flex;justify-content:space-between;gap:14px;align-items:end;margin-bottom:8px}}
.evidence-path-heading h4{{margin:0;font-size:13px}}
.evidence-path-heading p{{margin:2px 0 0;color:var(--muted);font-size:9px}}
.evidence-path-list{{border-top:1px solid rgba(111,128,135,.22)}}
.evidence-path-row{{display:grid;grid-template-columns:115px minmax(0,1fr) auto;gap:12px;align-items:center;width:100%;padding:10px 8px;border:0;border-bottom:1px solid rgba(111,128,135,.12);background:transparent;color:var(--text);font:inherit;text-align:left;cursor:pointer}}
.evidence-path-row[hidden]{{display:none}}
.evidence-path-row:hover,.evidence-path-row.active{{background:rgba(54,118,87,.10)}}
.evidence-path-row.active{{box-shadow:inset 2px 0 var(--green)}}
.evidence-path-kind{{color:var(--blue);font-size:8px;font-weight:720;text-transform:uppercase}}
.evidence-path-main{{display:flex;min-width:0;align-items:center;gap:7px;overflow:hidden}}
.evidence-path-main>.focus-membership-chips{{margin-left:auto;flex-wrap:nowrap}}
.evidence-path-main code{{overflow:hidden;color:var(--text);font-size:9px;text-overflow:ellipsis;white-space:nowrap}}
.evidence-path-arrow{{flex:0 0 auto;color:var(--green)}}.evidence-path-plus{{color:var(--faint)}}
.evidence-path-action{{color:var(--faint);font-size:8px;white-space:nowrap}}
.evidence-path-inspector{{margin-top:12px;padding:12px;border:1px solid rgba(111,128,135,.24);background:rgba(3,7,9,.22)}}
.evidence-path-inspector[hidden],.evidence-path-trace[hidden],.path-trace-order[hidden]{{display:none}}
.evidence-path-inspector-heading{{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:11px;font-size:9px}}
.path-direction-controls{{display:flex;gap:5px}}
.path-direction-controls button{{padding:4px 8px;border:1px solid rgba(111,128,135,.34);border-radius:6px;background:transparent;color:var(--muted);font:inherit;font-size:8px;cursor:pointer}}
.path-direction-controls button[aria-pressed="true"]{{border-color:var(--green);color:var(--text)}}
.path-tree-forest{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;align-items:start}}
.path-tree-forest>.path-tree-node:only-child{{grid-column:1/-1}}
.path-tree-node{{min-width:0}}
.path-tree-node>ul{{display:grid;gap:6px;margin:6px 0 0 12px;padding:0 0 0 14px;border-left:1px solid rgba(123,227,172,.28);list-style:none}}
.path-tree-node>ul>li{{display:grid;grid-template-columns:94px minmax(0,1fr);gap:8px;align-items:start;position:relative}}
.path-tree-node>ul>li::before{{content:"";position:absolute;top:13px;left:-14px;width:11px;border-top:1px solid rgba(123,227,172,.42)}}
.path-trace-step{{display:grid;min-width:0;gap:3px;padding:7px 9px;border-left:2px solid var(--green);background:rgba(16,27,33,.5)}}
.path-trace-step a,.path-trace-step b{{overflow:hidden;color:var(--text);font:650 9px ui-monospace,SFMono-Regular,Menlo,monospace;text-decoration:none;text-overflow:ellipsis;white-space:nowrap}}
.path-trace-step a:hover{{color:var(--blue);text-decoration:underline}}
.path-trace-step small{{overflow:hidden;color:var(--faint);font-size:7px;text-overflow:ellipsis;white-space:nowrap}}
.path-tree-relation{{padding-top:7px;color:var(--green);font-size:7px;text-align:right}}
.path-tree-relation b{{font-size:10px;font-weight:400}}
.path-tree-reference{{display:block;padding:7px 9px;color:var(--blue);font:650 8px ui-monospace,SFMono-Regular,Menlo,monospace}}
.evidence-path-empty{{margin:10px 0 0;padding:10px;border:1px dashed rgba(111,128,135,.28);color:var(--muted);font-size:9px}}
.structural-audit{{margin-top:14px;border-top:1px solid rgba(111,128,135,.22);padding-top:10px}}
.structural-audit>summary{{cursor:pointer;color:var(--muted);font-size:10px}}
.structural-audit-intro{{margin:8px 0 0;color:var(--faint);font-size:8px}}
.structural-audit .file-member-graph{{margin-top:10px}}
@media(max-width:760px){{.evidence-path-row{{grid-template-columns:1fr auto}}.evidence-path-kind{{grid-column:1/-1}}.path-tree-forest{{grid-template-columns:1fr}}.path-tree-node>ul>li{{grid-template-columns:82px minmax(0,1fr)}}.evidence-path-main{{flex-wrap:wrap}}}}
</style></head><body><main class="shell">
<div class="topbar"><span class="brand-mark"></span>RepoDelta</div>
<section class="section"><div class="meta">{pr_link}<span>·</span><span>{escape(pr_state)}</span><span>·</span><span>{brief.overview.changed_file_count} changed files</span><span>·</span><span>{escape(ci_copy)}</span><span>·</span><span>{escape(llm_shadow_copy)}</span></div><h1>{escape(packet.title)}</h1>{primary_context}<span class="source-note">Source: {source_line}</span>{review_context}</section>
<section class="section structural-graph-section">{review_graph}</section>
{transformation_summary}
    {coverage_limits}
<div class="footer">RepoDelta · {escape(pr_label)} · Schema {escape(brief.schema_version)} · Generated by {escape(brief.generated_by)}</div>
</main><script>
const tokenSet = (value) => new Set((value || "").split(/\\s+/).filter(Boolean));
const intersects = (left, right) => [...left].some((item) => right.has(item));
const focusSurfaces = document.querySelectorAll(".review-structural-graph");
const clearMapFocus = (surface) => {{
  surface.querySelectorAll(".file-graph-node, .file-delta-edge, .retained-context-chip").forEach((item) => {{
    item.classList.remove("focus-hidden", "focus-muted", "focus-context", "focus-active");
  }});
  surface.querySelector(".file-graph-layer")?.classList.remove("focus-no-map");
}};
const applyAuthoredMapFocus = (surface, focus) => {{
  clearMapFocus(surface);
  surface.querySelectorAll(".file-graph-node, .file-delta-edge, .retained-context-chip").forEach((item) => {{
    const direct = focus === "overview" || tokenSet(item.dataset.focuses).has(focus);
    const contextual = focus !== "overview" && !direct &&
      tokenSet(item.dataset.contextFocuses).has(focus);
    item.classList.toggle("focus-hidden", focus !== "overview" && !direct && !contextual);
    item.classList.toggle("focus-context", contextual);
    item.classList.toggle("focus-active", focus !== "overview" && direct);
  }});
  const control = surface.querySelector(`[data-focus-target="${{focus}}"]`);
  const matched = focus === "overview" || control?.dataset.overviewVisible === "true";
  surface.querySelector(".file-graph-layer")?.classList.toggle(
    "focus-no-map", focus !== "overview" && !matched
  );
  return matched;
}};
const setPathDirection = (surface, direction) => {{
  const inspector = surface.querySelector(".evidence-path-inspector");
  if (!inspector) return;
  inspector.querySelectorAll("[data-path-direction-target]").forEach((button) => {{
    button.setAttribute("aria-pressed", String(
      button.dataset.pathDirectionTarget === direction
    ));
  }});
  inspector.querySelectorAll(".evidence-path-trace:not([hidden]) .path-trace-order").forEach((order) => {{
    order.hidden = order.dataset.pathDirection !== direction;
  }});
}};
const activateEvidencePath = (surface, row, narrowMap = true) => {{
  const fileIds = tokenSet(row.dataset.fileNodeIds);
  const groupIds = tokenSet(row.dataset.groupIds);
  surface.querySelectorAll(".evidence-path-row").forEach((item) => {{
    const active = item === row;
    item.classList.toggle("active", active);
    item.setAttribute("aria-pressed", String(active));
  }});
  if (narrowMap) {{
    clearMapFocus(surface);
    surface.querySelectorAll(".file-graph-node").forEach((node) => {{
      const active = fileIds.has(node.dataset.fileNode);
      node.classList.toggle("focus-active", active);
      node.classList.toggle("focus-muted", !active);
    }});
    surface.querySelectorAll(".file-delta-edge").forEach((edge) => {{
      const active = intersects(tokenSet(edge.dataset.groupIds), groupIds);
      edge.classList.toggle("focus-active", active);
      edge.classList.toggle("focus-muted", !active);
    }});
  }}
  const inspector = surface.querySelector(".evidence-path-inspector");
  if (!inspector) return;
  inspector.hidden = false;
  let selectedTrace = null;
  inspector.querySelectorAll(".evidence-path-trace").forEach((trace) => {{
    const active = trace.dataset.pathTrace === row.dataset.pathId;
    trace.hidden = !active;
    if (active) selectedTrace = trace;
  }});
  const callsMode = selectedTrace?.dataset.directionMode === "calls";
  const forward = inspector.querySelector('[data-path-direction-target="forward"]');
  const reverse = inspector.querySelector('[data-path-direction-target="reverse"]');
  if (forward) forward.textContent = callsMode ? "Callees" : "Forward";
  if (reverse) reverse.textContent = callsMode ? "Callers" : "Reverse";
  setPathDirection(surface, "forward");
}};
const filterEvidencePaths = (surface, focus) => {{
  const paths = surface.querySelector(".evidence-paths");
  if (!paths) return false;
  paths.hidden = focus === "overview";
  const inspector = paths.querySelector(".evidence-path-inspector");
  if (focus === "overview") {{
    if (inspector) inspector.hidden = true;
    paths.querySelectorAll(".evidence-path-row").forEach((row) => {{
      row.hidden = true;
      row.classList.remove("active");
      row.setAttribute("aria-pressed", "false");
    }});
    return false;
  }}
  let firstVisible = null;
  paths.querySelectorAll(".evidence-path-row").forEach((row) => {{
    const visible = tokenSet(row.dataset.focuses).has(focus);
    row.hidden = !visible;
    row.classList.remove("active");
    row.setAttribute("aria-pressed", "false");
    if (visible && !firstVisible) firstVisible = row;
  }});
  const empty = paths.querySelector(".evidence-path-empty");
  if (empty) empty.hidden = Boolean(firstVisible);
  if (!firstVisible) {{
    if (inspector) inspector.hidden = true;
    return false;
  }}
  activateEvidencePath(surface, firstVisible, false);
  return true;
}};
const activateFocus = (focus) => {{
  document.querySelectorAll(".delta-focus").forEach((item) => {{
    item.classList.toggle("active", item.dataset.focusTarget === focus);
  }});
  focusSurfaces.forEach((surface) => {{
    const assessmentInspector = surface.querySelector(".focus-assessment-inspector");
    let selectedAssessment = null;
    assessmentInspector?.querySelectorAll("[data-verification-subject]").forEach((item) => {{
      const active = focus !== "overview" && item.dataset.verificationSubject === focus;
      item.hidden = !active;
      if (active) selectedAssessment = item;
    }});
    if (assessmentInspector) assessmentInspector.hidden = !selectedAssessment;
    const matchedMap = applyAuthoredMapFocus(surface, focus);
    const matchedPath = filterEvidencePaths(surface, focus);
    const empty = surface.querySelector(".delta-focus-empty");
    if (empty) {{
      const show = focus !== "overview" && !matchedMap && !matchedPath;
      empty.hidden = !show;
      empty.textContent = show
        ? (selectedAssessment?.dataset.structuralFocusMessage ||
          `${{focus}} has no structural evidence in the default change backbone.`)
        : "";
    }}
  }});
}};
const activateMembers = (trigger) => {{
  const audit = trigger.closest(".structural-audit");
  if (!audit) return;
  audit.open = true;
  const nodeIds = tokenSet(trigger.dataset.memberNodeIds);
  const contextNodeIds = tokenSet(trigger.dataset.contextNodeIds);
  const groupIds = tokenSet(trigger.dataset.memberGroupIds);
  const contextGroupIds = tokenSet(trigger.dataset.contextGroupIds);
  audit.querySelectorAll("[data-component-target]").forEach((item) => {{
    const active = item.dataset.componentTarget === trigger.dataset.componentTarget;
    item.classList.toggle("member-active", active);
    item.classList.toggle("member-muted", !active);
  }});
  audit.querySelectorAll("[data-structural-node]").forEach((item) => {{
    const active = nodeIds.has(item.dataset.structuralNode);
    const contextual = !active && contextNodeIds.has(item.dataset.structuralNode);
    item.classList.toggle("member-active", active);
    item.classList.toggle("member-context", contextual);
    item.classList.toggle("member-muted", !active && !contextual);
  }});
  audit.querySelectorAll("[data-group-target]").forEach((item) => {{
    const active = groupIds.has(item.dataset.groupTarget);
    const contextual = !active && contextGroupIds.has(item.dataset.groupTarget);
    item.classList.toggle("member-active", active);
    item.classList.toggle("member-context", contextual);
    item.classList.toggle("member-muted", !active && !contextual);
  }});
  audit.scrollIntoView({{ behavior: "smooth", block: "nearest" }});
}};
document.querySelectorAll("[data-component-target]").forEach((item) => {{
  item.addEventListener("click", (event) => {{
    event.preventDefault();
    event.stopPropagation();
    activateMembers(item);
  }});
}});
document.querySelectorAll(".review-structural-graph").forEach((graph) => {{
  const interaction = {{ expandedGroup: null }};
  graph.querySelectorAll(".delta-focus").forEach((button) => {{
    button.addEventListener("click", () => {{
      const focus = button.dataset.focusTarget;
      activateFocus(focus);
    }});
  }});
  graph.querySelectorAll(".evidence-path-row").forEach((row) => {{
    row.addEventListener("click", () => activateEvidencePath(graph, row));
  }});
  graph.querySelectorAll("[data-path-direction-target]").forEach((button) => {{
    button.addEventListener("click", () => {{
      setPathDirection(graph, button.dataset.pathDirectionTarget);
    }});
  }});
  graph.querySelectorAll(".file-graph-node").forEach((node) => {{
    const selectPath = () => {{
      const fileId = node.dataset.fileNode;
      const row = Array.from(graph.querySelectorAll(".evidence-path-row:not([hidden])"))
        .find((candidate) => tokenSet(candidate.dataset.fileNodeIds).has(fileId));
      if (row) {{
        activateEvidencePath(graph, row);
        return;
      }}
      clearMapFocus(graph);
      graph.querySelectorAll(".file-graph-node").forEach((candidate) => {{
        const active = candidate === node;
        candidate.classList.toggle("focus-active", active);
        candidate.classList.toggle("focus-muted", !active);
      }});
      graph.querySelectorAll(".file-delta-edge").forEach((edge) => {{
        const active = tokenSet(edge.dataset.sourceFileIds).has(fileId) ||
          edge.dataset.targetFile === fileId;
        edge.classList.toggle("focus-active", active);
        edge.classList.toggle("focus-muted", !active);
      }});
    }};
    node.addEventListener("click", selectPath);
    node.addEventListener("keydown", (event) => {{
      if (event.key === "Enter" || event.key === " ") {{
        event.preventDefault();
        selectPath();
      }}
    }});
  }});
  const toggleGroup = (groupId) => {{
    interaction.expandedGroup = interaction.expandedGroup === groupId ? null : groupId;
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
    group.addEventListener("click", () => toggleGroup(group.dataset.groupTarget));
  }});
  graph.querySelectorAll(".member-relation[data-target-node]").forEach((relation) => {{
    const setTargetHighlight = (active) => {{
      graph.querySelectorAll(".file-member-line.related-target").forEach((row) => {{
        row.classList.remove("related-target");
      }});
      if (!active) return;
      graph.querySelector(
        `.file-member-line[data-structural-node="${{CSS.escape(relation.dataset.targetNode)}}"]`
      )?.classList.add("related-target");
    }};
    relation.addEventListener("mouseenter", () => setTargetHighlight(true));
    relation.addEventListener("mouseleave", () => setTargetHighlight(false));
    relation.addEventListener("focus", () => setTargetHighlight(true));
    relation.addEventListener("blur", () => setTargetHighlight(false));
  }});
}});
activateFocus("overview");
document.querySelectorAll("[data-summary-subject]").forEach((button) => {{
  button.addEventListener("click", () => {{
    const subject = button.dataset.summarySubject;
    activateFocus(subject);
    document.querySelector(".structural-graph-section")?.scrollIntoView({{
      behavior: "smooth", block: "start"
    }});
  }});
}});
</script></body></html>"""


def write_html(brief: ReviewBrief, output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(brief), encoding="utf-8")
    return path
