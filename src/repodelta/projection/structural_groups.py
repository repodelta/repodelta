from __future__ import annotations

import hashlib
from dataclasses import dataclass

from repodelta.model.contracts import (
    StructuralGraphEdge,
    StructuralGraphNode,
    StructuralGraphPlacement,
    StructuralRelationGroup,
)


@dataclass(frozen=True)
class StructuralRelationGroupProjection:
    groups: tuple[StructuralRelationGroup, ...]
    primary_placement_ids: tuple[str, ...]
    backbone_group_ids: tuple[str, ...]
    group_id_by_edge_id: dict[str, str]


def project_structural_relation_groups(
    *,
    nodes: tuple[StructuralGraphNode, ...],
    edges: tuple[StructuralGraphEdge, ...],
    placements: tuple[StructuralGraphPlacement, ...],
    backbone_edge_ids: tuple[str, ...],
) -> StructuralRelationGroupProjection:
    """Project stable display lanes without replacing canonical edge truth."""

    node_ids = {item.id for item in nodes}
    primary_by_child = _primary_placements(placements, node_ids)
    primary_placement_ids = tuple(
        sorted(placement.id for placement in primary_by_child.values())
    )
    grouped: dict[
        tuple[str, str, str, str],
        list[StructuralGraphEdge],
    ] = {}
    for edge in sorted(edges, key=lambda item: item.id):
        source_id, target_id = _display_endpoints(
            edge.source_node_id,
            edge.target_node_id,
            primary_by_child,
        )
        key = (source_id, target_id, edge.relation, edge.operation)
        grouped.setdefault(key, []).append(edge)

    groups = []
    group_id_by_edge_id: dict[str, str] = {}
    backbone_edges = set(backbone_edge_ids)
    backbone_group_ids = []
    for key in sorted(grouped):
        source_id, target_id, relation, operation = key
        members = grouped[key]
        group_id = _relation_group_id(*key)
        group = StructuralRelationGroup(
            id=group_id,
            source_node_id=source_id,
            target_node_id=target_id,
            relation=relation,
            operation=operation,
            member_edge_ids=tuple(item.id for item in members),
            path_evidence_ids=tuple(
                dict.fromkeys(
                    path_evidence_id
                    for item in members
                    for path_evidence_id in item.path_evidence_ids
                )
            ),
        )
        groups.append(group)
        for edge in members:
            group_id_by_edge_id[edge.id] = group_id
        if any(edge.id in backbone_edges for edge in members):
            backbone_group_ids.append(group_id)

    return StructuralRelationGroupProjection(
        groups=tuple(groups),
        primary_placement_ids=primary_placement_ids,
        backbone_group_ids=tuple(backbone_group_ids),
        group_id_by_edge_id=group_id_by_edge_id,
    )


def _primary_placements(
    placements: tuple[StructuralGraphPlacement, ...],
    node_ids: set[str],
) -> dict[str, StructuralGraphPlacement]:
    by_child: dict[str, list[StructuralGraphPlacement]] = {}
    for placement in placements:
        if (
            placement.parent_node_id in node_ids
            and placement.child_node_id in node_ids
        ):
            by_child.setdefault(placement.child_node_id, []).append(placement)
    return {
        child_id: min(
            candidates,
            key=lambda item: (
                0 if item.head_ownership_evidence_ids else 1,
                item.id,
            ),
        )
        for child_id, candidates in by_child.items()
    }


def _display_endpoints(
    source_id: str,
    target_id: str,
    primary_by_child: dict[str, StructuralGraphPlacement],
) -> tuple[str, str]:
    source_chain = _ownership_chain(source_id, primary_by_child)
    target_chain = _ownership_chain(target_id, primary_by_child)
    common = 0
    for source_ancestor, target_ancestor in zip(
        source_chain,
        target_chain,
        strict=False,
    ):
        if source_ancestor != target_ancestor:
            break
        common += 1
    if common == 0:
        return source_chain[0], target_chain[0]
    source_endpoint = (
        source_chain[common]
        if common < len(source_chain)
        else source_chain[-1]
    )
    target_endpoint = (
        target_chain[common]
        if common < len(target_chain)
        else target_chain[-1]
    )
    if source_endpoint == target_endpoint:
        return source_id, target_id
    return source_endpoint, target_endpoint


def _ownership_chain(
    node_id: str,
    primary_by_child: dict[str, StructuralGraphPlacement],
) -> tuple[str, ...]:
    chain = [node_id]
    current = node_id
    visited = {node_id}
    while current in primary_by_child:
        current = primary_by_child[current].parent_node_id
        if current in visited:
            raise ValueError("primary structural placement contains a cycle")
        visited.add(current)
        chain.append(current)
    return tuple(reversed(chain))


def _relation_group_id(
    source_node_id: str,
    target_node_id: str,
    relation: str,
    operation: str,
) -> str:
    identity = "\0".join(
        (source_node_id, target_node_id, relation, operation)
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return f"SRG:{digest}"
