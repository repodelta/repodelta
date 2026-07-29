from __future__ import annotations

from prismcode.model.contracts import (
    StructuralGraphEdge,
    StructuralGraphNode,
    StructuralGraphPlacement,
)
from prismcode.projection.structural_groups import (
    project_structural_relation_groups,
)


def _node(node_id: str) -> StructuralGraphNode:
    return StructuralGraphNode(
        id=node_id,
        review_symbol_id=node_id,
        delta="modified",
        evidence_ids=(f"E:{node_id}",),
        display_evidence_id=f"E:{node_id}",
    )


def _placement(parent: str, child: str) -> StructuralGraphPlacement:
    return StructuralGraphPlacement(
        id=f"P:{parent}:{child}",
        parent_node_id=parent,
        child_node_id=child,
        head_ownership_evidence_ids=(f"E:P:{parent}:{child}",),
    )


def _edge(
    edge_id: str,
    source: str,
    target: str,
    *,
    relation: str = "imports",
) -> StructuralGraphEdge:
    return StructuralGraphEdge(
        id=edge_id,
        source_node_id=source,
        target_node_id=target,
        relation=relation,
        operation="added",
        relation_change_evidence_id=f"E:{edge_id}",
        path_relation_ids=(f"PATH:{edge_id}",),
    )


def test_cross_container_edges_collapse_without_losing_members() -> None:
    nodes = tuple(
        _node(node_id)
        for node_id in ("file-a", "file-b", "class-b", "method-b")
    )
    placements = (
        _placement("file-b", "class-b"),
        _placement("class-b", "method-b"),
    )
    edges = (
        _edge("edge-class", "file-a", "class-b"),
        _edge("edge-method", "file-a", "method-b"),
    )

    result = project_structural_relation_groups(
        nodes=nodes,
        edges=tuple(reversed(edges)),
        placements=tuple(reversed(placements)),
        backbone_edge_ids=("edge-method", "edge-class"),
    )

    assert result.primary_placement_ids == (
        "P:class-b:method-b",
        "P:file-b:class-b",
    )
    assert len(result.groups) == 1
    group = result.groups[0]
    assert (group.source_node_id, group.target_node_id) == (
        "file-a",
        "file-b",
    )
    assert group.member_edge_ids == ("edge-class", "edge-method")
    assert group.path_relation_ids == (
        "PATH:edge-class",
        "PATH:edge-method",
    )
    assert result.backbone_group_ids == (group.id,)
    assert result.group_id_by_edge_id == {
        "edge-class": group.id,
        "edge-method": group.id,
    }


def test_internal_relations_keep_distinct_non_self_endpoints() -> None:
    nodes = tuple(
        _node(node_id)
        for node_id in ("file", "class", "source", "target")
    )
    placements = (
        _placement("file", "class"),
        _placement("class", "source"),
        _placement("class", "target"),
    )

    result = project_structural_relation_groups(
        nodes=nodes,
        edges=(_edge("edge", "source", "target", relation="calls"),),
        placements=placements,
        backbone_edge_ids=("edge",),
    )

    assert len(result.groups) == 1
    assert (
        result.groups[0].source_node_id,
        result.groups[0].target_node_id,
    ) == ("source", "target")
