from __future__ import annotations

import hashlib
from pathlib import PurePosixPath

from prismcode.model.contracts import (
    ArchitecturalChangeTopology,
    ArchitecturalComponent,
    ArchitecturalFlow,
    ArchitecturalLayer,
    ArchitecturalOperationCount,
    ArchitecturalSubjectOverlay,
    EvidenceCatalog,
    StructuralGraphNode,
    StructuralFocusOverlay,
    ReviewStructuralGraph,
    architectural_flow_kind,
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
            operation_counts=_operation_counts(node_ids, nodes),
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
    components_by_id = {item.id: item for item in components}
    grouped_flows: dict[tuple[str, str, str, str], list[str]] = {}
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
            (
                source_component_id,
                target_component_id,
                architectural_flow_kind(
                    group.relation,
                    components_by_id[source_component_id].layer,
                    components_by_id[target_component_id].layer,
                ),
                group.operation,
            ),
            [],
        ).append(group_id)

    flows = tuple(
        ArchitecturalFlow(
            id=_flow_id(source_id, target_id, kind, operation),
            source_component_id=source_id,
            target_component_id=target_id,
            kind=kind,
            operation=operation,
            relations=tuple(
                sorted({relation_groups[item].relation for item in group_ids})
            ),
            relation_group_ids=tuple(sorted(group_ids)),
        )
        for (source_id, target_id, kind, operation), group_ids in sorted(
            grouped_flows.items()
        )
    )
    topology = ArchitecturalChangeTopology(
        components=components,
        flows=flows,
        display_component_ids=_display_component_ids(components, flows),
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


def project_architectural_subject_overlay(
    topology: ArchitecturalChangeTopology,
    structural_overlay: StructuralFocusOverlay,
) -> ArchitecturalSubjectOverlay:
    """Join one canonical subject overlay to existing component and flow IDs."""

    component_by_node = {
        node_id: component.id
        for component in topology.components
        for node_id in component.node_ids
    }
    direct_node_ids = {
        item.node_id for item in structural_overlay.nodes if item.role != "intermediate"
    }
    context_node_ids = {
        item.node_id for item in structural_overlay.nodes if item.role == "intermediate"
    }
    direct_components = {
        component_by_node[item]
        for item in direct_node_ids
        if item in component_by_node
    }
    context_components = {
        component_by_node[item]
        for item in context_node_ids
        if item in component_by_node
    }
    overlay_groups = set(structural_overlay.relation_group_ids)
    flow_ids = []
    for flow in topology.flows:
        if not overlay_groups.intersection(flow.relation_group_ids):
            continue
        flow_ids.append(flow.id)
        context_components.update(
            (flow.source_component_id, flow.target_component_id)
        )
    context_components -= direct_components
    order = {item: index for index, item in enumerate(topology.display_component_ids)}
    return ArchitecturalSubjectOverlay(
        component_ids=tuple(sorted(direct_components, key=order.__getitem__)),
        context_component_ids=tuple(
            sorted(context_components, key=order.__getitem__)
        ),
        flow_ids=tuple(flow_ids),
    )


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


def _flow_id(source_id: str, target_id: str, kind: str, operation: str) -> str:
    digest = hashlib.sha256(
        f"{source_id}\0{target_id}\0{kind}\0{operation}".encode()
    ).hexdigest()[:20]
    return f"AF:{digest}"


def _operation_counts(
    node_ids: list[str],
    nodes: dict[str, StructuralGraphNode],
) -> tuple[ArchitecturalOperationCount, ...]:
    counts: dict[str, int] = {}
    for node_id in node_ids:
        operation = nodes[node_id].delta
        counts[operation] = counts.get(operation, 0) + 1
    order = ("added", "modified", "renamed", "removed", "retained", "unresolved")
    return tuple(
        ArchitecturalOperationCount(operation=operation, count=counts[operation])
        for operation in order
        if operation in counts
    )


def _display_component_ids(
    components: tuple[ArchitecturalComponent, ...],
    flows: tuple[ArchitecturalFlow, ...],
) -> tuple[str, ...]:
    """Order executable roots before consumers; retain stable order for cycles."""

    components_by_id = {item.id: item for item in components}
    component_ids = set(components_by_id)
    outgoing = {item: set() for item in component_ids}
    indegree = {item: 0 for item in component_ids}
    for flow in flows:
        if flow.kind != "executable" or flow.target_component_id in outgoing[
            flow.source_component_id
        ]:
            continue
        outgoing[flow.source_component_id].add(flow.target_component_id)
        indegree[flow.target_component_id] += 1
    def order_key(component_id: str) -> tuple[int, int, str]:
        return _component_order_key(components_by_id[component_id])
    ready = sorted(
        (item for item, count in indegree.items() if count == 0),
        key=order_key,
    )
    ordered = []
    while ready:
        component_id = ready.pop(0)
        ordered.append(component_id)
        for target_id in sorted(outgoing[component_id], key=order_key):
            indegree[target_id] -= 1
            if indegree[target_id] == 0:
                ready.append(target_id)
                ready.sort(key=order_key)
    ordered.extend(sorted(component_ids - set(ordered), key=order_key))
    return tuple(ordered)


def _component_order_key(component: ArchitecturalComponent) -> tuple[int, int, str]:
    layer_order = {
        "entry": 0,
        "presentation": 1,
        "application": 2,
        "domain": 3,
        "infrastructure": 4,
        "persistence": 5,
        "unclassified": 6,
        "verification": 7,
        "documentation": 8,
        "automation": 9,
    }
    support = component.layer in {"verification", "documentation", "automation"}
    return (1 if support else 0, layer_order[component.layer], component.domain)
