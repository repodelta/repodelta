from __future__ import annotations

from dataclasses import replace

import pytest

from repodelta.model.contracts import (
    EvidenceCatalog,
    EvidenceItem,
    ReviewStructuralGraph,
    StructuralFocusDisposition,
    StructuralFocusMembership,
    StructuralFocusOverlay,
    StructuralFocusProvenance,
    StructuralGraphEdge,
    StructuralGraphNode,
    StructuralRelationGroup,
    VerificationEvidenceInspection,
    VerificationWorkspace,
)
from repodelta.projection.architecture import project_architectural_change_topology
from repodelta.projection.structural_overview import (
    project_structural_overview,
    validate_structural_overview,
)


def _focus_member(kind, identity, membership_class, role):
    return StructuralFocusMembership(
        member_kind=kind,
        member_id=identity,
        membership_class=membership_class,
        structural_role=role,
        provenance=(
            StructuralFocusProvenance(
                producer="test_fixture",
                admission_class=membership_class,
                source_ids=(identity,),
            ),
        ),
    )


def _overview_fixture() -> tuple[
    ReviewStructuralGraph,
    EvidenceCatalog,
    VerificationWorkspace,
]:
    paths = {
        "A": "src/application/a.py",
        "B": "src/domain/b.py",
        "C": "src/infrastructure/c.py",
        "D": "src/domain/adjacent.py",
    }
    evidence = EvidenceCatalog(items=tuple(
        EvidenceItem(
            id=f"F:{node_id}",
            summary=path,
            kind="symbol",
            classification="code",
            metadata={"path": path, "qualified_name": path, "symbol_kind": "file"},
        )
        for node_id, path in paths.items()
    ))
    nodes = tuple(
        StructuralGraphNode(
            id=f"N:{node_id}",
            review_symbol_id=node_id,
            delta=delta,
            evidence_ids=(f"F:{node_id}",),
            display_evidence_id=f"F:{node_id}",
        )
        for node_id, delta in (
            ("A", "modified"),
            ("B", "retained"),
            ("C", "modified"),
            ("D", "retained"),
        )
    )

    def edge(source: str, target: str) -> StructuralGraphEdge:
        return StructuralGraphEdge(
            id=f"E:{source}:{target}",
            source_node_id=f"N:{source}",
            target_node_id=f"N:{target}",
            relation="calls",
            operation="retained",
            relation_change_evidence_id=f"RC:{source}:{target}",
        )

    edges = (edge("A", "B"), edge("B", "C"), edge("A", "D"))
    groups = tuple(
        StructuralRelationGroup(
            id=f"G:{item.id}",
            source_node_id=item.source_node_id,
            target_node_id=item.target_node_id,
            relation=item.relation,
            operation=item.operation,
            member_edge_ids=(item.id,),
        )
        for item in edges
    )
    graph = ReviewStructuralGraph(
        nodes=nodes,
        edges=edges,
        relation_groups=groups,
        backbone_node_ids=tuple(item.id for item in nodes),
        backbone_edge_ids=tuple(item.id for item in edges),
        backbone_relation_group_ids=tuple(item.id for item in groups),
    )
    workspace = VerificationWorkspace(inspections=(
        VerificationEvidenceInspection(
            id="VEI:R1",
            subject_id="R1",
            structural_overlay=StructuralFocusOverlay(memberships=(
                _focus_member("node", "N:A", "matched", "changed_anchor"),
                _focus_member("node", "N:B", "context", "connector"),
                _focus_member("node", "N:C", "context", "runtime_context"),
                _focus_member("edge", "E:A:B", "context", "relation_endpoint"),
                _focus_member("edge", "E:B:C", "context", "relation_endpoint"),
                _focus_member(
                    "relation_group",
                    "G:E:A:B",
                    "context",
                    "relation_endpoint",
                ),
                _focus_member(
                    "relation_group",
                    "G:E:B:C",
                    "context",
                    "relation_endpoint",
                ),
            )),
            structural_disposition=StructuralFocusDisposition(state="projected"),
        ),
        VerificationEvidenceInspection(
            id="VEI:G1",
            subject_id="G1",
            structural_disposition=StructuralFocusDisposition(
                state="not_applicable"
            ),
        ),
    ))
    return graph, evidence, workspace


def test_overview_preserves_retained_bridge_but_not_adjacent_context() -> None:
    graph, evidence, workspace = _overview_fixture()
    architecture = project_architectural_change_topology(graph, evidence)

    overview = project_structural_overview(
        graph, architecture, workspace, evidence
    )

    files = overview.files_by_id()
    assert files["N:A"].role == "changed"
    assert files["N:B"].role == "retained_bridge"
    assert files["N:C"].role == "changed"
    assert files["N:D"].role == "retained_context"
    assert {item.target_file_node_id for item in overview.relations} == {
        "N:B",
        "N:C",
    }
    assert {edge_id for item in overview.relations for edge_id in item.member_edge_ids} == {
        "E:A:B",
        "E:B:C",
    }
    focus = overview.focuses_by_subject_id()["R1"]
    assert set(focus.direct_file_node_ids) == {"N:A"}
    assert set(focus.context_file_node_ids) == {"N:B", "N:C"}
    assert overview.focuses_by_subject_id()["G1"].structural_disposition.state == (
        "not_applicable"
    )


def test_overview_validation_rejects_changed_exact_relation_members() -> None:
    graph, evidence, workspace = _overview_fixture()
    architecture = project_architectural_change_topology(graph, evidence)
    overview = project_structural_overview(
        graph, architecture, workspace, evidence
    )
    invalid = replace(
        overview,
        relations=(
            replace(overview.relations[0], member_edge_ids=("E:A:D",)),
            *overview.relations[1:],
        ),
    )

    with pytest.raises(ValueError, match="changed exact members"):
        validate_structural_overview(
            invalid, graph, architecture, workspace, evidence
        )


def test_overview_validation_rejects_renderer_owned_role_override() -> None:
    graph, evidence, workspace = _overview_fixture()
    architecture = project_architectural_change_topology(graph, evidence)
    overview = project_structural_overview(
        graph, architecture, workspace, evidence
    )
    bridge_index = next(
        index
        for index, item in enumerate(overview.files)
        if item.file_node_id == "N:B"
    )
    files = list(overview.files)
    files[bridge_index] = replace(files[bridge_index], role="changed")

    with pytest.raises(ValueError, match="diverges from canonical authorities"):
        validate_structural_overview(
            replace(overview, files=tuple(files)),
            graph,
            architecture,
            workspace,
            evidence,
        )
