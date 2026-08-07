from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import PurePosixPath

from prismcode.model.contracts import (
    ArchitecturalChangeTopology,
    ArchitecturalComponent,
    ArchitecturalLayer,
    EvidenceCatalog,
    ReviewStructuralGraph,
    StructuralGraphNode,
    StructuralRelationGroup,
)


_SOURCE_ROOTS = {"src", "lib", "app", "packages"}
_LAYER_SEGMENTS: tuple[tuple[ArchitecturalLayer, frozenset[str]], ...] = (
    ("verification", frozenset({"test", "tests", "spec", "specs"})),
    ("documentation", frozenset({"doc", "docs", "documentation"})),
    ("automation", frozenset({".github", "ci", "workflows"})),
    ("entry", frozenset({"cli", "entrypoint", "entrypoints"})),
    ("presentation", frozenset({"presentation", "ui", "views", "web"})),
    (
        "application",
        frozenset({"application", "orchestration", "pipeline", "service", "services"}),
    ),
    ("domain", frozenset({"domain", "model", "semantics", "assessment"})),
    (
        "infrastructure",
        frozenset({"provider", "providers", "adapter", "adapters", "client", "clients"}),
    ),
    (
        "persistence",
        frozenset(
            {"storage", "database", "db", "persistence", "repository", "repositories"}
        ),
    ),
)


def project_architectural_change_topology(
    graph: ReviewStructuralGraph,
    evidence_catalog: EvidenceCatalog,
) -> ArchitecturalChangeTopology:
    """Classify one canonical graph into path-bounded components."""

    evidence = evidence_catalog.by_id()
    nodes = {item.id: item for item in graph.nodes}
    relation_groups = {item.id: item for item in graph.relation_groups}
    grouped_nodes: dict[tuple[str, ArchitecturalLayer], list[str]] = {}
    for node_id in graph.backbone_node_ids:
        node = nodes[node_id]
        fact = evidence[node.display_evidence_id]
        path = str(fact.metadata.get("path", ""))
        domain, layer = classify_architectural_path(path)
        grouped_nodes.setdefault((domain, layer), []).append(node_id)

    components = tuple(
        ArchitecturalComponent(
            id=_component_id(domain, layer),
            domain=domain,
            layer=layer,
            node_ids=tuple(sorted(node_ids)),
            classification_authority=(
                "path_structure" if layer == "unclassified" else "path_convention"
            ),
        )
        for (domain, layer), node_ids in sorted(grouped_nodes.items())
    )
    components = _with_component_membership(
        components,
        tuple(
            relation_groups[item]
            for item in graph.backbone_relation_group_ids
        ),
    )
    topology = ArchitecturalChangeTopology(
        components=components,
    )
    validate_architectural_change_topology(topology, graph)
    return topology


def classify_architectural_path(
    path: str,
) -> tuple[str, ArchitecturalLayer]:
    """Classify only explicit path structure and common architectural vocabulary."""

    parts = tuple(
        item.lower()
        for item in PurePosixPath(path).parts
        if item not in {"/", ""}
    )
    if not parts:
        return "unclassified", "unclassified"
    layer: ArchitecturalLayer = "unclassified"
    for candidate, vocabulary in _LAYER_SEGMENTS:
        tokens = {*parts, PurePosixPath(parts[-1]).stem}
        if vocabulary & tokens:
            layer = candidate
            break
    domain_parts = _domain_parts(parts)
    return "/".join(domain_parts) if domain_parts else "unclassified", layer


def validate_architectural_change_topology(
    topology: ArchitecturalChangeTopology,
    graph: ReviewStructuralGraph,
) -> None:
    topology.validate_against(graph)


def _domain_parts(parts: tuple[str, ...]) -> tuple[str, ...]:
    if parts[0] in {"test", "tests", "spec", "specs", "docs", ".github"}:
        return (parts[0],)
    if parts[0] in _SOURCE_ROOTS:
        code_parts = parts[1:-1]
        return code_parts[:2] or parts[1:2] or (parts[0],)
    return parts[:1]


def _component_id(domain: str, layer: str) -> str:
    digest = hashlib.sha256(f"{domain}\0{layer}".encode()).hexdigest()[:20]
    return f"AC:{digest}"


def _with_component_membership(
    components: tuple[ArchitecturalComponent, ...],
    relation_groups: tuple[StructuralRelationGroup, ...],
) -> tuple[ArchitecturalComponent, ...]:
    enriched = []
    for component in components:
        members = set(component.node_ids)
        internal_group_ids = []
        context_group_ids = []
        context_node_ids = set()
        for group in relation_groups:
            source_inside = group.source_node_id in members
            target_inside = group.target_node_id in members
            if source_inside and target_inside:
                internal_group_ids.append(group.id)
            elif source_inside != target_inside:
                context_group_ids.append(group.id)
                context_node_ids.add(
                    group.target_node_id if source_inside else group.source_node_id
                )
        enriched.append(
            replace(
                component,
                internal_relation_group_ids=tuple(sorted(internal_group_ids)),
                context_node_ids=tuple(sorted(context_node_ids)),
                context_relation_group_ids=tuple(sorted(context_group_ids)),
            )
        )
    return tuple(enriched)
