from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from prismcode.pipeline import DeterministicAnalyzer
from prismcode.model.contracts import (
    ArchitecturalChangeTopology,
    ArchitecturalComponent,
    ArchitecturalFlow,
    ArchitecturalOperationCount,
    AnalysisInput,
    CandidateConvergence,
    CanonicalChangeMapEntry,
    ChangedFile,
    ConvergenceGroup,
    EvidenceCatalog,
    EvidenceItem,
    ObservedTransformation,
    ProjectionCandidateGroup,
    ProjectionCandidateSet,
    ProjectionRelation,
    Requirement,
    ReviewProjection,
    ReviewSlice,
    ReviewSourcePacket,
    ReviewStatement,
    ReviewStructuralGraph,
    SourceRecord,
    StructuralChangeIdentity,
    StructuralCoverage,
    StructuralFocusNode,
    StructuralFocusDisposition,
    StructuralFocusOverlay,
    StructuralGraphEdge,
    StructuralGraphNode,
    StructuralGraphPlacement,
    StructuralRelationGroup,
    StructuralOwnershipChangeIdentity,
    StructuralOwnershipIdentity,
    StructuralRelationChangeIdentity,
    TransformationAlignment,
    TransformationAssessment,
    TransformationContract,
    TransformationStructuralClosure,
    TransformationStructuralTopologyGroup,
    VerificationIdentity,
    architectural_flow_kind,
)
from prismcode.projection.architecture import (
    classify_architectural_path,
    project_architectural_change_topology,
    validate_architectural_change_topology,
)
from prismcode.evaluation.core import load_evaluation_suite
from prismcode.facts.lexical import association_signature
from prismcode.intake.fixture import load_fixture
from prismcode.routing.candidates import build_projection_candidates
from prismcode.routing.semantics import (
    focus_evidence_role,
    requirement_profile,
)
from prismcode.convergence.core import (
    ConvergencePolicy,
    converge_candidates,
)
from prismcode.projection.build import (
    _canonical_backbone_seed_node_ids,
    _change_backbone,
    _display_evidence_id,
    _merge_node,
    _structural_node_id,
    _support_node_delta,
    build_review_projection,
)
from prismcode.projection.overview import project_diagnostic_presentation
from prismcode.projection.structural_groups import (
    project_structural_relation_groups,
)
from prismcode.presentation.html import (
    _architectural_change_topology,
    _review_graph,
    _structural_compound_layout,
    _structural_edge_path,
    render_html,
)
from prismcode.providers.structural import (
    StructuralGraphCollection,
    StructuralGraphIndexStatus,
    StructuralGraphResult,
)


def _with_verification_overlays(projection: ReviewProjection) -> SimpleNamespace:
    return SimpleNamespace(
        verification_workspace=SimpleNamespace(
            inspections=tuple(
                SimpleNamespace(
                    subject_id=item.change_map.focus_statement_id,
                    structural_overlay=item.change_map.structural_overlay,
                )
                for item in projection.slices
            )
        )
    )


SUITE = Path("fixtures/evaluation-suite.json")


def _architectural_node(node_id: str, evidence_id: str) -> StructuralGraphNode:
    return StructuralGraphNode(
        id=node_id,
        review_symbol_id=f"RS:{node_id}",
        delta="modified",
        evidence_ids=(evidence_id,),
        display_evidence_id=evidence_id,
    )


def test_architectural_topology_groups_canonical_nodes_and_cross_component_flow() -> None:
    cli = _architectural_node("N:cli", "E:cli")
    provider = _architectural_node("N:provider", "E:provider")
    relation = StructuralRelationGroup(
        id="RG:call",
        source_node_id=cli.id,
        target_node_id=provider.id,
        relation="calls",
        operation="added",
        member_edge_ids=("E:edge",),
    )
    dependency = StructuralRelationGroup(
        id="RG:import",
        source_node_id=cli.id,
        target_node_id=provider.id,
        relation="imports",
        operation="retained",
        member_edge_ids=("E:import",),
    )
    graph = ReviewStructuralGraph(
        nodes=(cli, provider),
        relation_groups=(relation, dependency),
        backbone_node_ids=(cli.id, provider.id),
        backbone_relation_group_ids=(relation.id, dependency.id),
    )
    evidence = EvidenceCatalog(
        items=(
            EvidenceItem(
                id="E:cli",
                summary="CLI",
                kind="symbol",
                classification="code",
                metadata={"path": "src/prismcode/cli.py"},
            ),
            EvidenceItem(
                id="E:provider",
                summary="Provider",
                kind="symbol",
                classification="code",
                metadata={"path": "src/prismcode/providers/openai.py"},
            ),
        )
    )

    topology = project_architectural_change_topology(graph, evidence)

    assert [(item.domain, item.layer) for item in topology.components] == [
        ("prismcode", "entry"),
        ("prismcode/providers", "infrastructure"),
    ]
    flows = {item.kind: item for item in topology.flows}
    assert {item: flow.relations for item, flow in flows.items()} == {
        "executable": ("calls",),
        "dependency": ("imports",),
    }
    assert flows["executable"].relation_group_ids == (relation.id,)
    assert flows["dependency"].relation_group_ids == (dependency.id,)
    ordered = {item.id: item.domain for item in topology.components}
    assert tuple(ordered[item] for item in topology.display_component_ids) == (
        "prismcode",
        "prismcode/providers",
    )
    assert all(
        item.operation_counts == (
            ArchitecturalOperationCount(operation="modified", count=1),
        )
        for item in topology.components
    )

    html = _architectural_change_topology(
        SimpleNamespace(
            projection=SimpleNamespace(architectural_topology=topology)
        )
    )
    assert html.count("<h2>Change topology</h2>") == 1
    assert "Executable flow" in html
    assert "Dependency and structural support · 1" in html
    assert "calls · 1 groups · added" in html
    assert "imports · 1 groups · retained" in html

    invalid = replace(
        topology,
        flows=tuple(
            replace(item, kind="executable")
            if item.kind == "dependency"
            else item
            for item in topology.flows
        ),
    )
    with pytest.raises(ValueError, match="flow kind"):
        validate_architectural_change_topology(invalid, graph)


def test_architectural_path_keeps_unknown_semantics_unclassified() -> None:
    assert classify_architectural_path("custom/opaque/worker.py") == (
        "custom",
        "unclassified",
    )


def test_architectural_flow_keeps_verification_out_of_production_flow() -> None:
    assert architectural_flow_kind("calls", "verification", "domain") == (
        "verification_support"
    )
    assert architectural_flow_kind("imports", "verification", "domain") == (
        "verification_support"
    )
    assert architectural_flow_kind("calls", "application", "domain") == (
        "executable"
    )


def test_architectural_topology_rejects_missing_backbone_membership() -> None:
    graph = ReviewStructuralGraph(
        nodes=(_architectural_node("N:one", "E:one"),),
        backbone_node_ids=("N:one",),
    )
    invalid = ArchitecturalChangeTopology(
        components=(
            ArchitecturalComponent(
                id="AC:missing",
                domain="unknown",
                layer="unclassified",
                node_ids=("N:missing",),
                operation_counts=(
                    ArchitecturalOperationCount(operation="modified", count=1),
                ),
                classification_authority="path_structure",
            ),
        ),
        display_component_ids=("AC:missing",),
    )

    with pytest.raises(ValueError, match="complete backbone"):
        validate_architectural_change_topology(invalid, graph)


def test_architectural_topology_rejects_relabelled_flow_endpoints() -> None:
    left = _architectural_node("N:left", "E:left")
    right = _architectural_node("N:right", "E:right")
    relation = StructuralRelationGroup(
        id="RG:call",
        source_node_id=left.id,
        target_node_id=right.id,
        relation="calls",
        operation="added",
        member_edge_ids=("E:edge",),
    )
    graph = ReviewStructuralGraph(
        nodes=(left, right),
        relation_groups=(relation,),
        backbone_node_ids=(left.id, right.id),
        backbone_relation_group_ids=(relation.id,),
    )
    source = ArchitecturalComponent(
        id="AC:left",
        domain="left",
        layer="unclassified",
        node_ids=(left.id,),
        operation_counts=(
            ArchitecturalOperationCount(operation="modified", count=1),
        ),
        classification_authority="path_structure",
    )
    target = ArchitecturalComponent(
        id="AC:right",
        domain="right",
        layer="unclassified",
        node_ids=(right.id,),
        operation_counts=(
            ArchitecturalOperationCount(operation="modified", count=1),
        ),
        classification_authority="path_structure",
    )
    invalid = ArchitecturalChangeTopology(
        components=(source, target),
        flows=(
            ArchitecturalFlow(
                id="AF:reversed",
                source_component_id=target.id,
                target_component_id=source.id,
                kind="executable",
                operation="added",
                relations=("calls",),
                relation_group_ids=(relation.id,),
            ),
        ),
        display_component_ids=(source.id, target.id),
    )

    with pytest.raises(ValueError, match="canonical relation endpoints"):
        validate_architectural_change_topology(invalid, graph)


