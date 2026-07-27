from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from prismcode.pipeline import DeterministicAnalyzer
from prismcode.model.contracts import (
    AnalysisInput,
    ChangedFile,
    EvidenceCatalog,
    EvidenceItem,
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
    StructuralFocusNode,
    StructuralFocusOverlay,
    StructuralGraphEdge,
    StructuralGraphNode,
    StructuralRelationChangeIdentity,
    VerificationIdentity,
)
from prismcode.evaluation.core import load_evaluation_suite
from prismcode.facts.lexical import association_signature
from prismcode.intake.fixture import load_fixture
from prismcode.routing.candidates import build_projection_candidates
from prismcode.convergence.core import (
    ConvergencePolicy,
    converge_candidates,
)
from prismcode.projection.build import build_review_projection
from prismcode.presentation.html import (
    _review_graph,
    _structural_edge_path,
    render_html,
)
from prismcode.providers.structural import (
    StructuralGraphCollection,
    StructuralGraphIndexStatus,
    StructuralGraphResult,
)


SUITE = Path("fixtures/evaluation-suite.json")


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
        "E:structural_change:5910f29667b835bd4cbe",
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
    overlay = brief.projection.slices[0].structural_overlay
    graph = brief.projection.review_graph
    assert [item.role for item in overlay.nodes] == ["changed_anchor"]
    assert overlay.path_relation_ids == ()
    assert graph.edges == ()
    assert graph.nodes[0].provider_symbol_id == "Y"
    assert graph.nodes[0].evidence_ids == (
        "E:structural_change:5910f29667b835bd4cbe",
        "E:symbol:9e703e599343229d97c1",
    )
    html = render_html(brief)
    assert html.count("Structural delta graph") == 1
    assert html.index("Structural delta graph") < html.index(
        '<div class="requirements">'
    )
    assert "0 connected nodes · 0 canonical edges · 1 isolated changed anchor" in html
    assert 'data-focus-target="R1"' in html
    assert 'class="requirement" data-focus-id="R1" open' in html
    assert 'requirement.querySelector("summary").addEventListener("click"' in html
    assert "activateFocus(requirement.dataset.focusId)" in html
    assert 'class="delta-canvas"' not in html
    assert '<details class="isolated-anchors">' in html
    assert "No safe canonical relation delta is available." in html
    assert '<span class="block-title">Structural paths</span>' not in html
    assert '<span class="block-title">Runtime context</span>' in html
    assert '<span class="block-title">Test context</span>' in html
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
    assert tuple(item.node_id for item in first.structural_overlay.nodes) == tuple(
        item.node_id for item in second.structural_overlay.nodes
    )
    assert first.structural_overlay.edge_ids == second.structural_overlay.edge_ids
    assert first.structural_overlay.path_relation_ids == ()
    assert second.structural_overlay.path_relation_ids == ()
    html = render_html(brief)
    assert html.count("Structural delta graph") == 1
    assert html.count('<div class="isolated-anchor operation-modified"') == 1
    assert 'data-focus-target="R1"' in html
    assert 'data-focus-target="R2"' in html
    assert "Structural overlay" not in html


