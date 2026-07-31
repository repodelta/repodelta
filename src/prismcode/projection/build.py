from __future__ import annotations

import hashlib
from dataclasses import replace

from prismcode.model.contracts import (
    CandidateConvergence,
    CanonicalChangeMapEntry,
    ChangedFile,
    DiagnosticPresentation,
    EvidenceCatalog,
    EvidenceItem,
    ClosureScanPlanSet,
    ProjectionCandidateSet,
    ProjectionRelation,
    ReviewProjection,
    ReviewSourcePacket,
    ReviewSlice,
    ReviewStructuralGraph,
    StructuralFocusNode,
    StructuralFocusDisposition,
    StructuralFocusOverlay,
    StructuralGraphEdge,
    StructuralGraphNode,
    StructuralGraphOwnershipEdge,
    StructuralGraphPlacement,
)
from prismcode.projection.structural_groups import (
    project_structural_relation_groups,
)
from prismcode.projection.structural_navigation import (
    project_structural_navigation,
)


_ROLE_ORDER = {
    "changed_anchor": 0,
    "runtime_context": 1,
    "test_context": 2,
    "intermediate": 3,
}
def build_review_projection(
    candidates: ProjectionCandidateSet,
    convergence: CandidateConvergence,
    evidence_catalog: EvidenceCatalog,
    *,
    diagnostic_presentation: DiagnosticPresentation,
    changed_files: tuple[ChangedFile, ...] = (),
    closure_scan_plans: ClosureScanPlanSet = ClosureScanPlanSet(),
    packet: ReviewSourcePacket | None = None,
) -> ReviewProjection:
    """Project converged canonical facts without performing retrieval or selection."""

    relations = candidates.by_id()
    evidence = evidence_catalog.by_id()
    convergence_groups = {
        item.focus_statement_id: item for item in convergence.groups
    }
    plans_by_statement = closure_scan_plans.by_statement_id()
    diagnostic_ids_by_focus = diagnostic_presentation.ids_by_focus()
    structural_diagnostics = {
        item.id: item
        for item in (*candidates.diagnostics, *convergence.diagnostics)
        if item.slot
        in {"changed_anchor", "runtime_context", "test_context", "structural_path"}
    }
    slices = []
    graph_node_order: list[str] = []
    graph_nodes: dict[str, StructuralGraphNode] = {}
    graph_edge_order: list[str] = []
    graph_edges: dict[str, StructuralGraphEdge] = {}
    graph_ownership_edge_order: list[str] = []
    graph_ownership_edges: dict[str, StructuralGraphOwnershipEdge] = {}
    graph_placement_order: list[str] = []
    graph_placements: dict[str, StructuralGraphPlacement] = {}
    graph_path_relation_ids: list[str] = []
    backbone_seed_node_ids: list[str] = []

    for group in candidates.groups:
        converged = convergence_groups[group.focus_statement_id]
        selected = tuple(
            relations[relation_id]
            for relation_id in converged.selected_relation_ids
        )
        by_slot = {
            slot: tuple(item for item in selected if item.slot == slot)
            for slot in (
                "claim",
                "changed_anchor",
                "runtime_context",
                "test_context",
                "verification",
                "structural_path",
                "closure_fact",
            )
        }
        overlay, nodes, edges, ownership_edges, placements = _structural_focus_overlay(
            path_relations=tuple(
                relations[relation_id]
                for relation_id in converged.structural_closure.path_relation_ids
            ),
            relation_change_evidence_ids=(
                converged.structural_closure.relation_change_evidence_ids
            ),
            anchor_relations=by_slot["changed_anchor"],
            runtime_relations=by_slot["runtime_context"],
            test_relations=by_slot["test_context"],
            evidence=evidence,
            changed_files=changed_files,
        )
        represented_relation_ids = {
            relation_id
            for node in overlay.nodes
            for relation_id in node.relation_ids
        }
        deferred_structural_relation_ids = tuple(
            relation_id
            for relation_id in converged.deferred_relation_ids
            if _is_structural_relation(relations[relation_id], evidence)
        )
        non_structural_relation_ids = tuple(
            relation_id
            for relation_id in converged.selected_relation_ids
            if relations[relation_id].target_type == "evidence"
            if relation_id not in represented_relation_ids
            if not _is_structural_relation(relations[relation_id], evidence)
        )
        structural_diagnostic_ids = tuple(
            diagnostic_id
            for diagnostic_id in diagnostic_ids_by_focus.get(
                group.focus_statement_id,
                (),
            )
            if diagnostic_id in structural_diagnostics
        )
        structural_disposition = StructuralFocusDisposition(
            state=_structural_disposition_state(
                projected=bool(overlay.nodes),
                non_structural_relation_ids=non_structural_relation_ids,
                deferred_structural_relation_ids=deferred_structural_relation_ids,
                diagnostic_states=tuple(
                    structural_diagnostics[item].state
                    for item in structural_diagnostic_ids
                ),
            ),
            non_structural_relation_ids=non_structural_relation_ids,
            deferred_structural_relation_ids=deferred_structural_relation_ids,
            diagnostic_ids=structural_diagnostic_ids,
        )
        backbone_seed_node_ids.extend(
            node.node_id
            for node in overlay.nodes
            if any(
                relations[relation_id].slot == "changed_anchor"
                and relations[relation_id].evidence_role == "primary"
                for relation_id in node.relation_ids
            )
        )
        for node in nodes:
            if node.id not in graph_nodes:
                graph_node_order.append(node.id)
                graph_nodes[node.id] = node
            else:
                graph_nodes[node.id] = _merge_node(graph_nodes[node.id], node)
        for edge in edges:
            if edge.id not in graph_edges:
                graph_edge_order.append(edge.id)
                graph_edges[edge.id] = edge
            else:
                graph_edges[edge.id] = _merge_edge(graph_edges[edge.id], edge)
        for edge in ownership_edges:
            if edge.id not in graph_ownership_edges:
                graph_ownership_edge_order.append(edge.id)
                graph_ownership_edges[edge.id] = edge
            elif graph_ownership_edges[edge.id] != edge:
                raise ValueError(
                    "canonical structural ownership edge identity is inconsistent"
                )
        for placement in placements:
            if placement.id not in graph_placements:
                graph_placement_order.append(placement.id)
                graph_placements[placement.id] = placement
            elif graph_placements[placement.id] != placement:
                raise ValueError(
                    "canonical structural placement identity is inconsistent"
                )
        graph_path_relation_ids.extend(overlay.path_relation_ids)
        slices.append(
            ReviewSlice(
                change_map=CanonicalChangeMapEntry(
                    focus_statement_id=group.focus_statement_id,
                    claim_relation_ids=tuple(
                        item.id for item in by_slot["claim"]
                    ),
                    structural_overlay=overlay,
                    structural_disposition=structural_disposition,
                ),
                standalone_changed_fact_relation_ids=tuple(
                    item.id
                    for item in by_slot["changed_anchor"]
                    if item.evidence_role == "primary"
                    if evidence[item.target_id].kind
                    not in {"symbol", "structural_change"}
                ),
                standalone_test_support_relation_ids=tuple(
                    item.id
                    for item in by_slot["changed_anchor"]
                    if item.evidence_role == "test_support"
                    if evidence[item.target_id].kind
                    not in {"symbol", "structural_change"}
                ),
                standalone_document_support_relation_ids=tuple(
                    item.id
                    for item in by_slot["changed_anchor"]
                    if item.evidence_role == "document_support"
                    if evidence[item.target_id].kind
                    not in {"symbol", "structural_change"}
                ),
                standalone_runtime_relation_ids=tuple(
                    item.id
                    for item in by_slot["runtime_context"]
                    if item.id not in represented_relation_ids
                ),
                standalone_test_relation_ids=tuple(
                    item.id
                    for item in by_slot["test_context"]
                    if item.id not in represented_relation_ids
                ),
                verification_relation_ids=tuple(
                    item.id for item in by_slot["verification"]
                ),
                closure_fact_relation_ids=tuple(
                    item.id for item in by_slot["closure_fact"]
                ),
                closure_scan_plan_id=(
                    plans_by_statement[group.focus_statement_id].id
                    if group.focus_statement_id in plans_by_statement
                    else None
                ),
                diagnostic_ids=diagnostic_ids_by_focus.get(
                    group.focus_statement_id,
                    (),
                ),
            )
        )

    complete_nodes = tuple(
        graph_nodes[node_id] for node_id in graph_node_order
    )
    complete_edges = tuple(
        graph_edges[edge_id] for edge_id in graph_edge_order
    )
    complete_ownership_edges = tuple(
        graph_ownership_edges[edge_id]
        for edge_id in graph_ownership_edge_order
    )
    complete_placements = tuple(
        graph_placements[placement_id]
        for placement_id in graph_placement_order
    )
    (
        backbone_node_ids,
        backbone_edge_ids,
        backbone_ownership_edge_ids,
    ) = _change_backbone(
        nodes=complete_nodes,
        edges=complete_edges,
        ownership_edges=complete_ownership_edges,
        placements=complete_placements,
        seed_node_ids=tuple(dict.fromkeys(backbone_seed_node_ids)),
    )
    relation_groups = project_structural_relation_groups(
        nodes=complete_nodes,
        edges=complete_edges,
        placements=complete_placements,
        backbone_edge_ids=backbone_edge_ids,
    )
    navigation = project_structural_navigation(
        nodes=complete_nodes,
        edges=complete_edges,
        evidence=evidence,
        packet=packet,
    )
    slices = [
        replace(
            review_slice,
            change_map=replace(
                review_slice.change_map,
                structural_overlay=replace(
                    review_slice.change_map.structural_overlay,
                    relation_group_ids=tuple(
                        dict.fromkeys(
                            relation_groups.group_id_by_edge_id[edge_id]
                            for edge_id in (
                                review_slice.change_map.structural_overlay.edge_ids
                            )
                        )
                    )
                ),
            ),
        )
        for review_slice in slices
    ]
    projection = ReviewProjection(
        slices=tuple(slices),
        review_graph=ReviewStructuralGraph(
            nodes=navigation.nodes,
            edges=navigation.edges,
            relation_groups=relation_groups.groups,
            ownership_edges=complete_ownership_edges,
            placements=complete_placements,
            primary_placement_ids=relation_groups.primary_placement_ids,
            backbone_node_ids=backbone_node_ids,
            backbone_edge_ids=backbone_edge_ids,
            backbone_relation_group_ids=relation_groups.backbone_group_ids,
            backbone_ownership_edge_ids=backbone_ownership_edge_ids,
            path_relation_ids=tuple(dict.fromkeys(graph_path_relation_ids)),
            navigation_targets=navigation.targets,
        ),
    )
    projection.validate_consistency(
        evidence_catalog,
        candidates,
        convergence,
    )
    return projection