def test_compound_layout_keeps_every_canonical_membership_for_moved_symbol() -> None:
    nodes = tuple(
        StructuralGraphNode(
            id=f"N:{name}",
            review_symbol_id=name,
            delta="modified",
            evidence_ids=(),
            display_evidence_id=f"E:{name}",
        )
        for name in ("old-parent", "new-parent", "child")
    )
    removed = StructuralGraphPlacement(
        id="P:old",
        parent_node_id="N:old-parent",
        child_node_id="N:child",
        base_ownership_evidence_ids=("E:removed",),
    )
    added = StructuralGraphPlacement(
        id="P:new",
        parent_node_id="N:new-parent",
        child_node_id="N:child",
        head_ownership_evidence_ids=("E:added",),
    )

    layout = _structural_compound_layout(
        nodes,
        (),
        (removed, added),
        primary_placement_ids=("P:new",),
    )

    assert set(layout.positions) == {item.id for item in nodes}
    assert tuple(item.id for item in layout.secondary_placements) == ("P:old",)
    assert {item.node_id for item in layout.containers} == {"N:new-parent"}


def _build_projection(
    candidates: ProjectionCandidateSet,
    convergence: CandidateConvergence,
    evidence: EvidenceCatalog,
    **kwargs,
) -> ReviewProjection:
    return build_review_projection(
        candidates,
        convergence,
        evidence,
        diagnostic_presentation=project_diagnostic_presentation(
            candidates,
            convergence,
        ),
        focus_statements=(),
        transformation_contract=TransformationContract(),
        observed_transformation=ObservedTransformation(),
        transformation_structural_closure=TransformationStructuralClosure(),
        transformation_alignment=TransformationAlignment(),
        transformation_assessment=TransformationAssessment(),
        **kwargs,
    )


def _head_graph(**values) -> StructuralGraphCollection:
    return StructuralGraphCollection(
        revisions=(StructuralGraphResult(**values),)
    )


def _selected_targets(brief, focus_id: str, slot: str) -> tuple[str, ...]:
    selected = set(brief.candidate_convergence.selected_relation_ids())
    return tuple(
        item.target_id
        for item in brief.projection_candidates.relations
        if item.focus_statement_id == focus_id
        and item.slot == slot
        and item.id in selected
    )




@pytest.mark.parametrize(
    ("focus_profile", "fact_profile", "expected"),
    (
        ("documentation", "document", "primary"),
        ("generic", "document", "document_support"),
        ("test_verification", "test", "primary"),
        ("behavior", "test", "test_support"),
        ("generic", "production", "primary"),
        ("workflow_configuration", "workflow", "primary"),
    ),
)
def test_focus_evidence_role_uses_typed_focus_and_fact_profiles(
    focus_profile,
    fact_profile,
    expected,
) -> None:
    assert focus_evidence_role(focus_profile, fact_profile) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        ("Document bounded_trace behavior", "documentation"),
        ("Documentation explains bounded_trace", "documentation"),
        ("Tests verify bounded_trace", "test_verification"),
        ("Verify bounded_trace behavior", "test_verification"),
        ("A document fact remains supporting evidence", "generic"),
        ("A test fact remains supporting evidence", "generic"),
        ("Documentation and test focus profiles retain typed roles", "generic"),
        ("Display document and test support in HTML", "ui"),
    ),
)
def test_requirement_profile_uses_intent_not_incidental_fact_nouns(
    text,
    expected,
) -> None:
    assert requirement_profile(Requirement(id="R1", text=text)) == expected


def test_direct_hunks_and_claim_route_into_independent_slots() -> None:
    brief = DeterministicAnalyzer().analyze(
        load_fixture("fixtures/evaluation/direct-hunk.json")
    )

    assert _selected_targets(brief, "R1", "claim") == ("C1",)
    assert set(_selected_targets(brief, "R1", "changed_anchor")) == {
        "E:change_relation:0e16ce839a33fc1c55dd",
        "E:change_relation:b41461fdd711f642d363",
    }
    assert _selected_targets(brief, "R2", "claim") == ()
    assert _selected_targets(brief, "R2", "changed_anchor") == ()
    assert {
        (item.slot, item.state)
        for item in brief.projection_candidates.diagnostics
        if item.focus_statement_id == "R2"
    } >= {
        ("claim", "no_association"),
        ("changed_anchor", "no_association"),
    }


def test_codegraph_context_only_expands_selected_exact_anchor() -> None:
    suite = load_evaluation_suite(SUITE)
    case = next(item for item in suite.cases if item.id == "bounded-y-x-z")
    analysis_input = replace(
        load_fixture(case.fixture),
        structural_graph=case.structural_graph,
    )
    brief = DeterministicAnalyzer().analyze(analysis_input)

    assert _selected_targets(brief, "R1", "changed_anchor") == (
        "E:structural_change:e3a262c5dc2f418b1bf4",
    )
    assert _selected_targets(brief, "R1", "runtime_context") == (
        "E:symbol:51c78d1cf2a276cc9a40",
    )
    assert _selected_targets(brief, "R1", "test_context") == (
        "E:symbol:3c8a35c2cab106b983ca",
    )
    selected_paths = _selected_targets(brief, "R1", "structural_path")
    anchor = brief.evidence_catalog.by_id()[
        "E:symbol:9e703e599343229d97c1"
    ]
    assert set(selected_paths) <= set(anchor.structural_path_ids)
    overlay = brief.projection.slices[0].change_map.structural_overlay
    graph = brief.projection.review_graph
    assert [item.role for item in overlay.nodes] == ["changed_anchor"]
    assert overlay.path_relation_ids == ()
    assert graph.edges == ()
    assert graph.nodes[0].review_symbol_id == "E:review_symbol:739129a16c60a7fa48f8"
    assert graph.nodes[0].evidence_ids == (
        "E:structural_change:e3a262c5dc2f418b1bf4",
        "E:symbol:9e703e599343229d97c1",
    )
    html = render_html(brief)
    assert html.count("Structural delta graph") == 1
    assert html.index("Verification") < html.index("Structural delta graph")
    assert (
            "1 backbone nodes · 0 support nodes · "
            "0 backbone relation groups · 0 canonical executable edges · "
            "0 structural placements · "
            "0 ownership deltas · "
            "1 isolated changed anchor"
    ) in html
    assert 'data-verification-subject="R1"' in html
    assert 'class="delta-canvas"' not in html
    assert '<details class="isolated-anchors">' in html
    assert "No safe canonical relation delta is available." in html
    assert '<span class="block-title">Structural paths</span>' not in html
    assert "No associated canonical evidence." not in html
    assert '<span class="block-title">Structural overlay</span>' not in html


def test_identical_focus_graphs_share_one_review_graph() -> None:
    suite = load_evaluation_suite(SUITE)
    case = next(item for item in suite.cases if item.id == "bounded-y-x-z")
    base = load_fixture(case.fixture)
    requirement = base.requirements[0]
    brief = DeterministicAnalyzer().analyze(
        replace(
            base,
            requirements=(
                replace(requirement, id="R1"),
                replace(requirement, id="R2"),
            ),
            structural_graph=case.structural_graph,
        )
    )

    graph = brief.projection.review_graph
    first, second = brief.projection.slices
    assert len(graph.nodes) == 1
    assert len(graph.edges) == 0
    assert tuple(item.node_id for item in first.change_map.structural_overlay.nodes) == tuple(
        item.node_id for item in second.change_map.structural_overlay.nodes
    )
    assert first.change_map.structural_overlay.edge_ids == second.change_map.structural_overlay.edge_ids
    assert first.change_map.structural_overlay.path_relation_ids == ()
    assert second.change_map.structural_overlay.path_relation_ids == ()
    html = render_html(brief)
    assert html.count("Structural delta graph") == 1
    assert html.count('<div class="isolated-anchor operation-unresolved"') == 1
    assert 'data-verification-subject="R1"' in html
    assert 'data-verification-subject="R2"' in html
    assert "Structural overlay" not in html


