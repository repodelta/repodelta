from __future__ import annotations

import hashlib

from repodelta.model.contracts import (
    ArchitecturalChangeTopology,
    EvidenceCatalog,
    ReviewStructuralGraph,
    StructuralOverviewFile,
    StructuralOverviewFocus,
    StructuralOverviewProjection,
    StructuralOverviewRelation,
    VerificationWorkspace,
)


def project_structural_overview(
    graph: ReviewStructuralGraph,
    architecture: ArchitecturalChangeTopology,
    workspace: VerificationWorkspace,
    evidence_catalog: EvidenceCatalog,
) -> StructuralOverviewProjection:
    """Project compact file membership once for every presentation adapter."""

    result = _derive_structural_overview(
        graph, architecture, workspace, evidence_catalog
    )
    validate_structural_overview(
        result, graph, architecture, workspace, evidence_catalog
    )
    return result


def _derive_structural_overview(
    graph: ReviewStructuralGraph,
    architecture: ArchitecturalChangeTopology,
    workspace: VerificationWorkspace,
    evidence_catalog: EvidenceCatalog,
) -> StructuralOverviewProjection:
    """Derive one overview value from its three canonical authorities."""

    evidence = evidence_catalog.by_id()
    nodes = {item.id: item for item in graph.nodes}
    groups = {item.id: item for item in graph.relation_groups}
    edges = {item.id: item for item in graph.edges}
    backbone_nodes = {
        node_id: nodes[node_id] for node_id in graph.backbone_node_ids
    }
    backbone_groups = tuple(
        groups[group_id] for group_id in graph.backbone_relation_group_ids
    )
    file_node_ids = {
        node_id
        for node_id, node in backbone_nodes.items()
        if evidence[node.display_evidence_id].metadata.get("symbol_kind") == "file"
    }
    if not file_node_ids:
        return StructuralOverviewProjection(
            focuses=tuple(
                StructuralOverviewFocus(
                    subject_id=item.subject_id,
                    structural_disposition=item.structural_disposition,
                )
                for item in workspace.inspections
            )
        )

    placements = {item.id: item for item in graph.placements}
    primary_parent = {
        placements[placement_id].child_node_id: (
            placements[placement_id].parent_node_id
        )
        for placement_id in graph.primary_placement_ids
        if placement_id in placements
    }

    def owning_file(node_id: str) -> str | None:
        current = node_id
        visited = {current}
        while True:
            if current in file_node_ids:
                return current
            parent = primary_parent.get(current)
            if parent is None or parent in visited:
                return None
            visited.add(parent)
            current = parent

    file_by_node = {
        node_id: file_id
        for node_id in backbone_nodes
        if (file_id := owning_file(node_id)) is not None
    }
    members_by_file = {file_id: [] for file_id in file_node_ids}
    for node_id, file_id in file_by_node.items():
        if node_id != file_id:
            members_by_file[file_id].append(node_id)

    changed_file_ids = {
        file_id
        for file_id in file_node_ids
        if backbone_nodes[file_id].delta != "retained"
        or any(
            backbone_nodes[node_id].delta != "retained"
            for node_id in members_by_file[file_id]
        )
    }
    file_group_endpoints = {
        group.id: (
            file_by_node.get(group.source_node_id),
            file_by_node.get(group.target_node_id),
        )
        for group in backbone_groups
    }
    directed_pairs = {
        (source_file, target_file)
        for source_file, target_file in file_group_endpoints.values()
        if source_file is not None
        and target_file is not None
        and source_file != target_file
    }
    outgoing = {file_id: set() for file_id in file_node_ids}
    for source_file, target_file in directed_pairs:
        outgoing[source_file].add(target_file)

    retained_bridge_ids = _retained_bridges(changed_file_ids, outgoing)
    displayed_file_ids = changed_file_ids | retained_bridge_ids
    context_group_ids: dict[str, set[str]] = {}
    boundary_group_ids_by_displayed: dict[str, set[str]] = {
        file_id: set() for file_id in displayed_file_ids
    }
    context_files_by_displayed: dict[str, set[str]] = {
        file_id: set() for file_id in displayed_file_ids
    }
    for group_id, (source_file, target_file) in file_group_endpoints.items():
        if source_file is None or target_file is None or source_file == target_file:
            continue
        displayed_endpoint = (
            source_file
            if source_file in displayed_file_ids and target_file not in displayed_file_ids
            else target_file
            if target_file in displayed_file_ids and source_file not in displayed_file_ids
            else None
        )
        if displayed_endpoint is None:
            continue
        context_file = target_file if displayed_endpoint == source_file else source_file
        context_group_ids.setdefault(context_file, set()).add(group_id)
        boundary_group_ids_by_displayed[displayed_endpoint].add(group_id)
        context_files_by_displayed[displayed_endpoint].add(context_file)

    layer_by_node = {
        node_id: component.layer
        for component in architecture.components
        for node_id in component.node_ids
    }
    visible_group_ids_by_file = {
        file_id: set() for file_id in displayed_file_ids
    }
    exact_bundles: dict[tuple[str, str, str], list[str]] = {}
    for group in backbone_groups:
        source_file, target_file = file_group_endpoints[group.id]
        if (
            source_file not in displayed_file_ids
            or target_file not in displayed_file_ids
            or source_file == target_file
        ):
            continue
        exact_bundles.setdefault(
            (source_file, target_file, group.operation), []
        ).append(group.id)
        visible_group_ids_by_file[source_file].add(group.id)
        visible_group_ids_by_file[target_file].add(group.id)

    visual_bundles: dict[tuple[tuple[str, ...], str, str], list[str]] = {}
    for (source_file, target_file, operation), group_ids in exact_bundles.items():
        source_key = (
            ("__verification__",)
            if layer_by_node.get(source_file) == "verification"
            and layer_by_node.get(target_file) != "verification"
            else (source_file,)
        )
        visual_bundles.setdefault(
            (source_key, target_file, operation), []
        ).extend(group_ids)

    relation_items = []
    for (source_key, target_file, operation), group_ids in sorted(
        visual_bundles.items()
    ):
        source_files = tuple(sorted({
            file_group_endpoints[group_id][0]
            for group_id in group_ids
            if file_group_endpoints[group_id][0] is not None
        }))
        canonical_group_ids = tuple(sorted(set(group_ids)))
        member_edge_ids = tuple(sorted({
            edge_id
            for group_id in canonical_group_ids
            for edge_id in groups[group_id].member_edge_ids
        }))
        relations = tuple(sorted({
            groups[group_id].relation for group_id in canonical_group_ids
        }))
        relation_items.append(
            StructuralOverviewRelation(
                id=_overview_relation_id(
                    source_files,
                    target_file,
                    operation,
                    canonical_group_ids,
                ),
                source_file_node_ids=source_files,
                target_file_node_id=target_file,
                operation=operation,
                relations=relations,
                relation_group_ids=canonical_group_ids,
                member_edge_ids=member_edge_ids,
            )
        )

    file_items = tuple(
        StructuralOverviewFile(
            file_node_id=file_id,
            member_node_ids=tuple(sorted(members_by_file[file_id])),
            role=(
                "changed"
                if file_id in changed_file_ids
                else "retained_bridge"
                if file_id in retained_bridge_ids
                else "retained_context"
            ),
            lane=(
                "verification"
                if layer_by_node.get(file_id) == "verification"
                else "production"
            ),
            architectural_layer=layer_by_node.get(file_id, "unclassified"),
            relation_group_ids=tuple(sorted(
                (
                    visible_group_ids_by_file.get(file_id, set())
                    | boundary_group_ids_by_displayed.get(file_id, set())
                )
                if file_id in displayed_file_ids
                else context_group_ids.get(file_id, ())
            )),
            context_file_node_ids=tuple(sorted(
                context_files_by_displayed.get(file_id, ())
            )),
        )
        for file_id in sorted(displayed_file_ids | set(context_group_ids))
    )

    relation_id_by_group_id = {
        group_id: relation.id
        for relation in relation_items
        for group_id in relation.relation_group_ids
    }
    relation_by_id = {relation.id: relation for relation in relation_items}
    group_id_by_edge_id = {
        edge_id: group.id
        for group in groups.values()
        for edge_id in group.member_edge_ids
    }
    overview_files = {item.file_node_id: item for item in file_items}
    focus_items = []
    for inspection in workspace.inspections:
        direct_files = set()
        suggested_files = set()
        context_files = set()
        unresolved_files = set()
        for focus_node in inspection.structural_overlay.nodes:
            file_id = file_by_node.get(focus_node.node_id)
            if file_id not in overview_files:
                continue
            if focus_node.is_direct_mapping:
                direct_files.add(file_id)
            elif focus_node.is_suggested:
                suggested_files.add(file_id)
            elif focus_node.is_context:
                context_files.add(file_id)
            elif focus_node.is_unresolved:
                unresolved_files.add(file_id)
        overlay_group_ids = set(inspection.structural_overlay.relation_group_ids)
        overlay_group_ids.update(
            group_id
            for edge_id in inspection.structural_overlay.edge_ids
            if (group_id := group_id_by_edge_id.get(edge_id)) is not None
        )
        relation_ids = {
            relation_id_by_group_id[group_id]
            for group_id in overlay_group_ids
            if group_id in relation_id_by_group_id
        }
        # A focused exact relation can carry a file-level endpoint even when
        # the endpoint symbol is outside the displayed backbone. Preserve
        # that endpoint as structural context so changing provenance buckets
        # cannot silently change the selected file universe.
        for relation_id in relation_ids:
            relation = relation_by_id[relation_id]
            context_files.update(relation.source_file_node_ids)
            context_files.add(relation.target_file_node_id)
        context_files.difference_update(
            direct_files | suggested_files | unresolved_files
        )
        focus_items.append(
            StructuralOverviewFocus(
                subject_id=inspection.subject_id,
                direct_file_node_ids=tuple(sorted(direct_files)),
                suggested_file_node_ids=tuple(sorted(suggested_files)),
                context_file_node_ids=tuple(sorted(context_files)),
                unresolved_file_node_ids=tuple(sorted(unresolved_files)),
                relation_ids=tuple(sorted(relation_ids)),
                structural_disposition=inspection.structural_disposition,
            )
        )

    return StructuralOverviewProjection(
        files=file_items,
        relations=tuple(relation_items),
        focuses=tuple(focus_items),
    )


