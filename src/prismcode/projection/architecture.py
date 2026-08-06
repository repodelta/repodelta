from __future__ import annotations

import hashlib
from pathlib import PurePosixPath

from prismcode.model.contracts import (
    ArchitecturalChangeTopology,
    ArchitecturalComponent,
    ArchitecturalFlow,
    ArchitecturalLayer,
    EvidenceCatalog,
    ReviewStructuralGraph,
)


_SOURCE_ROOTS = {"src", "lib", "app", "packages"}
_LAYER_SEGMENTS: tuple[tuple[ArchitecturalLayer, frozenset[str]], ...] = (
    ("verification", frozenset({"test", "tests", "spec", "specs"})),
    ("documentation", frozenset({"doc", "docs", "documentation"})),
    ("automation", frozenset({".github", "ci", "workflows"})),
    ("entry", frozenset({"cli", "entrypoint", "entrypoints"})),
    ("presentation", frozenset({"presentation", "ui", "views", "web"})),
    ("application", frozenset({"application", "orchestration", "pipeline"})),
    ("domain", frozenset({"domain", "model", "semantics", "assessment"})),
    (
        "infrastructure",
        frozenset({"provider", "providers", "adapter", "adapters", "client", "clients"}),
    ),
    (
        "persistence",
        frozenset({"storage", "database", "db", "persistence", "repositories"}),
    ),
)


def project_architectural_change_topology(
    graph: ReviewStructuralGraph,
    evidence_catalog: EvidenceCatalog,
) -> ArchitecturalChangeTopology:
    """Aggregate one canonical graph into path-bounded components and flows."""

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
    component_by_node = {
        node_id: component.id
        for component in components
        for node_id in component.node_ids
    }
    grouped_flows: dict[tuple[str, str, str], list[str]] = {}
    for group_id in graph.backbone_relation_group_ids:
        group = relation_groups[group_id]
        source_component_id = component_by_node.get(group.source_node_id)
        target_component_id = component_by_node.get(group.target_node_id)
        if (
            source_component_id is None
            or target_component_id is None
            or source_component_id == target_component_id
        ):
            continue
        grouped_flows.setdefault(
            (source_component_id, target_component_id, group.operation), []
        ).append(group_id)

    flows = tuple(
        ArchitecturalFlow(
            id=_flow_id(source_id, target_id, operation),
            source_component_id=source_id,
            target_component_id=target_id,
            operation=operation,
            relation_group_ids=tuple(sorted(group_ids)),
        )
        for (source_id, target_id, operation), group_ids in sorted(
            grouped_flows.items()
        )
    )
    topology = ArchitecturalChangeTopology(components=components, flows=flows)
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


def _flow_id(source_id: str, target_id: str, operation: str) -> str:
    digest = hashlib.sha256(
        f"{source_id}\0{target_id}\0{operation}".encode()
    ).hexdigest()[:20]
    return f"AF:{digest}"