def test_canonical_ownership_projects_recursive_shared_focus_hierarchy() -> None:
    def symbol(fact_id: str, provider_id: str) -> EvidenceItem:
        return EvidenceItem(
            id=fact_id,
            summary=f"Unchanged symbol: {provider_id}",
            kind="symbol",
            classification="code",
            profile="production",
            authority="structural_provider",
            revision_side="head",
            operation="unchanged",
            role="runtime_context",
            metadata={
                "symbol_id": provider_id,
                "review_symbol_id": provider_id,
                "qualified_name": provider_id,
                "symbol_kind": "class",
            },
        )

    anchor = EvidenceItem(
        id="E:change:child",
        summary="Modified method: child",
        kind="structural_change",
        classification="code",
        profile="production",
        authority="structural_provider",
        revision_side="review",
        operation="modified",
        role="changed_anchor",
        changed=True,
        structural_change=StructuralChangeIdentity(
            review_symbol_id="child",
            head_symbol_evidence_id="E:symbol:child",
        ),
    )

    def ownership(
        fact_id: str,
        parent_id: str,
        child_id: str,
    ) -> EvidenceItem:
        return EvidenceItem(
            id=fact_id,
            summary=f"Retained ownership: {parent_id} contains {child_id}",
            kind="structural_ownership_change",
            classification="code",
            profile="unknown",
            authority="structural_provider",
            revision_side="review",
            operation="retained",
            role="structural_ownership",
            structural_ownership_change=StructuralOwnershipChangeIdentity(
                parent_review_symbol_id=parent_id,
                child_review_symbol_id=child_id,
                base_ownership_evidence_id=f"E:base:{fact_id}",
                head_ownership_evidence_id=f"E:head:{fact_id}",
            ),
        )

    def ownership_provenance(
        fact_id: str,
        revision: str,
        parent_symbol_id: str,
        child_symbol_id: str,
    ) -> EvidenceItem:
        return EvidenceItem(
            id=fact_id,
            summary=f"{revision} ownership",
            kind="structural_ownership",
            classification="code",
            profile="unknown",
            authority="structural_provider",
            revision_side=revision,
            operation="observed",
            role="structural_ownership",
            structural_ownership=StructuralOwnershipIdentity(
                parent_provider_symbol_id=parent_symbol_id,
                child_provider_symbol_id=child_symbol_id,
                parent_symbol_evidence_id=f"E:symbol:{parent_symbol_id}",
                child_symbol_evidence_id=f"E:symbol:{child_symbol_id}",
            ),
        )

    evidence = EvidenceCatalog(
        items=(
            anchor,
            symbol("E:symbol:child", "child"),
            symbol("E:symbol:parent", "parent"),
            symbol("E:symbol:file", "file"),
            ownership_provenance(
                "E:base:E:ownership:parent-child",
                "base",
                "parent",
                "child",
            ),
            ownership_provenance(
                "E:head:E:ownership:parent-child",
                "head",
                "parent",
                "child",
            ),
            ownership_provenance(
                "E:base:E:ownership:file-parent",
                "base",
                "file",
                "parent",
            ),
            ownership_provenance(
                "E:head:E:ownership:file-parent",
                "head",
                "file",
                "parent",
            ),
            ownership("E:ownership:parent-child", "parent", "child"),
            ownership("E:ownership:file-parent", "file", "parent"),
        )
    )
    relations = tuple(
        ProjectionRelation(
            id=f"P:{focus_id}",
            focus_statement_id=focus_id,
            slot="changed_anchor",
            target_type="evidence",
            target_id=anchor.id,
            association="exact_identifier",
            reasons=(),
        )
        for focus_id in ("R1", "R2")
    )
    candidates = ProjectionCandidateSet(
        relations=relations,
        groups=tuple(
            ProjectionCandidateGroup(
                focus_statement_id=focus_id,
                profile="generic",
                relation_ids=(relation.id,),
            )
            for focus_id, relation in zip(
                ("R1", "R2"),
                relations,
                strict=True,
            )
        ),
    )
    convergence = CandidateConvergence(
        groups=tuple(
            ConvergenceGroup(
                focus_statement_id=focus_id,
                selected_relation_ids=(relation.id,),
            )
            for focus_id, relation in zip(
                ("R1", "R2"),
                relations,
                strict=True,
            )
        )
    )

    projection = _build_projection(candidates, convergence, evidence)

    assert {
        node.review_symbol_id for node in projection.review_graph.nodes
    } == {"child", "parent", "file"}
    assert projection.review_graph.edges == ()
    assert [
        (
            edge.ownership_change_evidence_id,
            edge.operation,
        )
        for edge in projection.review_graph.ownership_edges
    ] == [
        ("E:ownership:parent-child", "retained"),
        ("E:ownership:file-parent", "retained"),
    ]
    assert (
        projection.slices[0].change_map.structural_overlay.ownership_edge_ids
        == projection.slices[1].change_map.structural_overlay.ownership_edge_ids
        == (
            "E:ownership:parent-child",
            "E:ownership:file-parent",
        )
    )
    assert len(projection.review_graph.ownership_edges) == 2
    assert len(projection.review_graph.placements) == 2
    html = _review_graph(
        projection.review_graph,
        _with_verification_overlays(projection),
        SimpleNamespace(
            evidence_catalog=evidence,
            overview=SimpleNamespace(
                structural_coverage=StructuralCoverage(state="unavailable")
            ),
        ),
    )
    assert (
        "3 backbone nodes · 0 support nodes · "
        "0 backbone relation groups · 0 canonical executable edges · "
        "2 structural placements · "
        "2 ownership deltas · "
        "0 isolated changed anchors"
    ) in html
    assert html.count('class="structural-container operation-') == 2
    assert html.count('class="structural-container-header operation-') == 2
    assert "Structural coverage · unavailable" in html
    assert html.count('data-context-focuses="R1 R2"') >= 4
    assert html.count('data-focuses="R1 R2"') == 1
    assert "member · retained" not in html
    assert 'class="hierarchy-toggle' not in html
    assert 'class="ownership-edge' not in html
    assert html.count('class="delta-node operation-') == 1

    cyclic_evidence = replace(
        evidence,
        items=(
            *evidence.items,
            ownership("E:ownership:child-file", "child", "file"),
        ),
    )
    with pytest.raises(
        ValueError,
        match="review structural ownership contains a cycle",
    ):
        _build_projection(candidates, convergence, cyclic_evidence)


