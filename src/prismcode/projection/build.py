from __future__ import annotations

from prismcode.model.contracts import (
    CandidateConvergence,
    EvidenceCatalog,
    EvidenceItem,
    ProjectionCandidateSet,
    ProjectionRelation,
    ReviewProjection,
    ReviewSlice,
    StructuralSubgraph,
    StructuralSubgraphEdge,
    StructuralSubgraphNode,
)


def build_review_projection(
    candidates: ProjectionCandidateSet,
    convergence: CandidateConvergence,
    evidence_catalog: EvidenceCatalog,
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
    slices = []
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
            )
        }
        subgraph = _structural_subgraph(
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
        graph_node_ids = {item.evidence_id for item in subgraph.nodes}
        slices.append(
            ReviewSlice(
                focus_statement_id=group.focus_statement_id,
                claim_relation_ids=tuple(item.id for item in by_slot["claim"]),
                standalone_changed_anchor_relation_ids=tuple(
                    item.id
                    for item in by_slot["changed_anchor"]
                    if item.target_id not in graph_node_ids
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
                structural_subgraph=subgraph,
                diagnostic_ids=(
                    *group.diagnostic_ids,
                    *converged.diagnostic_ids,
                ),
            )
        )
    return ReviewProjection(slices=tuple(slices))


def _structural_subgraph(
    *,
    path_relations: tuple[ProjectionRelation, ...],
    anchor_relations: tuple[ProjectionRelation, ...],
    runtime_relations: tuple[ProjectionRelation, ...],
    test_relations: tuple[ProjectionRelation, ...],
    evidence: dict[str, EvidenceItem],
    symbol_evidence_ids: dict[str, str],
) -> StructuralSubgraph:
    if not path_relations:
        return StructuralSubgraph()

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
    edge_order: list[tuple[str, str, str, str]] = []
    path_ids_by_edge: dict[tuple[str, str, str, str], list[str]] = {}
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
            if key not in path_ids_by_edge:
                edge_order.append(key)
                path_ids_by_edge[key] = []
            path_ids_by_edge[key].append(path_relation.id)

    nodes = tuple(
        StructuralSubgraphNode(
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
    edges = tuple(
        StructuralSubgraphEdge(
            source_evidence_id=source_id,
            target_evidence_id=target_id,
            relation=relation,
            direction=direction,
            path_relation_ids=tuple(dict.fromkeys(path_ids_by_edge[key])),
        )
        for key in edge_order
        for source_id, relation, direction, target_id in (key,)
    )
    return StructuralSubgraph(
        nodes=nodes,
        edges=edges,
        path_relation_ids=tuple(item.id for item in path_relations),
    )
