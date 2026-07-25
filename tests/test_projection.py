from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from prismcode.pipeline import DeterministicAnalyzer
from prismcode.model.contracts import (
    AnalysisInput,
    EvidenceCatalog,
    EvidenceItem,
    Requirement,
    ReviewStatement,
    ReviewSourcePacket,
    SourceRecord,
)
from prismcode.evaluation.core import load_evaluation_suite
from prismcode.intake.fixture import load_fixture
from prismcode.routing.candidates import build_projection_candidates
from prismcode.convergence.core import (
    ConvergencePolicy,
    converge_candidates,
)
from prismcode.projection.build import build_review_projection
from prismcode.presentation.html import render_html
from prismcode.providers.structural import (
    StructuralGraphIndexStatus,
    StructuralGraphResult,
)


SUITE = Path("fixtures/evaluation-suite.json")


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
        "E:changed_hunk:13c27ca8c4cfe45cfbcc",
        "E:changed_hunk:5b5657b12be7abe2bf93",
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
        "E:symbol:9e703e599343229d97c1",
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


def test_every_requirement_is_routed_without_a_global_statement_budget() -> None:
    requirements = tuple(
        Requirement(id=f"R{index}", text=f"Expose capability_{index}")
        for index in range(1, 81)
    )
    evidence = tuple(
        EvidenceItem(
            id=f"E:{index}",
            summary=f"Changed function: capability_{index}",
            kind="symbol",
            classification="code",
            profile="production",
            changed=True,
            metadata={
                "qualified_name": f"capability_{index}",
                "provided_for_statement_ids": (f"R{index}",),
            },
        )
        for index in range(1, 81)
    )

    candidates = build_projection_candidates(
        requirements=requirements,
        claims=(),
        evidence_catalog=EvidenceCatalog(items=evidence),
        structural_graph=None,
        head_sha=None,
    )
    convergence = converge_candidates(candidates)
    projection = build_review_projection(candidates, convergence)

    assert len(candidates.groups) == 80
    assert len(projection.slices) == 80
    assert all(item.changed_anchor_relation_ids for item in projection.slices)
    assert not [
        item
        for item in convergence.diagnostics
        if item.state == "budget_truncated"
    ]


def test_one_generic_shared_term_is_not_a_default_relation() -> None:
    candidates = build_projection_candidates(
        requirements=(Requirement(id="R1", text="Runtime color approval"),),
        claims=(),
        evidence_catalog=EvidenceCatalog(
            items=(
                EvidenceItem(
                    id="E:unrelated",
                    summary="Changed runtime helper",
                    kind="changed_hunk",
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
                    kind="changed_hunk",
                    classification="test",
                    profile="test",
                    changed=True,
                    authority="github_diff",
                    revision_side="base",
                    operation="removed",
                    role="changed_anchor",
                    metadata={"base_excerpt": '{"id": "R1"}'},
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
                kind="changed_hunk",
                classification="code",
                profile="production",
                changed=True,
                authority="github_diff",
                revision_side="head",
                operation="modified",
                role="changed_anchor",
                metadata={
                    "path": "src/b.py",
                    "new_start": 20,
                    "head_excerpt": "bounded_trace()",
                },
            ),
            EvidenceItem(
                id="E:aaa",
                summary="Changed function: bounded_trace",
                kind="changed_hunk",
                classification="code",
                profile="production",
                changed=True,
                authority="github_diff",
                revision_side="head",
                operation="modified",
                role="changed_anchor",
                metadata={
                    "path": "src/a.py",
                    "new_start": 10,
                    "head_excerpt": "bounded_trace()",
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
        policy=ConvergencePolicy(max_changed=1),
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
        structural_graph=StructuralGraphResult(
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
        structural_graph=StructuralGraphResult(
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


def test_per_slot_budget_marks_only_that_focus_and_slot() -> None:
    evidence = tuple(
        EvidenceItem(
            id=f"E:{index}",
            summary=f"Changed function: bounded_trace_{index}",
            kind="symbol",
            classification="code",
            profile="production",
            changed=True,
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
        policy=ConvergencePolicy(
            max_changed=2,
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
    assert len(selected) == 2
    assert len(truncated) == 1


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
                kind="changed_hunk",
                classification="document",
                profile="document",
                changed=True,
                metadata={"path": "docs/bounded_trace.md"},
            ),
            EvidenceItem(
                id="E:workflow",
                summary="Changed workflow: bounded_trace tests",
                kind="changed_hunk",
                classification="code",
                profile="workflow",
                changed=True,
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
    convergence = converge_candidates(candidates)
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
    assert without_graph.projection.slices[0].changed_anchor_relation_ids
    assert with_graph.projection.slices[0].changed_anchor_relation_ids
    assert without_graph.projection.slices[0].structural_path_relation_ids == ()
    assert with_graph.projection.slices[0].structural_path_relation_ids