def test_projection_uses_review_relevant_structural_closure() -> None:
    def symbol(
        fact_id: str,
        symbol_id: str,
        *,
        changed: bool = False,
        profile: str = "production",
        kind: str = "function",
    ) -> EvidenceItem:
        return EvidenceItem(
            id=fact_id,
            summary=symbol_id,
            kind="symbol",
            classification="test" if profile == "test" else "code",
            profile=profile,
            authority="structural_provider",
            revision_side="head" if changed else "unchanged",
            operation="modified" if changed else "unchanged",
            role=(
                "changed_anchor"
                if changed
                else "test_context"
                if profile == "test"
                else "runtime_context"
            ),
            changed=changed,
            metadata={
                "symbol_id": symbol_id,
                "review_symbol_id": symbol_id,
                "qualified_name": symbol_id,
                "symbol_kind": kind,
            },
        )

    def path(fact_id: str, *steps: tuple[str, str]) -> EvidenceItem:
        return EvidenceItem(
            id=fact_id,
            summary=fact_id,
            kind="structural_path",
            classification="code",
            profile="structural_path",
            authority="structural_provider",
            revision_side="unchanged",
            operation="observed",
            role="structural_path",
            metadata={
                "depth": len(steps),
                "steps": tuple(
                    {
                        "source_evidence_id": f"E:{source}",
                        "target_evidence_id": f"E:{target}",
                        "relation": "calls",
                        "direction": "outgoing",
                    }
                    for source, target in steps
                ),
            },
        )

    def relation(
        relation_id: str,
        slot: str,
        target_id: str,
        *,
        bridges: tuple[str, ...] = (),
        ordinal: int = 0,
    ) -> ProjectionRelation:
        return ProjectionRelation(
            id=relation_id,
            focus_statement_id="R1",
            slot=slot,
            target_type="evidence",
            target_id=target_id,
            association=(
                "exact_identifier"
                if slot == "changed_anchor"
                else "structural_bridge"
            ),
            reasons=(),
            bridge_ids=bridges,
            source_ordinal=ordinal,
        )

    evidence = EvidenceCatalog(
        items=(
            symbol("E:anchor", "anchor", changed=True),
            symbol("E:runtime", "runtime", kind="class"),
            symbol("E:test", "test", profile="test", kind="variable"),
            symbol("E:detour", "detour"),
            symbol("E:anchor_2", "anchor_2", changed=True),
            symbol("E:runtime_2", "runtime_2"),
            symbol("E:peripheral", "peripheral"),
            path("E:path:runtime", ("anchor", "runtime")),
            path(
                "E:path:runtime-long",
                ("anchor", "detour"),
                ("detour", "runtime"),
            ),
            path(
                "E:path:test",
                ("anchor", "runtime"),
                ("runtime", "test"),
            ),
            path("E:path:independent", ("anchor_2", "runtime_2")),
            path("E:path:anchor-link", ("anchor", "anchor_2")),
            EvidenceItem(
                id="E:relation:anchor-runtime",
                summary="Retained structural relation: anchor calls runtime",
                kind="structural_relation_change",
                classification="code",
                profile="structural_path",
                authority="structural_provider",
                revision_side="review",
                operation="retained",
                role="structural_relation",
                changed=False,
                structural_relation_change=StructuralRelationChangeIdentity(
                source_review_symbol_id="anchor",
                target_review_symbol_id="runtime",
                    relation="calls",
                    head_path_evidence_ids=("E:path:runtime",),
                ),
            ),
            EvidenceItem(
                id="E:relation:runtime-test",
                summary="Removed structural relation: runtime calls test",
                kind="structural_relation_change",
                classification="test",
                profile="structural_path",
                authority="structural_provider",
                revision_side="review",
                operation="removed",
                role="structural_relation",
                changed=True,
                structural_relation_change=StructuralRelationChangeIdentity(
                    source_review_symbol_id="runtime",
                    target_review_symbol_id="test",
                    relation="calls",
                    base_path_evidence_ids=("E:path:test",),
                ),
            ),
            EvidenceItem(
                id="E:relation:anchor2-runtime2",
                summary="Added structural relation: anchor_2 calls runtime_2",
                kind="structural_relation_change",
                classification="code",
                profile="structural_path",
                authority="structural_provider",
                revision_side="review",
                operation="added",
                role="structural_relation",
                changed=True,
                structural_relation_change=StructuralRelationChangeIdentity(
                    source_review_symbol_id="anchor_2",
                    target_review_symbol_id="runtime_2",
                    relation="calls",
                    head_path_evidence_ids=("E:path:independent",),
                ),
            ),
            EvidenceItem(
                id="E:relation:anchor-anchor2",
                summary="Added structural relation: anchor calls anchor_2",
                kind="structural_relation_change",
                classification="code",
                profile="structural_path",
                authority="structural_provider",
                revision_side="review",
                operation="added",
                role="structural_relation",
                changed=True,
                structural_relation_change=StructuralRelationChangeIdentity(
                    source_review_symbol_id="anchor",
                    target_review_symbol_id="anchor_2",
                    relation="calls",
                    head_path_evidence_ids=("E:path:anchor-link",),
                ),
            ),
            EvidenceItem(
                id="E:relation:peripheral",
                summary="Retained structural relation: detour calls peripheral",
                kind="structural_relation_change",
                classification="code",
                profile="structural_path",
                authority="structural_provider",
                revision_side="review",
                operation="retained",
                role="structural_relation",
                changed=False,
                structural_relation_change=StructuralRelationChangeIdentity(
                    source_review_symbol_id="detour",
                    target_review_symbol_id="peripheral",
                    relation="calls",
                    head_path_evidence_ids=("E:path:runtime-long",),
                ),
            ),
        )
    )
    relations = (
        relation("A", "changed_anchor", "E:anchor"),
        relation(
            "P-runtime",
            "structural_path",
            "E:path:runtime",
            bridges=("E:anchor",),
        ),
        relation(
            "P-runtime-long",
            "structural_path",
            "E:path:runtime-long",
            bridges=("E:anchor",),
            ordinal=1,
        ),
        relation(
            "P-test",
            "structural_path",
            "E:path:test",
            bridges=("E:anchor",),
            ordinal=2,
        ),
        relation(
            "C-runtime",
            "runtime_context",
            "E:runtime",
            bridges=("E:path:runtime",),
        ),
        relation(
            "C-test",
            "test_context",
            "E:test",
            bridges=("E:path:test",),
        ),
        relation("A-2", "changed_anchor", "E:anchor_2", ordinal=1),
        relation(
            "P-independent",
            "structural_path",
            "E:path:independent",
            bridges=("E:anchor_2",),
            ordinal=3,
        ),
        relation(
            "C-runtime-2",
            "runtime_context",
            "E:runtime_2",
            bridges=("E:path:independent",),
            ordinal=1,
        ),
        relation(
            "P-anchor-link",
            "structural_path",
            "E:path:anchor-link",
            bridges=("E:anchor",),
            ordinal=4,
        ),
    )
    second_relations = tuple(
        replace(item, id=f"R2-{item.id}", focus_statement_id="R2")
        for item in relations
    )
    candidates = ProjectionCandidateSet(
        relations=(*relations, *second_relations),
        groups=(
            ProjectionCandidateGroup(
                focus_statement_id="R1",
                profile="generic",
                relation_ids=tuple(item.id for item in relations),
            ),
            ProjectionCandidateGroup(
                focus_statement_id="R2",
                profile="generic",
                relation_ids=tuple(item.id for item in second_relations),
            ),
        ),
    )

    convergence = converge_candidates(candidates, evidence_catalog=evidence)
    closure = convergence.groups[0].structural_closure
    assert closure.path_relation_ids == (
        "P-anchor-link",
        "P-runtime",
        "P-test",
        "P-independent",
    )
    assert closure.relation_change_evidence_ids == (
        "E:relation:anchor-runtime",
        "E:relation:runtime-test",
        "E:relation:anchor2-runtime2",
        "E:relation:anchor-anchor2",
    )
    assert "E:relation:peripheral" not in closure.relation_change_evidence_ids
    assert "P-anchor-link" in convergence.groups[0].selected_relation_ids

    projection = _build_projection(candidates, convergence, evidence)
    assert projection.slices[0].change_map.structural_disposition.state == "projected"
    assert (
        "P-runtime-long"
        in projection.slices[0]
        .change_map.structural_disposition
        .deferred_structural_relation_ids
    )
    overlay = projection.slices[0].change_map.structural_overlay
    second_overlay = projection.slices[1].change_map.structural_overlay
    graph = projection.review_graph
    assert {item.review_symbol_id for item in graph.nodes} == {
        "anchor",
        "runtime",
        "test",
        "anchor_2",
        "runtime_2",
    }
    assert len(graph.edges) == 4
    assert tuple(item.operation for item in graph.edges) == (
        "retained",
        "removed",
        "added",
        "added",
    )
    assert graph.edges[0].path_relation_ids == ("P-runtime", "R2-P-runtime")
    assert overlay.edge_ids == second_overlay.edge_ids
    direct_edge = next(
        item
        for item in graph.edges
        if item.relation_change_evidence_id == "E:relation:anchor-anchor2"
    )
    assert direct_edge.path_relation_ids == (
        "P-anchor-link",
        "R2-P-anchor-link",
    )
    assert tuple(item.node_id for item in overlay.nodes) == tuple(
        item.node_id for item in second_overlay.nodes
    )
    assert {
        graph_node.review_symbol_id: item.path_relation_ids
        for item in overlay.nodes
        for graph_node in graph.nodes
        if graph_node.id == item.node_id
    } == {
        "anchor": ("P-runtime", "P-anchor-link"),
        "runtime": ("P-runtime", "P-test"),
        "test": ("P-test",),
        "anchor_2": ("P-independent", "P-anchor-link"),
        "runtime_2": ("P-independent",),
    }
    html = _review_graph(
        graph,
        _with_verification_overlays(projection),
        SimpleNamespace(
            evidence_catalog=evidence,
            overview=SimpleNamespace(
                structural_coverage=StructuralCoverage(state="unavailable")
            ),
        ),
    )
    assert html.count('class="delta-canvas"') == 1
    assert graph.backbone_node_ids == (
        _structural_node_id("anchor"),
        _structural_node_id("anchor_2"),
        _structural_node_id("runtime"),
        _structural_node_id("runtime_2"),
    )
    assert graph.backbone_edge_ids == (
        "E:relation:anchor-runtime",
        "E:relation:anchor2-runtime2",
        "E:relation:anchor-anchor2",
    )
    assert html.count('class="delta-edge operation-') == 3
    assert "calls · added" in html
    assert "calls · retained" in html
    assert "function · modified" in html
    assert "variable · context" not in html
    assert 'data-focuses="R1 R2"' in html