def test_projection_uses_terminal_aware_structural_support_set() -> None:
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
                    source_provider_symbol_id="anchor",
                    target_provider_symbol_id="runtime",
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
                    source_provider_symbol_id="runtime",
                    target_provider_symbol_id="test",
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
                    source_provider_symbol_id="anchor_2",
                    target_provider_symbol_id="runtime_2",
                    relation="calls",
                    head_path_evidence_ids=("E:path:independent",),
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
    support = convergence.groups[0].structural_support
    assert support.path_relation_ids == (
        "P-runtime",
        "P-test",
        "P-independent",
    )

    projection = build_review_projection(candidates, convergence, evidence)
    overlay = projection.slices[0].structural_overlay
    second_overlay = projection.slices[1].structural_overlay
    graph = projection.review_graph
    assert {item.provider_symbol_id for item in graph.nodes} == {
        "anchor",
        "runtime",
        "test",
        "anchor_2",
        "runtime_2",
    }
    assert len(graph.edges) == 3
    assert tuple(item.operation for item in graph.edges) == (
        "retained",
        "removed",
        "added",
    )
    assert graph.edges[0].path_relation_ids == ("P-runtime", "R2-P-runtime")
    assert overlay.edge_ids == second_overlay.edge_ids
    assert tuple(item.node_id for item in overlay.nodes) == tuple(
        item.node_id for item in second_overlay.nodes
    )
    assert {
        graph_node.provider_symbol_id: item.path_relation_ids
        for item in overlay.nodes
        for graph_node in graph.nodes
        if graph_node.id == item.node_id
    } == {
        "anchor": ("P-runtime",),
        "runtime": ("P-runtime", "P-test"),
        "test": ("P-test",),
        "anchor_2": ("P-independent",),
        "runtime_2": ("P-independent",),
    }
    html = _review_graph(
        graph,
        projection,
        SimpleNamespace(evidence_catalog=evidence),
    )
    assert html.count('class="delta-canvas"') == 1
    assert html.count('class="delta-edge operation-') == 3
    assert "calls · retained" in html
    assert "calls · removed" in html
    assert "calls · added" in html
    assert "function · modified" in html
    assert "class · context" in html
    assert "variable · context" in html
    assert 'data-focus-target="R1"' in html
    assert 'data-focus-target="R2"' in html


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
                source_provider_symbol_id=source_id,
                target_provider_symbol_id=target_id,
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
            provider_symbol_id=node_id,
            operation="modified",
            evidence_ids=(f"E:{node_id}",),
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

    def overlay(focus_id: str, *focus_node_ids: str) -> ReviewSlice:
        edge_ids = () if focus_id == "R3" else (f"D:{focus_id}",)
        return ReviewSlice(
            focus_statement_id=focus_id,
            structural_overlay=StructuralFocusOverlay(
                nodes=tuple(
                    StructuralFocusNode(
                        node_id=f"N:{node_id}",
                        role="changed_anchor",
                    )
                    for node_id in focus_node_ids
                ),
                edge_ids=edge_ids,
            ),
        )

    projection = ReviewProjection(
        slices=(
            overlay("R1", "r1_only", "shared"),
            overlay("R2", "shared", "r2_only"),
            overlay("G1", "g_only", "shared"),
            overlay("R3", "isolated"),
        ),
        review_graph=ReviewStructuralGraph(nodes=nodes, edges=edges),
    )
    html = _review_graph(
        projection.review_graph,
        projection,
        SimpleNamespace(evidence_catalog=evidence),
    )

    assert "4 connected nodes · 3 canonical edges · 1 isolated changed anchor" in html
    assert html.count('class="delta-node operation-') == 4
    assert html.count('class="isolated-anchor operation-') == 1
    assert html.count('class="delta-edge operation-') == 3
    assert 'data-focuses="R1 R2 G1"' in html
    for focus_id in ("R1", "R2", "R3", "G1"):
        assert f'data-focus-target="{focus_id}"' in html

    occupied: list[tuple[int, int, int, int]] = []
    first = _structural_edge_path(
        30,
        35,
        390,
        35,
        "instantiates · added",
        occupied,
    )
    second = _structural_edge_path(
        30,
        35,
        390,
        35,
        "imports · retained",
        occupied,
    )

    assert first[1] == second[1] == 315
    assert first[2] != second[2]
    assert len(occupied) == 2
    assert occupied[0][2] <= occupied[1][0] or occupied[1][3] <= occupied[0][1]
    for left, _top, right, _bottom in occupied:
        assert 240 <= left < right <= 390


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
                provider_symbol_id=f"capability_{index}",
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
    projection = build_review_projection(
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
    assert all(item.structural_overlay.nodes for item in projection.slices)
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
                    provider_symbol_id="S:bounded_trace",
                    head_symbol_evidence_id="E:symbol",
                ),
                associated_statement_ids=("R1",),
                head_signature=association_signature("bounded_trace"),
                metadata={
                    "symbol_id": "S:bounded_trace",
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

    projection = build_review_projection(candidates, convergence, evidence)
    code_slice, document_slice = projection.slices

    assert len(code_slice.structural_overlay.nodes) == 1
    assert projection.review_graph.nodes[0].provider_symbol_id == "S:bounded_trace"
    assert projection.review_graph.nodes[0].evidence_ids == (
        "E:structural-change",
        "E:symbol",
    )
    assert projection.review_graph.edges == ()
    assert len(document_slice.standalone_changed_fact_relation_ids) == 1
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
    assert "provided" in html
    assert "Repository facts" in html


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
                provider_symbol_id=f"bounded_trace_{index}",
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
    assert without_graph.projection.slices[0].structural_overlay.nodes == ()
    assert with_graph.projection.slices[0].structural_overlay.nodes


def test_change_relation_association_scans_beyond_display_preview() -> None:
    late_identifier = "late_bounded_adapter"
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=91,
        title="Large change",
        source_records=(),
        changed_files=(
            ChangedFile(
                path="src/large.py",
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
                path="src/service.py",
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
