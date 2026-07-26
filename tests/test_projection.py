from __future__ import annotations

from dataclasses import replace
from pathlib import Path

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
    ReviewStatement,
    ReviewSourcePacket,
    SourceRecord,
    StructuralChangeIdentity,
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
from prismcode.presentation.html import render_html
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
    assert [item.role for item in overlay.nodes] == [
        "changed_anchor",
        "runtime_context",
        "test_context",
    ]
    assert len(overlay.path_relation_ids) == 2
    assert len(graph.edges) == 2
    assert len(graph.edges[0].path_relation_ids) == 2
    assert len(graph.edges[1].path_relation_ids) == 1
    assert {
        item.evidence_id: item.relation_ids for item in overlay.nodes
    } == {
        "E:symbol:9e703e599343229d97c1": (
            next(
                item.id
                for item in brief.projection_candidates.relations
                if item.focus_statement_id == "R1"
                and item.slot == "changed_anchor"
                and item.target_id
                == "E:structural_change:5910f29667b835bd4cbe"
            ),
        ),
        "E:symbol:51c78d1cf2a276cc9a40": (
            next(
                item.id
                for item in brief.projection_candidates.relations
                if item.focus_statement_id == "R1"
                and item.slot == "runtime_context"
                and item.target_id == "E:symbol:51c78d1cf2a276cc9a40"
            ),
        ),
        "E:symbol:3c8a35c2cab106b983ca": (
            next(
                item.id
                for item in brief.projection_candidates.relations
                if item.focus_statement_id == "R1"
                and item.slot == "test_context"
                and item.target_id == "E:symbol:3c8a35c2cab106b983ca"
            ),
        ),
    }
    html = render_html(brief)
    assert html.count("Structural evidence graph") == 1
    assert "3 canonical nodes · 2 canonical edges" in html
    assert '<span class="block-title">Structural paths</span>' not in html
    assert '<span class="block-title">Runtime context</span>' not in html
    assert '<span class="block-title">Test context</span>' not in html


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
    assert len(graph.nodes) == 3
    assert len(graph.edges) == 2
    assert tuple(item.evidence_id for item in first.structural_overlay.nodes) == tuple(
        item.evidence_id for item in second.structural_overlay.nodes
    )
    assert first.structural_overlay.edge_ids == second.structural_overlay.edge_ids
    assert (
        first.structural_overlay.path_relation_ids
        != second.structural_overlay.path_relation_ids
    )
    assert all(
        len(edge.path_relation_ids) == 2 * expected
        for edge, expected in zip(graph.edges, (2, 1), strict=True)
    )

    html = render_html(brief)
    assert html.count("Structural evidence graph") == 1
    assert html.count('<div class="subgraph-node">') == 3
    assert html.count('<div class="subgraph-edge">') == 2
    assert html.count("Structural overlay") == 2


def test_projection_uses_terminal_aware_structural_support_set() -> None:
    def symbol(
        fact_id: str,
        symbol_id: str,
        *,
        changed: bool = False,
        profile: str = "production",
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
            metadata={"symbol_id": symbol_id, "qualified_name": symbol_id},
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
            symbol("E:runtime", "runtime"),
            symbol("E:test", "test", profile="test"),
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
    candidates = ProjectionCandidateSet(
        relations=relations,
        groups=(
            ProjectionCandidateGroup(
                focus_statement_id="R1",
                profile="generic",
                relation_ids=tuple(item.id for item in relations),
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
    graph = projection.review_graph
    assert {item.evidence_id for item in graph.nodes} == {
        "E:anchor",
        "E:runtime",
        "E:test",
        "E:anchor_2",
        "E:runtime_2",
    }
    assert len(graph.edges) == 3
    assert graph.edges[0].path_relation_ids == ("P-runtime", "P-test")
    assert {
        item.evidence_id: item.path_relation_ids for item in overlay.nodes
    } == {
        "E:anchor": ("P-runtime", "P-test"),
        "E:runtime": ("P-runtime", "P-test"),
        "E:test": ("P-test",),
        "E:anchor_2": ("P-independent",),
        "E:runtime_2": ("P-independent",),
    }


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

    assert tuple(
        item.evidence_id for item in code_slice.structural_overlay.nodes
    ) == ("E:symbol",)
    assert projection.review_graph.nodes[0].evidence_id == "E:symbol"
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
    assert with_graph.projection.review_graph.path_relation_ids
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