def test_review_graph_renders_complete_focus_union() -> None:
    def symbol(fact_id: str, symbol_id: str) -> EvidenceItem:
        return EvidenceItem(
            id=fact_id,
            summary=f"Changed function: {symbol_id}",
            kind="symbol",
            classification="code",
            profile="production",
            authority="structural_provider",
            revision_side="head",
            operation="modified",
            role="changed_anchor",
            changed=True,
            metadata={
                "symbol_id": symbol_id,
                "review_symbol_id": symbol_id,
                "qualified_name": symbol_id,
                "symbol_kind": "function",
            },
        )

    def relation_change(
        fact_id: str,
        source_id: str,
        target_id: str,
        operation: str,
    ) -> EvidenceItem:
        return EvidenceItem(
            id=fact_id,
            summary=f"{operation.title()} structural relation",
            kind="structural_relation_change",
            classification="code",
            profile="structural_path",
            authority="structural_provider",
            revision_side="review",
            operation=operation,
            role="structural_relation",
            changed=operation != "retained",
            structural_relation_change=StructuralRelationChangeIdentity(
                source_review_symbol_id=source_id,
                target_review_symbol_id=target_id,
                relation="calls",
                base_path_evidence_ids=(
                    (f"E:path:{fact_id}:base",)
                    if operation == "removed"
                    else ()
                ),
                head_path_evidence_ids=(
                    (f"E:path:{fact_id}:head",)
                    if operation != "removed"
                    else ()
                ),
            ),
        )

    node_ids = ("r1_only", "shared", "r2_only", "g_only", "isolated")
    evidence = EvidenceCatalog(
        items=(
            *(symbol(f"E:{node_id}", node_id) for node_id in node_ids),
            relation_change("E:edge:r1", "r1_only", "shared", "added"),
            relation_change("E:edge:r2", "shared", "r2_only", "retained"),
            relation_change("E:edge:g1", "g_only", "shared", "removed"),
        )
    )
    nodes = tuple(
        StructuralGraphNode(
            id=f"N:{node_id}",
            review_symbol_id=node_id,
            delta="modified",
            evidence_ids=(f"E:{node_id}",),
            display_evidence_id=f"E:{node_id}",
        )
        for node_id in node_ids
    )
    edges = tuple(
        StructuralGraphEdge(
            id=f"D:{focus_id}",
            source_node_id=f"N:{source_id}",
            target_node_id=f"N:{target_id}",
            relation="calls",
            operation=operation,
            relation_change_evidence_id=f"E:edge:{focus_id.casefold()}",
        )
        for focus_id, source_id, target_id, operation in (
            ("R1", "r1_only", "shared", "added"),
            ("R2", "shared", "r2_only", "retained"),
            ("G1", "g_only", "shared", "removed"),
        )
    )
    group_projection = project_structural_relation_groups(
        nodes=nodes,
        edges=edges,
        placements=(),
        backbone_edge_ids=tuple(item.id for item in edges),
    )

    def overlay(focus_id: str, *focus_node_ids: str) -> ReviewSlice:
        edge_ids = () if focus_id == "R3" else (f"D:{focus_id}",)
        return ReviewSlice(
            change_map=CanonicalChangeMapEntry(
                focus_statement_id=focus_id,
                claim_relation_ids=(
                    ("P:claim",) if focus_id == "R1" else ()
                ),
                structural_disposition=StructuralFocusDisposition(
                    state="projected"
                ),
                structural_overlay=StructuralFocusOverlay(
                    nodes=tuple(
                        StructuralFocusNode(
                            node_id=f"N:{node_id}",
                            role="changed_anchor",
                        )
                        for node_id in focus_node_ids
                    ),
                    edge_ids=edge_ids,
                    relation_group_ids=tuple(
                        group_projection.group_id_by_edge_id[edge_id]
                        for edge_id in edge_ids
                    )
                ),
            ),
        )

    projection = ReviewProjection(
        slices=(
            overlay("R1", "r1_only", "shared"),
            overlay("R2", "shared", "r2_only"),
            overlay("G1", "g_only", "shared"),
            overlay("R3", "isolated"),
            ReviewSlice(
                change_map=CanonicalChangeMapEntry(focus_statement_id="G2")
            ),
        ),
        review_graph=ReviewStructuralGraph(
            nodes=nodes,
            edges=edges,
            relation_groups=group_projection.groups,
            backbone_node_ids=tuple(item.id for item in nodes),
            backbone_edge_ids=tuple(item.id for item in edges),
            backbone_relation_group_ids=group_projection.backbone_group_ids,
        ),
    )
    html = _review_graph(
        projection.review_graph,
        SimpleNamespace(
            verification_workspace=SimpleNamespace(
                inspections=tuple(
                    SimpleNamespace(
                        subject_id=item.change_map.focus_statement_id,
                        structural_overlay=item.change_map.structural_overlay,
                    )
                    for item in projection.slices
                )
            )
        ),
        SimpleNamespace(
            evidence_catalog=evidence,
            requirements=tuple(
                Requirement(id=focus_id, text=f"{focus_id} contract")
                for focus_id in ("R1", "R2", "R3")
            ),
            guardrails=tuple(
                Requirement(
                    id=focus_id,
                    text=f"{focus_id} guardrail",
                    kind="guardrail",
                    purpose="guardrail",
                )
                for focus_id in ("G1", "G2")
            ),
            claims=(ReviewStatement(id="C1", text="R1 implementation claim"),),
            projection_candidates=ProjectionCandidateSet(
                relations=(
                    ProjectionRelation(
                        id="P:claim",
                        focus_statement_id="R1",
                        slot="claim",
                        target_type="statement",
                        target_id="C1",
                        association="exact_identifier",
                        reasons=(),
                    ),
                )
            ),
            overview=SimpleNamespace(
                structural_coverage=StructuralCoverage(state="unavailable")
            ),
        ),
    )
    assert html.count('class="relation-group-details"') == 3
    assert html.count('class="relation-member"') == 3
    assert html.count('data-group-target="') == 3
    assert html.count('role="button" aria-expanded="false"') == 3
    assert "navigation unavailable" in html
    assert 'class="change-map-entry"' not in html
    assert "Canonical Change Map" not in html

    assert (
        "5 backbone nodes · 0 support nodes · "
        "3 backbone relation groups · 3 canonical executable edges · "
        "0 structural placements · "
        "0 ownership deltas · "
        "1 isolated changed anchor"
    ) in html
    assert html.count('class="delta-node operation-') == 4
    assert html.count('class="isolated-anchor operation-') == 1
    assert html.count('class="delta-edge operation-') == 3
    assert 'data-focuses="R1 R2 G1"' in html
    assert html.count('data-focus-target="all"') == 1


def test_change_backbone_does_not_transitively_promote_changed_edges() -> None:
    nodes = tuple(
            StructuralGraphNode(
                id=f"N:{name}",
                review_symbol_id=name,
                delta="modified",
                evidence_ids=(),
                display_evidence_id=f"E:{name}",
            )
        for name in ("seed", "direct", "transitive")
    )
    edges = (
        StructuralGraphEdge(
            id="D:direct",
            source_node_id="N:seed",
            target_node_id="N:direct",
            relation="calls",
            operation="added",
            relation_change_evidence_id="E:direct",
        ),
        StructuralGraphEdge(
            id="D:transitive",
            source_node_id="N:direct",
            target_node_id="N:transitive",
            relation="calls",
            operation="added",
            relation_change_evidence_id="E:transitive",
        ),
    )

    node_ids, edge_ids, ownership_edge_ids = _change_backbone(
        nodes=nodes,
        edges=edges,
        ownership_edges=(),
        seed_node_ids=("N:seed",),
    )

    assert node_ids == ("N:seed", "N:direct")
    assert edge_ids == ("D:direct",)
    assert ownership_edge_ids == ()


def test_change_backbone_keeps_one_hop_retained_support_from_direct_seed() -> None:
    nodes = tuple(
            StructuralGraphNode(
                id=f"N:{name}",
                review_symbol_id=name,
                delta="modified",
                evidence_ids=(),
                display_evidence_id=f"E:{name}",
            )
        for name in ("left", "right", "support")
    )
    edges = (
        StructuralGraphEdge(
            id="D:backbone",
            source_node_id="N:left",
            target_node_id="N:right",
            relation="calls",
            operation="retained",
            relation_change_evidence_id="E:backbone",
        ),
        StructuralGraphEdge(
            id="D:support",
            source_node_id="N:right",
            target_node_id="N:support",
            relation="calls",
            operation="retained",
            relation_change_evidence_id="E:support",
        ),
    )

    node_ids, edge_ids, _ = _change_backbone(
        nodes=nodes,
        edges=edges,
        ownership_edges=(),
        seed_node_ids=("N:left",),
    )

    assert node_ids == ("N:left", "N:right")
    assert edge_ids == ("D:backbone",)


def test_canonical_backbone_seeds_include_rg_and_transformation_anchors() -> None:
    relations = {
        "P:primary": ProjectionRelation(
            id="P:primary",
            focus_statement_id="R1",
            slot="changed_anchor",
            target_type="evidence",
            target_id="E:primary",
            association="provided_association",
            evidence_role="primary",
            reasons=(),
        ),
        "P:test": ProjectionRelation(
            id="P:test",
            focus_statement_id="R1",
            slot="changed_anchor",
            target_type="evidence",
            target_id="E:test",
            association="provided_association",
            evidence_role="test_support",
            reasons=(),
        ),
    }
    review_slice = ReviewSlice(
        change_map=CanonicalChangeMapEntry(
            focus_statement_id="R1",
            structural_overlay=StructuralFocusOverlay(
                nodes=(
                    StructuralFocusNode(
                        node_id="N:rg-primary",
                        role="changed_anchor",
                        relation_ids=("P:primary",),
                    ),
                    StructuralFocusNode(
                        node_id="N:rg-test",
                        role="changed_anchor",
                        relation_ids=("P:test",),
                    ),
                )
            ),
        )
    )
    transformation_group = TransformationStructuralTopologyGroup(
        claim_id="T1",
        structural_overlay=StructuralFocusOverlay(
            nodes=(
                StructuralFocusNode(
                    node_id="N:transformation-anchor",
                    role="changed_anchor",
                ),
                StructuralFocusNode(
                    node_id="N:transformation-context",
                    role="intermediate",
                ),
            )
        ),
    )

    assert _canonical_backbone_seed_node_ids(
        slices=(review_slice,),
        transformation_topology_groups=(transformation_group,),
        relations=relations,
    ) == ("N:rg-primary", "N:transformation-anchor")