def _is_structural_relation(
    relation: ProjectionRelation,
    evidence: dict[str, EvidenceItem],
) -> bool:
    if relation.slot == "structural_path":
        return True
    target = evidence.get(relation.target_id)
    return (
        relation.slot in {"changed_anchor", "runtime_context", "test_context"}
        and target is not None
        and target.kind in {"symbol", "structural_change"}
    )


def _structural_disposition_state(
    *,
    projected: bool,
    non_structural_relation_ids: tuple[str, ...],
    deferred_structural_relation_ids: tuple[str, ...],
    diagnostic_states: tuple[str, ...],
) -> str:
    if projected:
        return "projected"
    if deferred_structural_relation_ids:
        return "deferred"
    if non_structural_relation_ids:
        return "non_structural_only"
    states = set(diagnostic_states)
    if states & {"no_association", "no_eligible_fact"}:
        return "unassociated"
    if states & {
        "provider_unavailable",
        "not_applicable",
        "source_absent",
        "stale_source",
        "partial_coverage",
    }:
        return "unavailable"
    return "no_structural_evidence"


def _change_backbone(
    *,
    nodes: tuple[StructuralGraphNode, ...],
    edges: tuple[StructuralGraphEdge, ...],
    ownership_edges: tuple[StructuralGraphOwnershipEdge, ...],
    placements: tuple[StructuralGraphPlacement, ...] = (),
    seed_node_ids: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Project the default change backbone without deleting complete support."""

    node_ids = {item.id for item in nodes}
    backbone_nodes = set(seed_node_ids) & node_ids
    backbone_edges: set[str] = set()
    changed_edge_seed_ids = set(backbone_nodes)

    for edge in edges:
        if edge.operation not in {"added", "removed"}:
            continue
        if (
            edge.source_node_id not in changed_edge_seed_ids
            and edge.target_node_id not in changed_edge_seed_ids
        ):
            continue
        backbone_edges.add(edge.id)
        backbone_nodes.update((edge.source_node_id, edge.target_node_id))

    for edge in edges:
        if (
            edge.operation == "retained"
            and edge.source_node_id in backbone_nodes
            and edge.target_node_id in backbone_nodes
        ):
            backbone_edges.add(edge.id)

    ownership_by_child: dict[str, list[StructuralGraphOwnershipEdge]] = {}
    for edge in ownership_edges:
        ownership_by_child.setdefault(edge.child_node_id, []).append(edge)
    backbone_ownership_edges: set[str] = set()
    frontier = list(backbone_nodes)
    expanded: set[str] = set()
    while frontier:
        child_node_id = frontier.pop(0)
        if child_node_id in expanded:
            continue
        expanded.add(child_node_id)
        for edge in ownership_by_child.get(child_node_id, ()):
            backbone_ownership_edges.add(edge.id)
            if edge.parent_node_id not in backbone_nodes:
                backbone_nodes.add(edge.parent_node_id)
                frontier.append(edge.parent_node_id)

    placement_parents_by_child: dict[str, list[str]] = {}
    for placement in placements:
        placement_parents_by_child.setdefault(
            placement.child_node_id, []
        ).append(placement.parent_node_id)
    frontier = list(backbone_nodes)
    expanded.clear()
    while frontier:
        child_node_id = frontier.pop(0)
        if child_node_id in expanded:
            continue
        expanded.add(child_node_id)
        for parent_node_id in placement_parents_by_child.get(
            child_node_id, ()
        ):
            if parent_node_id not in backbone_nodes:
                backbone_nodes.add(parent_node_id)
                frontier.append(parent_node_id)

    return (
        tuple(item.id for item in nodes if item.id in backbone_nodes),
        tuple(item.id for item in edges if item.id in backbone_edges),
        tuple(
            item.id
            for item in ownership_edges
            if item.id in backbone_ownership_edges
        ),
    )


def _structural_focus_overlay(
    *,
    path_relations: tuple[ProjectionRelation, ...],
    relation_change_evidence_ids: tuple[str, ...],
    anchor_relations: tuple[ProjectionRelation, ...],
    runtime_relations: tuple[ProjectionRelation, ...],
    test_relations: tuple[ProjectionRelation, ...],
    evidence: dict[str, EvidenceItem],
    changed_files: tuple[ChangedFile, ...],
) -> tuple[
    StructuralFocusOverlay,
    tuple[StructuralGraphNode, ...],
    tuple[StructuralGraphEdge, ...],
    tuple[StructuralGraphOwnershipEdge, ...],
    tuple[StructuralGraphPlacement, ...],
]:
    """Build one focus overlay from canonical change and relation-change facts."""

    path_relation_by_evidence_id = {
        relation.target_id: relation for relation in path_relations
    }
    selected_path_ids = set(path_relation_by_evidence_id)
    symbols_by_review_id = _symbols_by_review_id(evidence)
    relation_ids_by_review_id: dict[str, list[str]] = {}
    role_by_review_id: dict[str, str] = {}
    anchor_nodes: dict[str, StructuralGraphNode] = {}

    for role, selected_relations in (
        ("changed_anchor", anchor_relations),
        ("runtime_context", runtime_relations),
        ("test_context", test_relations),
    ):
        for relation in selected_relations:
            fact = evidence.get(relation.target_id)
            if fact is None:
                raise ValueError(
                    f"selected {relation.slot} relation references missing evidence: "
                    f"{relation.id}"
                )
            review_id = _review_symbol_id(fact)
            if review_id is None:
                continue
            relation_ids_by_review_id.setdefault(review_id, []).append(relation.id)
            previous_role = role_by_review_id.get(review_id, "intermediate")
            role_by_review_id[review_id] = min(
                (previous_role, role),
                key=_ROLE_ORDER.__getitem__,
            )
            if role == "changed_anchor":
                anchor_nodes[review_id] = _node_for_review_symbol(
                    review_id,
                    evidence=evidence,
                    symbols_by_review_id=symbols_by_review_id,
                    changed_files=changed_files,
                    anchor=fact,
                )

    edges = []
    nodes_by_review_id = dict(anchor_nodes)
    node_path_ids: dict[str, list[str]] = {
        review_id: [] for review_id in anchor_nodes
    }
    edge_ids = []
    overlay_path_relation_ids = []
    for relation_change_id in relation_change_evidence_ids:
        relation_change = evidence.get(relation_change_id)
        if relation_change is None:
            raise ValueError(
                "structural closure references missing relation-change evidence: "
                f"{relation_change_id}"
            )
        identity = relation_change.structural_relation_change
        if relation_change.kind != "structural_relation_change" or identity is None:
            raise ValueError(
                "structural closure references invalid relation-change evidence: "
                f"{relation_change_id}"
            )
        provenance_path_ids = {
            *identity.base_path_evidence_ids,
            *identity.head_path_evidence_ids,
        }
        supporting_path_ids = selected_path_ids & provenance_path_ids
        support_relation_ids = tuple(
            relation.id
            for path_id, relation in path_relation_by_evidence_id.items()
            if path_id in supporting_path_ids
        )
        for review_id in (
            identity.source_review_symbol_id,
            identity.target_review_symbol_id,
        ):
            if review_id not in nodes_by_review_id:
                nodes_by_review_id[review_id] = _node_for_review_symbol(
                    review_id,
                    evidence=evidence,
                    symbols_by_review_id=symbols_by_review_id,
                    changed_files=changed_files,
                )
            node_path_ids.setdefault(review_id, []).extend(support_relation_ids)
        edge_ids.append(relation_change.id)
        overlay_path_relation_ids.extend(support_relation_ids)
        edges.append(
            StructuralGraphEdge(
                id=relation_change.id,
                source_node_id=_structural_node_id(
                    identity.source_review_symbol_id
                ),
                target_node_id=_structural_node_id(
                    identity.target_review_symbol_id
                ),
                relation=identity.relation,
                operation=relation_change.operation,
                relation_change_evidence_id=relation_change.id,
                path_relation_ids=support_relation_ids,
            )
        )

    placements = []
    placement_ids = []
    placements_by_child, nodes_by_placement_id = _placements_by_child(evidence)
    frontier = list(nodes_by_review_id)
    expanded: set[str] = set()
    while frontier:
        child_review_id = frontier.pop(0)
        if child_review_id in expanded:
            continue
        expanded.add(child_review_id)
        for placement in placements_by_child.get(child_review_id, ()):
            parent_review_id = nodes_by_placement_id[placement.id]
            if parent_review_id not in nodes_by_review_id:
                nodes_by_review_id[parent_review_id] = _node_for_review_symbol(
                    parent_review_id,
                    evidence=evidence,
                    symbols_by_review_id=symbols_by_review_id,
                    changed_files=changed_files,
                )
                node_path_ids.setdefault(parent_review_id, [])
                frontier.append(parent_review_id)
            placement_ids.append(placement.id)
            placements.append(placement)

    ownership_edges = []
    ownership_edge_ids = []
    ownership_by_child = _ownership_changes_by_child(evidence)
    frontier = list(nodes_by_review_id)
    expanded.clear()
    while frontier:
        child_review_id = frontier.pop(0)
        if child_review_id in expanded:
            continue
        expanded.add(child_review_id)
        for ownership_change in ownership_by_child.get(child_review_id, ()):
            identity = ownership_change.structural_ownership_change
            assert identity is not None
            parent_review_id = identity.parent_review_symbol_id
            if parent_review_id not in nodes_by_review_id:
                nodes_by_review_id[parent_review_id] = _node_for_review_symbol(
                    parent_review_id,
                    evidence=evidence,
                    symbols_by_review_id=symbols_by_review_id,
                    changed_files=changed_files,
                )
                node_path_ids.setdefault(parent_review_id, [])
                frontier.append(parent_review_id)
            ownership_edge_ids.append(ownership_change.id)
            ownership_edges.append(
                StructuralGraphOwnershipEdge(
                    id=ownership_change.id,
                    parent_node_id=_structural_node_id(parent_review_id),
                    child_node_id=_structural_node_id(child_review_id),
                    operation=ownership_change.operation,
                    ownership_change_evidence_id=ownership_change.id,
                )
            )

    graph_nodes = tuple(
        _merge_node(
            node,
            StructuralGraphNode(
                id=node.id,
                review_symbol_id=node.review_symbol_id,
                delta=node.delta,
                evidence_ids=node.evidence_ids,
                display_evidence_id=node.display_evidence_id,
                path_relation_ids=tuple(
                    dict.fromkeys(node_path_ids.get(review_id, ()))
                ),
            ),
        )
        for review_id, node in nodes_by_review_id.items()
    )
    overlay_nodes = tuple(
        StructuralFocusNode(
            node_id=node.id,
            role=role_by_review_id.get(review_id, "intermediate"),
            relation_ids=tuple(
                dict.fromkeys(relation_ids_by_review_id.get(review_id, ()))
            ),
            path_relation_ids=node.path_relation_ids,
        )
        for review_id, node in zip(nodes_by_review_id, graph_nodes, strict=True)
    )
    return (
        StructuralFocusOverlay(
            nodes=overlay_nodes,
            edge_ids=tuple(edge_ids),
            ownership_edge_ids=tuple(dict.fromkeys(ownership_edge_ids)),
            placement_ids=tuple(dict.fromkeys(placement_ids)),
            path_relation_ids=tuple(dict.fromkeys(overlay_path_relation_ids)),
        ),
        graph_nodes,
        tuple(edges),
        tuple(ownership_edges),
        tuple(placements),
    )


def _ownership_changes_by_child(
    evidence: dict[str, EvidenceItem],
) -> dict[str, tuple[EvidenceItem, ...]]:
    grouped: dict[str, list[EvidenceItem]] = {}
    for item in evidence.values():
        identity = item.structural_ownership_change
        if item.kind != "structural_ownership_change" or identity is None:
            continue
        grouped.setdefault(identity.child_review_symbol_id, []).append(item)
    return {
        child_id: tuple(sorted(items, key=lambda item: item.id))
        for child_id, items in grouped.items()
    }


def _placements_by_child(
    evidence: dict[str, EvidenceItem],
) -> tuple[
    dict[str, tuple[StructuralGraphPlacement, ...]],
    dict[str, str],
]:
    grouped: dict[tuple[str, str], dict[str, list[str]]] = {}
    for item in evidence.values():
        identity = item.structural_ownership
        if item.kind != "structural_ownership" or identity is None:
            continue
        parent = evidence.get(identity.parent_symbol_evidence_id)
        child = evidence.get(identity.child_symbol_evidence_id)
        parent_review_id = _review_symbol_id(parent) if parent is not None else None
        child_review_id = _review_symbol_id(child) if child is not None else None
        if parent_review_id is None or child_review_id is None:
            raise ValueError(
                f"{item.id}: structural ownership references symbols without "
                "review identities"
            )
        by_revision = grouped.setdefault(
            (parent_review_id, child_review_id),
            {"base": [], "head": []},
        )
        by_revision[item.revision_side].append(item.id)
    by_child: dict[str, list[StructuralGraphPlacement]] = {}
    parent_by_placement_id: dict[str, str] = {}
    for (parent_review_id, child_review_id), by_revision in sorted(grouped.items()):
        placement_id = _structural_placement_id(
            parent_review_id,
            child_review_id,
        )
        placement = StructuralGraphPlacement(
            id=placement_id,
            parent_node_id=_structural_node_id(parent_review_id),
            child_node_id=_structural_node_id(child_review_id),
            base_ownership_evidence_ids=tuple(sorted(by_revision["base"])),
            head_ownership_evidence_ids=tuple(sorted(by_revision["head"])),
        )
        by_child.setdefault(child_review_id, []).append(placement)
        parent_by_placement_id[placement_id] = parent_review_id
    return (
        {
            child_review_id: tuple(items)
            for child_review_id, items in by_child.items()
        },
        parent_by_placement_id,
    )


def _review_symbol_id(item: EvidenceItem) -> str | None:
    if item.kind == "structural_change" and item.structural_change is not None:
        return item.structural_change.review_symbol_id
    if item.kind == "symbol":
        value = item.metadata.get("review_symbol_id")
        return str(value) if value else None
    return None


def _symbols_by_review_id(
    evidence: dict[str, EvidenceItem],
) -> dict[str, tuple[EvidenceItem, ...]]:
    grouped: dict[str, list[EvidenceItem]] = {}
    for item in evidence.values():
        review_id = _review_symbol_id(item)
        if item.kind == "symbol" and review_id is not None:
            grouped.setdefault(review_id, []).append(item)
    return {
        review_id: tuple(
            sorted(
                items,
                key=lambda item: (
                    {"head": 0, "base": 1}.get(item.revision_side, 2),
                    item.id,
                ),
            )
        )
        for review_id, items in grouped.items()
    }


def _node_for_review_symbol(
    review_id: str,
    *,
    evidence: dict[str, EvidenceItem],
    symbols_by_review_id: dict[str, tuple[EvidenceItem, ...]],
    changed_files: tuple[ChangedFile, ...],
    anchor: EvidenceItem | None = None,
) -> StructuralGraphNode:
    symbol_items = symbols_by_review_id.get(review_id, ())
    if anchor is None:
        anchor = next(
            (
                item
                for item in evidence.values()
                if item.kind == "structural_change"
                and item.structural_change is not None
                and item.structural_change.review_symbol_id == review_id
            ),
            None,
        )
    evidence_ids = tuple(
        dict.fromkeys(
            (
                *((anchor.id,) if anchor is not None else ()),
                *(item.id for item in symbol_items),
            )
        )
    )
    if not evidence_ids:
        raise ValueError(
            f"structural graph references missing symbol fact: {review_id}"
        )
    delta = (
        _node_delta(anchor.operation)
        if anchor is not None and anchor.changed
        else _support_node_delta(symbol_items, changed_files)
    )
    display_evidence_id = _display_evidence_id(
        delta,
        evidence_ids,
        evidence,
    )
    return StructuralGraphNode(
        id=_structural_node_id(review_id),
        review_symbol_id=review_id,
        delta=delta,
        evidence_ids=evidence_ids,
        display_evidence_id=display_evidence_id,
    )


def _display_evidence_id(
    delta: str,
    evidence_ids: tuple[str, ...],
    evidence: dict[str, EvidenceItem],
) -> str:
    """Choose one revision-aware source fact for canonical graph presentation."""

    desired_revision = "base" if delta == "removed" else "head"
    available = tuple(
        evidence[evidence_id]
        for evidence_id in evidence_ids
        if evidence_id in evidence
    )
    desired = tuple(
        item for item in available if item.revision_side == desired_revision
    )
    candidates = desired or available
    if not candidates:
        raise ValueError("structural graph node has no display evidence")
    return min(
        candidates,
        key=lambda item: (
            0 if item.kind == "structural_change" else 1,
            0 if item.kind == "symbol" else 1,
            item.id,
        ),
    ).id


def _node_delta(operation: str) -> str:
    if operation in {
        "added",
        "modified",
        "renamed",
        "removed",
        "unresolved",
    }:
        return operation
    raise ValueError(f"unsupported structural node delta: {operation}")


def _support_node_delta(
    symbol_items: tuple[EvidenceItem, ...],
    changed_files: tuple[ChangedFile, ...],
) -> str:
    changed_operations = {
        item.operation
        for item in symbol_items
        if item.changed
        and item.operation
        in {"added", "modified", "renamed", "removed"}
    }
    if len(changed_operations) == 1:
        return next(iter(changed_operations))
    if any(item.metadata.get("symbol_kind") == "file" for item in symbol_items):
        symbol_paths = {
            str(item.metadata["path"])
            for item in symbol_items
            if item.metadata.get("path")
        }
        changed_file = next(
            (
                item
                for item in changed_files
                if symbol_paths & {item.base_path, item.head_path}
            ),
            None,
        )
        if changed_file is not None:
            return changed_file.status
    revisions = {item.revision_side for item in symbol_items}
    return "retained" if {"base", "head"} <= revisions else "unresolved"


def _merge_node(
    left: StructuralGraphNode,
    right: StructuralGraphNode,
) -> StructuralGraphNode:
    if left.id != right.id or left.review_symbol_id != right.review_symbol_id:
        raise ValueError("cannot merge different structural graph nodes")
    if left.delta != right.delta:
        raise ValueError(
            "canonical structural graph node delta is inconsistent: "
            f"{left.review_symbol_id} ({left.delta} != {right.delta})"
        )
    if left.display_evidence_id != right.display_evidence_id:
        raise ValueError(
            "canonical structural graph node display evidence is inconsistent: "
            f"{left.review_symbol_id}"
        )
    return StructuralGraphNode(
        id=left.id,
        review_symbol_id=left.review_symbol_id,
        delta=left.delta,
        evidence_ids=tuple(dict.fromkeys((*left.evidence_ids, *right.evidence_ids))),
        display_evidence_id=left.display_evidence_id,
        path_relation_ids=tuple(
            dict.fromkeys((*left.path_relation_ids, *right.path_relation_ids))
        ),
    )


def _merge_edge(
    left: StructuralGraphEdge,
    right: StructuralGraphEdge,
) -> StructuralGraphEdge:
    if left != right and (
        left.id,
        left.source_node_id,
        left.target_node_id,
        left.relation,
        left.operation,
        left.relation_change_evidence_id,
    ) != (
        right.id,
        right.source_node_id,
        right.target_node_id,
        right.relation,
        right.operation,
        right.relation_change_evidence_id,
    ):
        raise ValueError("canonical structural edge identity is inconsistent")
    return StructuralGraphEdge(
        id=left.id,
        source_node_id=left.source_node_id,
        target_node_id=left.target_node_id,
        relation=left.relation,
        operation=left.operation,
        relation_change_evidence_id=left.relation_change_evidence_id,
        path_relation_ids=tuple(
            dict.fromkeys((*left.path_relation_ids, *right.path_relation_ids))
        ),
    )


def _structural_node_id(review_symbol_id: str) -> str:
    digest = hashlib.sha256(review_symbol_id.encode("utf-8")).hexdigest()
    return f"SN:{digest[:20]}"


def _structural_placement_id(
    parent_review_symbol_id: str,
    child_review_symbol_id: str,
) -> str:
    identity = f"{parent_review_symbol_id}\0{child_review_symbol_id}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"SP:{digest[:20]}"