def _retained_bridges(
    changed_file_ids: set[str],
    outgoing: dict[str, set[str]],
) -> set[str]:
    retained_bridges: set[str] = set()
    for source in changed_file_ids:
        reachable_retained: set[str] = set()
        pending = list(outgoing.get(source, ()))
        while pending:
            candidate = pending.pop()
            if candidate in changed_file_ids or candidate in reachable_retained:
                continue
            reachable_retained.add(candidate)
            pending.extend(outgoing.get(candidate, ()))
        for candidate in reachable_retained:
            visited = {candidate}
            candidate_pending = list(outgoing.get(candidate, ()))
            while candidate_pending:
                target = candidate_pending.pop()
                if target in changed_file_ids:
                    if target != source:
                        retained_bridges.add(candidate)
                    break
                if target in visited:
                    continue
                visited.add(target)
                candidate_pending.extend(outgoing.get(target, ()))
    return retained_bridges


def _overview_relation_id(
    source_file_ids: tuple[str, ...],
    target_file_id: str,
    operation: str,
    group_ids: tuple[str, ...],
) -> str:
    identity = "\0".join((*source_file_ids, target_file_id, operation, *group_ids))
    return f"SOR:{hashlib.sha256(identity.encode()).hexdigest()[:20]}"


def validate_structural_overview(
    overview: StructuralOverviewProjection,
    graph: ReviewStructuralGraph,
    architecture: ArchitecturalChangeTopology,
    workspace: VerificationWorkspace,
    evidence_catalog: EvidenceCatalog,
) -> None:
    """Reject overview members that escape their canonical authorities."""

    if overview.schema_version != "structural_overview.v2":
        raise ValueError("unsupported structural overview schema")
    files = overview.files_by_id()
    if len(files) != len(overview.files):
        raise ValueError("structural overview contains duplicate files")
    relations = {item.id: item for item in overview.relations}
    if len(relations) != len(overview.relations):
        raise ValueError("structural overview contains duplicate relations")
    focuses = overview.focuses_by_subject_id()
    if len(focuses) != len(overview.focuses):
        raise ValueError("structural overview contains duplicate focuses")
    graph_nodes = {item.id: item for item in graph.nodes}
    backbone_nodes = set(graph.backbone_node_ids)
    graph_groups = {item.id: item for item in graph.relation_groups}
    backbone_groups = set(graph.backbone_relation_group_ids)
    graph_edges = {item.id for item in graph.edges}
    evidence = evidence_catalog.by_id()
    architecture_nodes = {
        node_id for component in architecture.components for node_id in component.node_ids
    }
    for item in overview.files:
        node = graph_nodes.get(item.file_node_id)
        if (
            node is None
            or item.file_node_id not in backbone_nodes
            or evidence[node.display_evidence_id].metadata.get("symbol_kind") != "file"
        ):
            raise ValueError("structural overview references a non-canonical file")
        if not set(item.member_node_ids) <= backbone_nodes:
            raise ValueError("structural overview file contains non-canonical members")
        if item.file_node_id not in architecture_nodes:
            raise ValueError("structural overview file lacks architectural authority")
        expected_layer = next(
            component.layer
            for component in architecture.components
            if item.file_node_id in component.node_ids
        )
        if item.architectural_layer != expected_layer:
            raise ValueError("structural overview changed architectural layer")
        if not set(item.relation_group_ids) <= backbone_groups:
            raise ValueError("structural overview file references non-backbone relations")
        if not set(item.context_file_node_ids) <= set(files):
            raise ValueError("structural overview file references unknown context files")
    visible_files = {
        item.file_node_id
        for item in overview.files
        if item.role != "retained_context"
    }
    for item in overview.relations:
        if (
            not set(item.source_file_node_ids) <= visible_files
            or item.target_file_node_id not in visible_files
            or not item.source_file_node_ids
        ):
            raise ValueError("structural overview relation escapes visible files")
        if not set(item.relation_group_ids) <= backbone_groups:
            raise ValueError("structural overview relation is not canonical")
        expected_edges = {
            edge_id
            for group_id in item.relation_group_ids
            for edge_id in graph_groups[group_id].member_edge_ids
        }
        if set(item.member_edge_ids) != expected_edges or not expected_edges <= graph_edges:
            raise ValueError("structural overview relation changed exact members")
        if {graph_groups[group_id].operation for group_id in item.relation_group_ids} != {
            item.operation
        }:
            raise ValueError("structural overview relation changed operation")
        if {graph_groups[group_id].relation for group_id in item.relation_group_ids} != set(
            item.relations
        ):
            raise ValueError("structural overview relation changed relation kinds")
    expected_focus_ids = tuple(item.subject_id for item in workspace.inspections)
    if tuple(item.subject_id for item in overview.focuses) != expected_focus_ids:
        raise ValueError("structural overview must preserve every focus once")
    for item in overview.focuses:
        inspection = workspace.inspections_by_subject_id()[item.subject_id]
        if item.structural_disposition != inspection.structural_disposition:
            raise ValueError("structural overview changed focus disposition")
        if not set(item.selected_file_node_ids) <= set(files):
            raise ValueError("structural overview focus references unknown files")
        if not set(item.relation_ids) <= set(relations):
            raise ValueError("structural overview focus references unknown relations")
    expected = _derive_structural_overview(
        graph, architecture, workspace, evidence_catalog
    )
    if overview != expected:
        raise ValueError("structural overview diverges from canonical authorities")