def test_support_node_delta_requires_exact_base_and_head_facts() -> None:
    def symbol(
        fact_id: str,
        revision_side: str,
        *,
        operation: str = "unchanged",
        changed: bool = False,
    ) -> EvidenceItem:
        return EvidenceItem(
            id=fact_id,
            summary=f"{revision_side.title()} symbol",
            kind="symbol",
            classification="code",
            profile="production",
            authority="structural_provider",
            revision_side=revision_side,
            operation=operation,
            role="revision_fact",
            changed=changed,
        )

    head = symbol("E:head", "head")
    base = symbol("E:base", "base")

    assert _support_node_delta((head, base), ()) == "retained"
    assert _support_node_delta((head,), ()) == "unresolved"
    removed = symbol(
        "E:removed",
        "base",
        operation="removed",
        changed=True,
    )
    assert _support_node_delta((removed,), ()) == "removed"


def test_structural_display_evidence_uses_head_except_for_removed_nodes() -> None:
    head = EvidenceItem(
        id="E:head",
        summary="Head symbol",
        kind="symbol",
        classification="code",
        profile="production",
        revision_side="head",
    )
    base = EvidenceItem(
        id="E:base",
        summary="Base symbol",
        kind="symbol",
        classification="code",
        profile="production",
        revision_side="base",
    )
    evidence = {item.id: item for item in (base, head)}

    for delta in ("added", "modified", "renamed", "retained", "unresolved"):
        assert (
            _display_evidence_id(delta, ("E:base", "E:head"), evidence)
            == "E:head"
        )
    assert (
        _display_evidence_id("removed", ("E:head", "E:base"), evidence)
        == "E:base"
    )


def test_file_support_node_delta_uses_canonical_git_change_truth() -> None:
    def file_symbol(fact_id: str, revision_side: str) -> EvidenceItem:
        return EvidenceItem(
            id=fact_id,
            summary=f"{revision_side.title()} file symbol",
            kind="symbol",
            classification="code",
            profile="production",
            authority="structural_provider",
            revision_side=revision_side,
            operation="unchanged",
            role="revision_fact",
            metadata={
                "path": "src/service.py",
                "symbol_kind": "file",
            },
        )

    assert _support_node_delta(
        (
            file_symbol("E:head-file", "head"),
            file_symbol("E:base-file", "base"),
        ),
        (
            ChangedFile(
                base_path="src/service.py",
                head_path="src/service.py",
                status="modified",
            ),
        ),
    ) == "modified"


def test_structural_node_merge_rejects_conflicting_delta_truth() -> None:
    left = StructuralGraphNode(
        id="N:service",
        review_symbol_id="service",
        delta="added",
        evidence_ids=("E:head",),
        display_evidence_id="E:head",
    )
    right = StructuralGraphNode(
        id="N:service",
        review_symbol_id="service",
        delta="removed",
        evidence_ids=("E:base",),
        display_evidence_id="E:base",
    )

    with pytest.raises(
        ValueError,
        match="canonical structural graph node delta is inconsistent",
    ):
        _merge_node(left, right)


def test_review_graph_preserves_renamed_node_operation() -> None:
    node = StructuralGraphNode(
        id="N:renamed",
        review_symbol_id="renamed",
        delta="renamed",
        evidence_ids=("E:renamed",),
        display_evidence_id="E:renamed",
    )
    evidence = EvidenceCatalog(
        items=(
            EvidenceItem(
                id="E:renamed",
                summary="Renamed function: renamed_function",
                kind="symbol",
                classification="code",
                profile="production",
                metadata={
                    "qualified_name": "renamed_function",
                    "symbol_kind": "function",
                },
            ),
        )
    )
    projection = ReviewProjection(
        review_graph=ReviewStructuralGraph(
            nodes=(node,),
            backbone_node_ids=(node.id,),
        )
    )

    html = _review_graph(
        projection.review_graph,
        _with_verification_overlays(projection),
        SimpleNamespace(
            evidence_catalog=evidence,
            overview=SimpleNamespace(
                structural_coverage=StructuralCoverage(state="unavailable")
            ),
        ),
    )

    assert 'class="isolated-anchor operation-renamed"' in html
    assert "renamed_function" in html

    occupied: list[tuple[int, int, int, int]] = []
    first = _structural_edge_path(
        30,
        35,
        210,
        72,
        390,
        35,
        210,
        72,
        "instantiates · added",
        occupied,
    )
    second = _structural_edge_path(
        30,
        35,
        210,
        72,
        390,
        35,
        210,
        72,
        "imports · retained",
        occupied,
    )

    assert first[0] == "M 240 71 H 315 V 71 H 390"
    assert first[1] == second[1] == 277
    assert first[2] != second[2]
    assert len(occupied) == 2
    assert occupied[0][2] <= occupied[1][0] or occupied[1][3] <= occupied[0][1]
    for left, _top, right, _bottom in occupied:
        assert 220 <= left < right <= 340


def test_every_requirement_is_routed_without_a_global_statement_budget() -> None:
    requirements = tuple(
        Requirement(id=f"R{index}", text=f"Expose capability_{index}")
        for index in range(1, 81)
    )
    changes = tuple(
        EvidenceItem(
            id=f"E:{index}",
            summary=f"Changed function: capability_{index}",
            kind="structural_change",
            classification="code",
            profile="production",
            revision_side="review",
            operation="added",
            role="changed_anchor",
            changed=True,
            structural_change=StructuralChangeIdentity(
                review_symbol_id=f"capability_{index}",
                head_symbol_evidence_id=f"S:{index}",
            ),
            head_signature=association_signature(f"capability_{index}"),
            metadata={
                "qualified_name": f"capability_{index}",
                "provided_for_statement_ids": (f"R{index}",),
            },
        )
        for index in range(1, 81)
    )
    symbols = tuple(
        EvidenceItem(
            id=f"S:{index}",
            summary=f"Changed function: capability_{index}",
            kind="symbol",
            classification="code",
            profile="production",
            authority="structural_provider",
            revision_side="head",
            operation="added",
            role="revision_fact",
            changed=True,
            metadata={
                "symbol_id": f"capability_{index}",
                "review_symbol_id": f"capability_{index}",
                "qualified_name": f"capability_{index}",
            },
        )
        for index in range(1, 81)
    )
    evidence = (*changes, *symbols)

    candidates = build_projection_candidates(
        requirements=requirements,
        claims=(),
        evidence_catalog=EvidenceCatalog(items=evidence),
        structural_graph=None,
        head_sha=None,
    )
    convergence = converge_candidates(candidates, evidence_catalog=EvidenceCatalog())
    projection = _build_projection(
        candidates,
        convergence,
        EvidenceCatalog(items=evidence),
    )

    assert len(candidates.groups) == 80
    assert len(projection.slices) == 80
    assert not any(
        item.standalone_changed_fact_relation_ids
        for item in projection.slices
    )
    assert all(item.change_map.structural_overlay.nodes for item in projection.slices)
    assert len(projection.review_graph.nodes) == 80
    assert not [
        item
        for item in convergence.diagnostics
        if item.state == "budget_truncated"
    ]


def test_isolated_symbol_and_standalone_document_keep_distinct_canonical_forms() -> None:
    requirements = (
        Requirement(id="R1", text="Expose bounded_trace adapter"),
        Requirement(id="R2", text="Document bounded_trace"),
    )
    evidence = EvidenceCatalog(
        items=(
            EvidenceItem(
                id="E:structural-change",
                summary="Changed function: bounded_trace",
                kind="structural_change",
                classification="code",
                profile="production",
                authority="structural_provider",
                revision_side="review",
                operation="modified",
                role="changed_anchor",
                changed=True,
                structural_change=StructuralChangeIdentity(
                    review_symbol_id="S:bounded_trace",
                    head_symbol_evidence_id="E:symbol",
                ),
                associated_statement_ids=("R1",),
                head_signature=association_signature("bounded_trace"),
                metadata={
                    "symbol_id": "S:bounded_trace",
                    "review_symbol_id": "S:bounded_trace",
                    "qualified_name": "service.bounded_trace",
                    "path": "src/service.py",
                    "provided_for_statement_ids": ("R1",),
                },
            ),
            EvidenceItem(
                id="E:symbol",
                summary="Changed function: bounded_trace",
                kind="symbol",
                classification="code",
                profile="production",
                authority="structural_provider",
                revision_side="head",
                operation="modified",
                role="revision_fact",
                changed=True,
                metadata={
                    "symbol_id": "S:bounded_trace",
                    "review_symbol_id": "S:bounded_trace",
                    "qualified_name": "service.bounded_trace",
                    "path": "src/service.py",
                },
            ),
            EvidenceItem(
                id="E:document",
                summary="Replaced change: docs/bounded_trace.md:1-2",
                kind="change_relation",
                classification="document",
                profile="document",
                authority="github_diff",
                revision_side="head",
                operation="modified",
                role="changed_anchor",
                changed=True,
                associated_statement_ids=("R2",),
                head_signature=association_signature("bounded_trace documentation"),
                metadata={
                    "path": "docs/bounded_trace.md",
                    "provided_for_statement_ids": ("R2",),
                },
            ),
        )
    )
    candidates = build_projection_candidates(
        requirements=requirements,
        claims=(),
        evidence_catalog=evidence,
        structural_graph=None,
        head_sha=None,
    )
    convergence = converge_candidates(candidates, evidence_catalog=evidence)

    projection = _build_projection(candidates, convergence, evidence)
    code_slice, document_slice = projection.slices

    assert len(code_slice.change_map.structural_overlay.nodes) == 1
    assert projection.review_graph.nodes[0].review_symbol_id == "S:bounded_trace"
    assert projection.review_graph.nodes[0].evidence_ids == (
        "E:structural-change",
        "E:symbol",
    )
    assert projection.review_graph.edges == ()
    assert len(document_slice.standalone_changed_fact_relation_ids) == 1
    assert code_slice.change_map.structural_disposition.state == "projected"
    assert document_slice.change_map.structural_disposition.state == "non_structural_only"
    assert (
        document_slice.change_map.structural_disposition.non_structural_relation_ids
        == document_slice.standalone_changed_fact_relation_ids
    )
    graph_html = _review_graph(
        projection.review_graph,
        _with_verification_overlays(projection),
        SimpleNamespace(
            evidence_catalog=evidence,
            overview=SimpleNamespace(
                structural_coverage=StructuralCoverage(state="unavailable")
            ),
        ),
    )
    assert 'data-focuses="R1"' in graph_html
    standalone_targets = {
        candidates.by_id()[relation_id].target_id
        for review_slice in projection.slices
        for relation_id in review_slice.standalone_changed_fact_relation_ids
    }
    assert standalone_targets == {"E:document"}


