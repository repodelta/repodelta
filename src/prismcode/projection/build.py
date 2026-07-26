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
)


def build_review_projection(
    candidates: ProjectionCandidateSet,
    convergence: CandidateConvergence,
    evidence_catalog: EvidenceCatalog,
    *,
    guardrail_scan_plans: GuardrailScanPlanSet = GuardrailScanPlanSet(),
) -> ReviewProjection:
    """Project converged relation IDs without performing retrieval or selection."""

    relations = candidates.by_id()
    evidence = evidence_catalog.by_id()
    symbol_evidence_ids = {
        item.metadata["symbol_id"]: item.id
        for item in evidence_catalog.items
        if item.kind == "symbol" and item.metadata.get("symbol_id")
    }
    convergence_groups = {
        item.focus_statement_id: item for item in convergence.groups
    }
    plans_by_guardrail = guardrail_scan_plans.by_guardrail_id()
    slices = []
    graph_node_order: list[str] = []
    graph_path_ids_by_node: dict[str, list[str]] = {}
    graph_edge_order: list[str] = []
    graph_edges: dict[str, StructuralGraphEdge] = {}
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
        overlay, nodes, edges = _structural_focus_overlay(
            path_relations=tuple(
                relations[relation_id]
                for relation_id in converged.structural_support.path_relation_ids
            ),
            anchor_relations=by_slot["changed_anchor"],
            runtime_relations=by_slot["runtime_context"],
            test_relations=by_slot["test_context"],
            evidence=evidence,
            symbol_evidence_ids=symbol_evidence_ids,
        )
        graph_node_ids = {item.evidence_id for item in overlay.nodes}
        for node in nodes:
            if node.evidence_id not in graph_node_order:
                graph_node_order.append(node.evidence_id)
            graph_path_ids_by_node.setdefault(node.evidence_id, []).extend(
                node.path_relation_ids
            )
        for edge in edges:
            if edge.id not in graph_edges:
                graph_edge_order.append(edge.id)
                graph_edges[edge.id] = edge
            else:
                existing = graph_edges[edge.id]
                graph_edges[edge.id] = StructuralGraphEdge(
                    id=existing.id,
                    source_evidence_id=existing.source_evidence_id,
                    target_evidence_id=existing.target_evidence_id,
                    relation=existing.relation,
                    direction=existing.direction,
                    path_relation_ids=tuple(
                        dict.fromkeys(
                            (*existing.path_relation_ids, *edge.path_relation_ids)
                        )
                    ),
                )
        graph_path_relation_ids.extend(overlay.path_relation_ids)
        slices.append(
            ReviewSlice(
                focus_statement_id=group.focus_statement_id,
                claim_relation_ids=tuple(item.id for item in by_slot["claim"]),
                standalone_changed_fact_relation_ids=tuple(
                    item.id
                    for item in by_slot["changed_anchor"]
                    if evidence[item.target_id].kind != "symbol"
                ),
                standalone_runtime_relation_ids=tuple(
                    item.id
                    for item in by_slot["runtime_context"]
                    if item.target_id not in graph_node_ids
                ),
                standalone_test_relation_ids=tuple(
                    item.id
                    for item in by_slot["test_context"]
                    if item.target_id not in graph_node_ids
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
    return ReviewProjection(
        slices=tuple(slices),
        review_graph=ReviewStructuralGraph(
            nodes=tuple(
                StructuralGraphNode(
                    evidence_id=node_id,
                    path_relation_ids=tuple(
                        dict.fromkeys(graph_path_ids_by_node[node_id])
                    ),
                )
                for node_id in graph_node_order
            ),
            edges=tuple(graph_edges[edge_id] for edge_id in graph_edge_order),
            path_relation_ids=tuple(dict.fromkeys(graph_path_relation_ids)),
        ),
    )


def _structural_focus_overlay(
    *,
    path_relations: tuple[ProjectionRelation, ...],
    anchor_relations: tuple[ProjectionRelation, ...],
    runtime_relations: tuple[ProjectionRelation, ...],
    test_relations: tuple[ProjectionRelation, ...],
    evidence: dict[str, EvidenceItem],
    symbol_evidence_ids: dict[str, str],
) -> tuple[
    StructuralFocusOverlay,
    tuple[StructuralGraphNode, ...],
    tuple[StructuralGraphEdge, ...],
]:
    relation_ids_by_node: dict[str, list[str]] = {}
    role_by_node = {}
    for role, relations in (
        ("changed_anchor", anchor_relations),
        ("runtime_context", runtime_relations),
        ("test_context", test_relations),
    ):
        for item in relations:
            relation_ids_by_node.setdefault(item.target_id, []).append(item.id)
            role_by_node.setdefault(item.target_id, role)

    node_order: list[str] = []
    path_ids_by_node: dict[str, list[str]] = {}
    edge_order: list[str] = []
    edge_identity: dict[str, tuple[str, str, str, str]] = {}
    path_ids_by_edge: dict[str, list[str]] = {}
    for anchor_relation in anchor_relations:
        anchor = evidence.get(anchor_relation.target_id)
        if anchor is None:
            raise ValueError(
                "selected changed-anchor relation references missing evidence: "
                f"{anchor_relation.id}"
            )
        if anchor.kind == "symbol":
            if anchor.id not in node_order:
                node_order.append(anchor.id)
            path_ids_by_node.setdefault(anchor.id, [])

    for path_relation in path_relations:
        path = evidence.get(path_relation.target_id)
        if path is None or path.kind != "structural_path":
            raise ValueError(
                "selected structural path relation references invalid evidence: "
                f"{path_relation.id}"
            )
        for step in path.metadata.get("steps", ()):
            source_id = symbol_evidence_ids.get(step.get("source_symbol_id"))
            target_id = symbol_evidence_ids.get(step.get("target_symbol_id"))
            if source_id is None or target_id is None:
                raise ValueError(
                    "selected structural path references a missing symbol fact: "
                    f"{path_relation.id}"
                )
            for node_id in (source_id, target_id):
                if node_id not in node_order:
                    node_order.append(node_id)
                path_ids_by_node.setdefault(node_id, []).append(
                    path_relation.id
                )
            key = (
                source_id,
                step["relation"],
                step["direction"],
                target_id,
            )
            edge_id = _structural_edge_id(key)
            if edge_id not in path_ids_by_edge:
                edge_order.append(edge_id)
                edge_identity[edge_id] = key
                path_ids_by_edge[edge_id] = []
            path_ids_by_edge[edge_id].append(path_relation.id)

    overlay_nodes = tuple(
        StructuralFocusNode(
            evidence_id=node_id,
            role=role_by_node.get(node_id, "intermediate"),
            relation_ids=tuple(
                dict.fromkeys(relation_ids_by_node.get(node_id, ()))
            ),
            path_relation_ids=tuple(
                dict.fromkeys(path_ids_by_node.get(node_id, ()))
            ),
        )
        for node_id in node_order
    )
    graph_nodes = tuple(
        StructuralGraphNode(
            evidence_id=node_id,
            path_relation_ids=tuple(
                dict.fromkeys(path_ids_by_node.get(node_id, ()))
            ),
        )
        for node_id in node_order
    )
    edges = tuple(
        StructuralGraphEdge(
            id=edge_id,
            source_evidence_id=source_id,
            target_evidence_id=target_id,
            relation=relation,
            direction=direction,
            path_relation_ids=tuple(dict.fromkeys(path_ids_by_edge[edge_id])),
        )
        for edge_id in edge_order
        for source_id, relation, direction, target_id in (
            edge_identity[edge_id],
        )
    )
    return (
        StructuralFocusOverlay(
            nodes=overlay_nodes,
            edge_ids=tuple(edge_order),
            path_relation_ids=tuple(item.id for item in path_relations),
        ),
        graph_nodes,
        edges,
    )


def _structural_edge_id(
    identity: tuple[str, str, str, str],
) -> str:
    digest = hashlib.sha256("\0".join(identity).encode("utf-8")).hexdigest()
    return f"SE:{digest[:20]}"
