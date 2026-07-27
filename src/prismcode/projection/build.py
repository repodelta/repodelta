from __future__ import annotations

import hashlib

from prismcode.model.contracts import (
    CandidateConvergence,
    EvidenceCatalog,
    EvidenceItem,
    GuardrailScanPlanSet,
    ProjectionCandidateSet,
    ProjectionRelation,
    ReviewProjection,
    ReviewSlice,
    ReviewStructuralGraph,
    StructuralFocusNode,
    StructuralFocusOverlay,
    StructuralGraphEdge,
    StructuralGraphNode,
    StructuralGraphOwnershipEdge,
)


_ROLE_ORDER = {
    "changed_anchor": 0,
    "runtime_context": 1,
    "test_context": 2,
    "intermediate": 3,
}
_OPERATION_ORDER = {
    "added": 0,
    "modified": 1,
    "removed": 2,
    "context": 3,
}


def build_review_projection(
    candidates: ProjectionCandidateSet,
    convergence: CandidateConvergence,
    evidence_catalog: EvidenceCatalog,
    *,
    guardrail_scan_plans: GuardrailScanPlanSet = GuardrailScanPlanSet(),
) -> ReviewProjection:
    """Project converged canonical facts without performing retrieval or selection."""

    relations = candidates.by_id()
    evidence = evidence_catalog.by_id()
    convergence_groups = {
        item.focus_statement_id: item for item in convergence.groups
    }
    plans_by_guardrail = guardrail_scan_plans.by_guardrail_id()
    slices = []
    graph_node_order: list[str] = []
    graph_nodes: dict[str, StructuralGraphNode] = {}
    graph_edge_order: list[str] = []
    graph_edges: dict[str, StructuralGraphEdge] = {}
    graph_ownership_edge_order: list[str] = []
    graph_ownership_edges: dict[str, StructuralGraphOwnershipEdge] = {}
    graph_path_relation_ids: list[str] = []

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
                "boundary_fact",
            )
        }
        overlay, nodes, edges, ownership_edges = _structural_focus_overlay(
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
        )
        represented_relation_ids = {
            relation_id
            for node in overlay.nodes
            for relation_id in node.relation_ids
        }
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
        graph_path_relation_ids.extend(overlay.path_relation_ids)
        slices.append(
            ReviewSlice(
                focus_statement_id=group.focus_statement_id,
                claim_relation_ids=tuple(item.id for item in by_slot["claim"]),
                standalone_changed_fact_relation_ids=tuple(
                    item.id
                    for item in by_slot["changed_anchor"]
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
                boundary_fact_relation_ids=tuple(
                    item.id for item in by_slot["boundary_fact"]
                ),
                guardrail_scan_plan_id=(
                    plans_by_guardrail[group.focus_statement_id].id
                    if group.focus_statement_id in plans_by_guardrail
                    else None
                ),
                structural_overlay=overlay,
                diagnostic_ids=(
                    *group.diagnostic_ids,
                    *converged.diagnostic_ids,
                ),
            )
        )

    projection = ReviewProjection(
        slices=tuple(slices),
        review_graph=ReviewStructuralGraph(
            nodes=tuple(graph_nodes[node_id] for node_id in graph_node_order),
            edges=tuple(graph_edges[edge_id] for edge_id in graph_edge_order),
            ownership_edges=tuple(
                graph_ownership_edges[edge_id]
                for edge_id in graph_ownership_edge_order
            ),
            path_relation_ids=tuple(dict.fromkeys(graph_path_relation_ids)),
        ),
    )
    projection.validate_consistency(evidence_catalog)
    return projection


def _structural_focus_overlay(
    *,
    path_relations: tuple[ProjectionRelation, ...],
    relation_change_evidence_ids: tuple[str, ...],
    anchor_relations: tuple[ProjectionRelation, ...],
    runtime_relations: tuple[ProjectionRelation, ...],
    test_relations: tuple[ProjectionRelation, ...],
    evidence: dict[str, EvidenceItem],
) -> tuple[
    StructuralFocusOverlay,
    tuple[StructuralGraphNode, ...],
    tuple[StructuralGraphEdge, ...],
    tuple[StructuralGraphOwnershipEdge, ...],
]:
    """Build one focus overlay from canonical change and relation-change facts."""

    path_relation_by_evidence_id = {
        relation.target_id: relation for relation in path_relations
    }
    selected_path_ids = set(path_relation_by_evidence_id)
    symbols_by_provider_id = _symbols_by_provider_id(evidence)
    relation_ids_by_provider: dict[str, list[str]] = {}
    role_by_provider: dict[str, str] = {}
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
            provider_id = _provider_symbol_id(fact)
            if provider_id is None:
                continue
            relation_ids_by_provider.setdefault(provider_id, []).append(relation.id)
            previous_role = role_by_provider.get(provider_id, "intermediate")
            role_by_provider[provider_id] = min(
                (previous_role, role),
                key=_ROLE_ORDER.__getitem__,
            )
            if role == "changed_anchor":
                anchor_nodes[provider_id] = _node_for_provider(
                    provider_id,
                    evidence=evidence,
                    symbols_by_provider_id=symbols_by_provider_id,
                    anchor=fact,
                )

    edges = []
    nodes_by_provider = dict(anchor_nodes)
    node_path_ids: dict[str, list[str]] = {
        provider_id: [] for provider_id in anchor_nodes
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
        for provider_id in (
            identity.source_provider_symbol_id,
            identity.target_provider_symbol_id,
        ):
            if provider_id not in nodes_by_provider:
                nodes_by_provider[provider_id] = _node_for_provider(
                    provider_id,
                    evidence=evidence,
                    symbols_by_provider_id=symbols_by_provider_id,
                )
            node_path_ids.setdefault(provider_id, []).extend(support_relation_ids)
        edge_ids.append(relation_change.id)
        overlay_path_relation_ids.extend(support_relation_ids)
        edges.append(
            StructuralGraphEdge(
                id=relation_change.id,
                source_node_id=_structural_node_id(
                    identity.source_provider_symbol_id
                ),
                target_node_id=_structural_node_id(
                    identity.target_provider_symbol_id
                ),
                relation=identity.relation,
                operation=relation_change.operation,
                relation_change_evidence_id=relation_change.id,
                path_relation_ids=support_relation_ids,
            )
        )

    ownership_edges = []
    ownership_edge_ids = []
    ownership_by_child = _ownership_changes_by_child(evidence)
    frontier = list(nodes_by_provider)
    expanded: set[str] = set()
    while frontier:
        child_provider_id = frontier.pop(0)
        if child_provider_id in expanded:
            continue
        expanded.add(child_provider_id)
        for ownership_change in ownership_by_child.get(child_provider_id, ()):
            identity = ownership_change.structural_ownership_change
            assert identity is not None
            parent_provider_id = identity.parent_provider_symbol_id
            if parent_provider_id not in nodes_by_provider:
                nodes_by_provider[parent_provider_id] = _node_for_provider(
                    parent_provider_id,
                    evidence=evidence,
                    symbols_by_provider_id=symbols_by_provider_id,
                )
                node_path_ids.setdefault(parent_provider_id, [])
                frontier.append(parent_provider_id)
            ownership_edge_ids.append(ownership_change.id)
            ownership_edges.append(
                StructuralGraphOwnershipEdge(
                    id=ownership_change.id,
                    parent_node_id=_structural_node_id(parent_provider_id),
                    child_node_id=_structural_node_id(child_provider_id),
                    operation=ownership_change.operation,
                    ownership_change_evidence_id=ownership_change.id,
                )
            )

    graph_nodes = tuple(
        _merge_node(
            node,
            StructuralGraphNode(
                id=node.id,
                provider_symbol_id=node.provider_symbol_id,
                operation=node.operation,
                evidence_ids=node.evidence_ids,
                path_relation_ids=tuple(
                    dict.fromkeys(node_path_ids.get(provider_id, ()))
                ),
            ),
        )
        for provider_id, node in nodes_by_provider.items()
    )
    overlay_nodes = tuple(
        StructuralFocusNode(
            node_id=node.id,
            role=role_by_provider.get(provider_id, "intermediate"),
            relation_ids=tuple(
                dict.fromkeys(relation_ids_by_provider.get(provider_id, ()))
            ),
            path_relation_ids=node.path_relation_ids,
        )
        for provider_id, node in zip(nodes_by_provider, graph_nodes, strict=True)
    )
    return (
        StructuralFocusOverlay(
            nodes=overlay_nodes,
            edge_ids=tuple(edge_ids),
            ownership_edge_ids=tuple(dict.fromkeys(ownership_edge_ids)),
            path_relation_ids=tuple(dict.fromkeys(overlay_path_relation_ids)),
        ),
        graph_nodes,
        tuple(edges),
        tuple(ownership_edges),
    )


def _ownership_changes_by_child(
    evidence: dict[str, EvidenceItem],
) -> dict[str, tuple[EvidenceItem, ...]]:
    grouped: dict[str, list[EvidenceItem]] = {}
    for item in evidence.values():
        identity = item.structural_ownership_change
        if item.kind != "structural_ownership_change" or identity is None:
            continue
        grouped.setdefault(identity.child_provider_symbol_id, []).append(item)
    return {
        child_id: tuple(sorted(items, key=lambda item: item.id))
        for child_id, items in grouped.items()
    }


def _provider_symbol_id(item: EvidenceItem) -> str | None:
    if item.kind == "structural_change" and item.structural_change is not None:
        return item.structural_change.provider_symbol_id
    if item.kind == "symbol":
        value = item.metadata.get("symbol_id")
        return str(value) if value else None
    return None


def _symbols_by_provider_id(
    evidence: dict[str, EvidenceItem],
) -> dict[str, tuple[EvidenceItem, ...]]:
    grouped: dict[str, list[EvidenceItem]] = {}
    for item in evidence.values():
        provider_id = _provider_symbol_id(item)
        if item.kind == "symbol" and provider_id is not None:
            grouped.setdefault(provider_id, []).append(item)
    return {
        provider_id: tuple(
            sorted(
                items,
                key=lambda item: (
                    {"head": 0, "base": 1}.get(item.revision_side, 2),
                    item.id,
                ),
            )
        )
        for provider_id, items in grouped.items()
    }


def _node_for_provider(
    provider_id: str,
    *,
    evidence: dict[str, EvidenceItem],
    symbols_by_provider_id: dict[str, tuple[EvidenceItem, ...]],
    anchor: EvidenceItem | None = None,
) -> StructuralGraphNode:
    symbol_items = symbols_by_provider_id.get(provider_id, ())
    if anchor is None:
        anchor = next(
            (
                item
                for item in evidence.values()
                if item.kind == "structural_change"
                and item.structural_change is not None
                and item.structural_change.provider_symbol_id == provider_id
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
            f"structural graph references missing symbol fact: {provider_id}"
        )
    operation = (
        _node_operation(anchor.operation)
        if anchor is not None and anchor.changed
        else "context"
    )
    return StructuralGraphNode(
        id=_structural_node_id(provider_id),
        provider_symbol_id=provider_id,
        operation=operation,
        evidence_ids=evidence_ids,
    )


def _node_operation(operation: str) -> str:
    if operation in {"added", "removed"}:
        return operation
    return "modified"


def _merge_node(
    left: StructuralGraphNode,
    right: StructuralGraphNode,
) -> StructuralGraphNode:
    if left.id != right.id or left.provider_symbol_id != right.provider_symbol_id:
        raise ValueError("cannot merge different structural graph nodes")
    return StructuralGraphNode(
        id=left.id,
        provider_symbol_id=left.provider_symbol_id,
        operation=min(
            (left.operation, right.operation),
            key=_OPERATION_ORDER.__getitem__,
        ),
        evidence_ids=tuple(dict.fromkeys((*left.evidence_ids, *right.evidence_ids))),
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


def _structural_node_id(provider_symbol_id: str) -> str:
    digest = hashlib.sha256(provider_symbol_id.encode("utf-8")).hexdigest()
    return f"SN:{digest[:20]}"