def test_one_generic_shared_term_is_not_a_default_relation() -> None:
    candidates = build_projection_candidates(
        requirements=(Requirement(id="R1", text="Runtime color approval"),),
        claims=(),
        evidence_catalog=EvidenceCatalog(
            items=(
                EvidenceItem(
                    id="E:unrelated",
                    summary="Changed runtime helper",
                    kind="change_relation",
                    classification="code",
                    profile="production",
                    changed=True,
                ),
            )
        ),
        structural_graph=None,
        head_sha=None,
    )

    assert not [
        item
        for item in candidates.relations
        if item.focus_statement_id == "R1"
        and item.slot == "changed_anchor"
    ]


def test_repository_local_r1_token_is_not_an_issue_reference() -> None:
    candidates = build_projection_candidates(
        requirements=(Requirement(id="R1", text="Expose bounded_trace"),),
        claims=(),
        evidence_catalog=EvidenceCatalog(
            items=(
                EvidenceItem(
                    id="E:fixture",
                    summary="Delete test fixture containing R1",
                    kind="change_relation",
                    classification="test",
                    profile="test",
                    changed=True,
                    authority="github_diff",
                    revision_side="base",
                    operation="removed",
                    role="changed_anchor",
                    base_signature=association_signature('{"id": "R1"}'),
                ),
            )
        ),
        structural_graph=None,
        head_sha=None,
    )

    assert not [
        item
        for item in candidates.relations
        if item.slot == "changed_anchor"
    ]


def test_only_authored_claims_can_explicitly_reference_requirement_ids() -> None:
    claims = (
        ReviewStatement(
            id="C1",
            text="R1: expose bounded_trace",
            role="claim",
            purpose="implementation",
            authority="pr_description",
        ),
    )
    candidates = build_projection_candidates(
        requirements=(Requirement(id="R1", text="Expose bounded_trace"),),
        claims=claims,
        evidence_catalog=EvidenceCatalog(),
        structural_graph=None,
        head_sha=None,
    )

    relation = next(item for item in candidates.relations if item.slot == "claim")
    assert relation.association == "explicit_reference"


def test_changed_anchor_selection_uses_typed_ordinal_not_hashed_id() -> None:
    evidence = EvidenceCatalog(
        items=(
            EvidenceItem(
                id="E:zzz",
                summary="Changed function: bounded_trace",
                kind="change_relation",
                classification="code",
                profile="production",
                changed=True,
                authority="github_diff",
                revision_side="head",
                operation="modified",
                role="changed_anchor",
                head_signature=association_signature("bounded_trace"),
                metadata={
                    "path": "src/b.py",
                    "added_lines": (20,),
                },
            ),
            EvidenceItem(
                id="E:aaa",
                summary="Changed function: bounded_trace",
                kind="change_relation",
                classification="code",
                profile="production",
                changed=True,
                authority="github_diff",
                revision_side="head",
                operation="modified",
                role="changed_anchor",
                head_signature=association_signature("bounded_trace"),
                metadata={
                    "path": "src/a.py",
                    "added_lines": (10,),
                },
            ),
        )
    )
    candidates = build_projection_candidates(
        requirements=(Requirement(id="R1", text="Expose bounded_trace"),),
        claims=(),
        evidence_catalog=evidence,
        structural_graph=None,
        head_sha=None,
    )
    convergence = converge_candidates(
        candidates,
        evidence_catalog=evidence,
        policy=ConvergencePolicy(
            max_direct_anchor_identities=1,
            max_anchor_identities=1,
        ),
    )
    selected_ids = set(convergence.selected_relation_ids())

    selected = [
        item.target_id
        for item in candidates.relations
        if item.slot == "changed_anchor" and item.id in selected_ids
    ]
    assert selected == ["E:aaa"]


def test_partial_structure_is_one_review_level_diagnostic() -> None:
    candidates = build_projection_candidates(
        requirements=(Requirement(id="R1", text="Expose bounded_trace"),),
        claims=(),
        evidence_catalog=EvidenceCatalog(
            items=(
                EvidenceItem(
                    id="E:anchor",
                    summary="Changed function: bounded_trace",
                    kind="symbol",
                    classification="code",
                    profile="production",
                    changed=True,
                    metadata={"qualified_name": "bounded_trace"},
                ),
            )
        ),
        structural_graph=_head_graph(
            index=StructuralGraphIndexStatus(
                state="partial",
                provider="codegraph",
                requested_files=2,
                indexed_files=1,
            )
        ),
        head_sha=None,
    )

    provider_diagnostics = [
        item
        for item in candidates.diagnostics
        if item.state == "partial_coverage" and item.provider == "codegraph"
    ]
    assert len(provider_diagnostics) == 1
    assert provider_diagnostics[0].focus_statement_id == "review"
    assert provider_diagnostics[0].scope == "review"


def test_stale_structure_is_one_review_level_diagnostic() -> None:
    candidates = build_projection_candidates(
        requirements=(
            Requirement(id="R1", text="Expose bounded_trace"),
            Requirement(id="R2", text="Call bounded_trace"),
        ),
        claims=(),
        evidence_catalog=EvidenceCatalog(),
        structural_graph=_head_graph(
            index=StructuralGraphIndexStatus(
                state="stale",
                provider="codegraph",
            )
        ),
        head_sha=None,
    )

    stale = [item for item in candidates.diagnostics if item.state == "stale_source"]
    assert len(stale) == 1
    assert stale[0].focus_statement_id == "review"
    assert stale[0].scope == "review"


def test_selection_and_rendering_are_byte_stable() -> None:
    analysis_input = load_fixture("fixtures/evaluation/direct-hunk.json")
    first = DeterministicAnalyzer().analyze(analysis_input)
    second = DeterministicAnalyzer().analyze(analysis_input)

    assert first.to_dict() == second.to_dict()
    assert render_html(first) == render_html(second)
    html = render_html(first)
    assert "candidate_binding" not in html
    assert "Issue contract" not in html
    assert '<span class="projection-heading">Claimed</span>' not in html
    assert "Observed" in html


def test_generic_inspection_budget_does_not_truncate_changed_anchor_set() -> None:
    evidence = tuple(
        EvidenceItem(
            id=f"E:{index}",
            summary=f"Changed function: bounded_trace_{index}",
            kind="structural_change",
            classification="code",
            profile="production",
            revision_side="review",
            operation="added",
            role="changed_anchor",
            changed=True,
            structural_change=StructuralChangeIdentity(
                review_symbol_id=f"bounded_trace_{index}",
                head_symbol_evidence_id=f"S:{index}",
            ),
            head_signature=association_signature(f"bounded_trace_{index}"),
            metadata={"qualified_name": f"bounded_trace_{index}"},
        )
        for index in range(8)
    )
    candidates = build_projection_candidates(
        requirements=(Requirement(id="R1", text="Expose bounded_trace"),),
        claims=(),
        evidence_catalog=EvidenceCatalog(items=evidence),
        structural_graph=None,
        head_sha=None,
    )
    convergence = converge_candidates(
        candidates,
        evidence_catalog=EvidenceCatalog(items=evidence),
        policy=ConvergencePolicy(
            max_candidates_per_slot=4,
        ),
    )
    selected_ids = set(convergence.selected_relation_ids())

    selected = [
        item
        for item in candidates.relations
        if item.slot == "changed_anchor" and item.id in selected_ids
    ]
    truncated = [
        item
        for item in convergence.diagnostics
        if item.slot == "changed_anchor"
        and item.state == "budget_truncated"
    ]
    assert len(selected) == 8
    assert truncated == []


def test_verification_is_current_head_fact_not_pr_claim() -> None:
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=7,
        title="Verify",
        source_records=(
            SourceRecord(
                id="pr:7",
                kind="pull_request",
                repository="acme/widget",
                body="## Verification\n- tests passed",
            ),
        ),
        head_sha="head",
    ).with_revision()
    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(
            packet=packet,
            requirements=(Requirement(id="R1", text="Tests pass"),),
        )
    )

    assert brief.claims[0].purpose == "verification"
    assert _selected_targets(brief, "R1", "verification") == ()


def test_verification_routing_excludes_stale_head_observations() -> None:
    evidence = EvidenceCatalog(
        items=(
            EvidenceItem(
                id="E:current",
                summary="test: completed/success",
                kind="check_run",
                classification="ci",
                profile="verification",
                authority="verification_provider",
                role="verification",
                observed_head_sha="head",
                verification_identity=VerificationIdentity(
                    provider="github",
                    kind="check_run",
                    name="test",
                ),
                verification_status="completed",
                verification_conclusion="success",
            ),
            EvidenceItem(
                id="E:stale",
                summary="review: completed/success",
                kind="check_run",
                classification="ci",
                profile="verification",
                authority="verification_provider",
                role="verification",
                observed_head_sha="old-head",
                verification_identity=VerificationIdentity(
                    provider="github",
                    kind="check_run",
                    name="review",
                ),
                verification_status="completed",
                verification_conclusion="success",
            ),
        )
    )
    candidates = build_projection_candidates(
        requirements=(Requirement(id="R1", text="Tests pass"),),
        claims=(),
        evidence_catalog=evidence,
        structural_graph=None,
        head_sha="head",
    )
    convergence = converge_candidates(candidates, evidence_catalog=evidence)

    selected = {
        relation.target_id
        for relation in candidates.relations
        if relation.id in convergence.selected_relation_ids()
        and relation.slot == "verification"
    }
    assert selected == {"E:current"}


def test_document_and_workflow_facts_are_routed_by_profile() -> None:
    requirements = (
        Requirement(id="R1", text="Documentation explains bounded_trace."),
        Requirement(id="R2", text="Workflow executes bounded_trace tests."),
        Requirement(id="R3", text="Runtime executes bounded_trace."),
    )
    evidence = EvidenceCatalog(
        items=(
            EvidenceItem(
                id="E:doc",
                summary="Changed documentation: bounded_trace behavior",
                kind="change_relation",
                classification="document",
                profile="document",
                changed=True,
                head_signature=association_signature(
                    "bounded_trace documentation behavior"
                ),
                metadata={"path": "docs/bounded_trace.md"},
            ),
            EvidenceItem(
                id="E:workflow",
                summary="Changed workflow: bounded_trace tests",
                kind="change_relation",
                classification="code",
                profile="workflow",
                changed=True,
                head_signature=association_signature("bounded_trace tests workflow"),
                metadata={"path": ".github/workflows/test.yml"},
            ),
        )
    )

    candidates = build_projection_candidates(
        requirements=requirements,
        claims=(),
        evidence_catalog=evidence,
        structural_graph=None,
        head_sha=None,
    )
    convergence = converge_candidates(
        candidates,
        evidence_catalog=evidence,
    )
    selected_ids = set(convergence.selected_relation_ids())
    selected = {
        (item.focus_statement_id, item.target_id)
        for item in candidates.relations
        if item.slot == "changed_anchor" and item.id in selected_ids
    }

    assert ("R1", "E:doc") in selected
    assert ("R2", "E:workflow") in selected
    assert ("R3", "E:doc") not in selected
    assert ("R3", "E:workflow") not in selected


def test_focus_evidence_roles_are_routed_before_convergence_and_presentation() -> None:
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=44,
        title="Expose bounded trace",
        source_url="https://github.com/acme/widget/pull/44",
        source_records=(),
        changed_files=(
            ChangedFile(
                base_path="docs/bounded_trace.md",
                head_path="docs/bounded_trace.md",
                patch="@@ -1,0 +2 @@\n+bounded_trace behavior\n",
            ),
            ChangedFile(
                base_path="tests/test_bounded_trace.py",
                head_path="tests/test_bounded_trace.py",
                patch="@@ -1,0 +2 @@\n+bounded_trace behavior\n",
            ),
            ChangedFile(
                base_path="src/bounded_trace.py",
                head_path="src/bounded_trace.py",
                patch="@@ -1,0 +2 @@\n+bounded_trace behavior\n",
            ),
        ),
    ).with_revision()
    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(
            packet=packet,
            requirements=(
                Requirement(id="R1", text="Expose bounded_trace behavior"),
            ),
        )
    )
    anchor_relations = tuple(
        item
        for item in brief.projection_candidates.relations
        if item.focus_statement_id == "R1"
        and item.slot == "changed_anchor"
    )
    evidence = brief.evidence_catalog.by_id()

    assert {
        evidence[item.target_id].profile: item.evidence_role
        for item in anchor_relations
    } == {
        "production": "primary",
        "test": "test_support",
        "document": "document_support",
    }
    review_slice = brief.projection.slices[0]
    assert len(review_slice.standalone_changed_fact_relation_ids) == 1
    assert len(review_slice.standalone_test_support_relation_ids) == 1
    assert len(review_slice.standalone_document_support_relation_ids) == 1
    html = render_html(brief)
    assert "Observed" in html
    assert "production" in html

    bounded = converge_candidates(
        brief.projection_candidates,
        evidence_catalog=brief.evidence_catalog,
        policy=ConvergencePolicy(
            max_direct_anchor_identities=2,
            max_anchor_identities=2,
        ),
    )
    selected = set(bounded.selected_relation_ids())
    assert [
        item.evidence_role
        for item in anchor_relations
        if item.id in selected
    ] == ["primary", "test_support"]


def test_graph_and_no_graph_use_the_same_projection_contract() -> None:
    suite = load_evaluation_suite(SUITE)
    case = next(item for item in suite.cases if item.id == "bounded-y-x-z")
    base = load_fixture(case.fixture)
    without_graph = DeterministicAnalyzer().analyze(base)
    with_graph = DeterministicAnalyzer().analyze(
        replace(base, structural_graph=case.structural_graph)
    )

    assert without_graph.projection.schema_version == with_graph.projection.schema_version
    assert [
        (item.focus_statement_id, item.profile)
        for item in without_graph.projection_candidates.groups
    ] == [
        (item.focus_statement_id, item.profile)
        for item in with_graph.projection_candidates.groups
    ]
    assert (
        without_graph.projection.slices[0].standalone_changed_fact_relation_ids
    )
    assert with_graph.projection.review_graph.nodes
    assert without_graph.projection.review_graph.path_relation_ids == ()
    assert with_graph.projection.review_graph.path_relation_ids == ()
    assert without_graph.projection.slices[0].change_map.structural_overlay.nodes == ()
    assert with_graph.projection.slices[0].change_map.structural_overlay.nodes


def test_change_relation_association_scans_beyond_display_preview() -> None:
    late_identifier = "late_bounded_adapter"
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=91,
        title="Large change",
        source_records=(),
        changed_files=(
            ChangedFile(
                base_path="src/large.py",
                head_path="src/large.py",
                patch=(
                    "@@ -0,0 +1 @@\n"
                    f"+{'x' * 4100} {late_identifier}()\n"
                ),
            ),
        ),
    ).with_revision()

    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(
            packet=packet,
            requirements=(
                Requirement(id="R1", text=f"Expose {late_identifier}"),
            ),
        )
    )
    anchor_id = _selected_targets(brief, "R1", "changed_anchor")[0]
    anchor = brief.evidence_catalog.by_id()[anchor_id]

    assert len(anchor.metadata["head_preview"]) == 4000
    assert late_identifier not in anchor.metadata["head_preview"]
    assert "lateboundedadapter" in anchor.head_signature.identifiers


def test_base_signature_is_used_only_for_removal_or_guardrail_focus() -> None:
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=92,
        title="Replace legacy path",
        source_records=(),
        changed_files=(
            ChangedFile(
                base_path="src/service.py",
                head_path="src/service.py",
                patch=(
                    "@@ -1 +1 @@\n"
                    "-legacy_bounded_adapter()\n"
                    "+modern_path()\n"
                ),
            ),
        ),
    ).with_revision()
    requirements = (
        Requirement(id="R1", text="Expose legacy_bounded_adapter"),
        Requirement(
            id="G1",
            text="Remove legacy_bounded_adapter",
            purpose="guardrail",
            kind="guardrail",
        ),
    )
    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(packet=packet, requirements=requirements)
    )

    assert _selected_targets(brief, "R1", "changed_anchor") == ()
    assert _selected_targets(brief, "G1", "changed_anchor")
