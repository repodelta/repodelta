from __future__ import annotations

from prismcode.analysis import DeterministicAnalyzer
from prismcode.candidate_binding import (
    CandidateBindingPolicy,
    build_candidate_bindings,
)
from prismcode.contracts import (
    EvidenceCatalog,
    EvidenceItem,
    AnalysisInput,
    ChangedFile,
    Requirement,
    ReviewSourcePacket,
    ReviewStatement,
    SourceRecord,
)
from prismcode.rendering import render_html


def _catalog() -> EvidenceCatalog:
    path_id = "E:structural_path:y-x-z"
    return EvidenceCatalog(
        items=(
            EvidenceItem(
                id="E:symbol:Y",
                kind="symbol",
                summary="Changed adapter entrypoint",
                classification="code",
                changed=True,
                structural_path_ids=(path_id,),
                metadata={
                    "symbol_id": "Y",
                    "qualified_name": "src.adapter.entrypoint",
                    "path": "src/adapter.py",
                },
            ),
            EvidenceItem(
                id="E:symbol:X",
                kind="symbol",
                summary="Unchanged core processing service",
                classification="code",
                structural_path_ids=(path_id,),
                metadata={
                    "symbol_id": "X",
                    "qualified_name": "src.core.process",
                    "path": "src/core.py",
                },
            ),
            EvidenceItem(
                id="E:symbol:Z",
                kind="symbol",
                summary="Unchanged persistence writer",
                classification="code",
                structural_path_ids=(path_id,),
                metadata={
                    "symbol_id": "Z",
                    "qualified_name": "src.store.persist",
                    "path": "src/store.py",
                },
            ),
            EvidenceItem(
                id=path_id,
                kind="structural_path",
                summary=(
                    "src.adapter.entrypoint →[calls] src.core.process "
                    "→[calls] src.store.persist"
                ),
                classification="runtime",
                structural_path_ids=(path_id,),
                metadata={
                    "seed_symbol_id": "Y",
                    "depth": 2,
                    "steps": (
                        {
                            "source_symbol_id": "Y",
                            "target_symbol_id": "X",
                            "relation": "calls",
                            "direction": "outgoing",
                        },
                        {
                            "source_symbol_id": "X",
                            "target_symbol_id": "Z",
                            "relation": "calls",
                            "direction": "outgoing",
                        },
                    ),
                },
            ),
            EvidenceItem(
                id="E:document:notes",
                kind="changed_file",
                summary="Modified file: docs/notes.md",
                classification="document",
                changed=True,
                metadata={"path": "docs/notes.md"},
            ),
        ),
    )


def test_many_to_many_requirement_claim_and_structural_candidates() -> None:
    requirements = (
        Requirement(id="R1", text="Core processing must preserve persistence."),
        Requirement(id="R2", text="Adapter entrypoint must invoke core processing."),
    )
    claims = (
        ReviewStatement(
            id="C1",
            text="Adapter entrypoint now invokes core processing.",
            role="claim",
            authority="pr_description",
        ),
        ReviewStatement(
            id="C2",
            text="Core processing preserves persistence.",
            role="claim",
            authority="pr_description",
        ),
        ReviewStatement(
            id="C3",
            text="Redesign the unrelated user interface.",
            role="claim",
            authority="pr_description",
        ),
    )

    result = build_candidate_bindings(
        requirements=requirements,
        objectives=(),
        claims=claims,
        evidence_catalog=_catalog(),
    )

    assert all(
        item.score == min(100, sum(reason.weight for reason in item.reasons))
        for item in result.items
    )
    requirement_claims = {
        (item.source_id, item.target_id)
        for item in result.items
        if item.kind == "requirement_claim"
    }
    assert ("R1", "C1") in requirement_claims
    assert ("R1", "C2") in requirement_claims
    assert ("R2", "C1") in requirement_claims
    evidence_pairs = {
        (item.source_id, item.target_id): item
        for item in result.items
        if item.kind == "statement_evidence"
    }
    assert ("R2", "E:symbol:Y") in evidence_pairs
    assert ("R2", "E:symbol:X") in evidence_pairs
    assert ("R2", "E:symbol:Z") in evidence_pairs
    propagated = evidence_pairs[("R2", "E:symbol:Z")]
    assert propagated.structural_path_ids == ("E:structural_path:y-x-z",)
    assert {
        reason.feature for reason in propagated.reasons
    } >= {"lexical_anchor", "structural_path"}
    assert result.coverage.requirement_ids_without_evidence_candidates == ()
    assert result.coverage.claim_ids_without_requirement_candidates == ("C3",)
    assert (
        "E:document:notes"
        in result.coverage.evidence_ids_without_statement_candidates
    )


def test_requirement_can_reach_evidence_without_claim() -> None:
    result = build_candidate_bindings(
        requirements=(
            Requirement(
                id="R1",
                text="Core processing must use the persistence writer.",
            ),
        ),
        objectives=(),
        claims=(),
        evidence_catalog=_catalog(),
    )

    targets = {
        item.target_id
        for item in result.items
        if item.kind == "statement_evidence" and item.source_id == "R1"
    }
    assert {"E:symbol:X", "E:symbol:Z"} <= targets
    assert result.coverage.requirement_ids_without_evidence_candidates == ()


def test_claim_bridge_adds_candidate_without_becoming_required() -> None:
    catalog = EvidenceCatalog(
        items=(
            EvidenceItem(
                id="E:symbol:Y",
                kind="symbol",
                summary="Changed adapter entrypoint",
                classification="code",
                changed=True,
                metadata={
                    "symbol_id": "Y",
                    "qualified_name": "src.adapter.entrypoint",
                    "path": "src/adapter.py",
                },
            ),
        ),
    )
    result = build_candidate_bindings(
        requirements=(
            Requirement(id="R1", text="Bounded delivery must be supported."),
        ),
        objectives=(),
        claims=(
            ReviewStatement(
                id="C1",
                text="Bounded delivery is implemented by the adapter entrypoint.",
                role="claim",
                authority="pr_description",
            ),
        ),
        evidence_catalog=catalog,
    )

    binding = next(
        item
        for item in result.items
        if item.kind == "statement_evidence"
        and item.source_id == "R1"
        and item.target_id == "E:symbol:Y"
    )
    assert {
        reason.feature for reason in binding.reasons
    } == {"requirement_claim_alignment", "claim_evidence_bridge"}
    assert binding.relation == "candidate_support"


def test_binding_ids_and_budget_are_deterministic() -> None:
    arguments = {
        "requirements": (
            Requirement(id="R1", text="Adapter core persistence processing."),
        ),
        "objectives": (),
        "claims": (),
        "evidence_catalog": _catalog(),
        "policy": CandidateBindingPolicy(max_per_statement=1, max_total=2),
    }

    first = build_candidate_bindings(**arguments)
    second = build_candidate_bindings(**arguments)

    assert [item.id for item in first.items] == [item.id for item in second.items]
    assert len(first.items) == 1
    assert [item.code for item in first.diagnostics] == [
        "candidate_binding_budget_reached"
    ]


def test_analyzer_serializes_candidates_without_using_them_as_status() -> None:
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=12,
        title="Connect adapter",
        source_records=(
            SourceRecord(
                id="pr:12",
                kind="pull_request",
                repository="acme/widget",
                body=(
                    "Connect the adapter safely.\n\n"
                    "## Requirements\n- Core processing remains bounded.\n\n"
                    "## Summary\n- Connect adapter to core processing."
                ),
            ),
        ),
        changed_files=(
            ChangedFile(
                path="src/core_processing.py",
                patch="+def bounded_core_processing(): pass",
            ),
        ),
    ).with_revision()

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    serialized = brief.to_dict()

    assert brief.schema_version == "review_brief.v9"
    assert brief.candidate_bindings.schema_version == "candidate_binding_set.v1"
    assert any(
        item.kind == "requirement_claim"
        and item.source_id == "R1"
        and item.target_id == "C1"
        for item in brief.candidate_bindings.items
    )
    assert serialized["candidate_bindings"]["items"]
    assert [item.id for item in brief.requirements] == ["R1"]


def test_consistency_report_keeps_candidates_separate_from_conclusions() -> None:
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=13,
        title="Report consistency candidates",
        source_records=(
            SourceRecord(
                id="pr:13",
                kind="pull_request",
                repository="acme/widget",
                body=(
                    "Show review consistency.\n\n"
                    "## Requirements\n"
                    "- Core processing remains bounded.\n"
                    "- Manual color approval is recorded.\n\n"
                    "## Summary\n"
                    "- Connect core processing.\n"
                    "- Redesign unrelated navigation."
                ),
            ),
        ),
        changed_files=(
            ChangedFile(
                path="src/core.py",
                patch="+def bounded_core_processing(): pass",
            ),
            ChangedFile(path="docs/notes.md", patch="+miscellaneous notes"),
        ),
    ).with_revision()

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    html = render_html(brief)

    assert "Review checks" in html
    assert "PR criterion" in html
    assert "PR says" in html
    assert "Repository facts" in html
    assert "No acceptance conclusion" in html
    assert "candidate relation" in html
    assert "changed fact" in html
    assert "PR claim coverage" in html and "R2" in html
    assert "Requirement evidence coverage" in html
    assert "Claim evidence coverage" in html and "C2" in html
    assert "Claims without acceptance links" in html
    assert "Changed evidence without statement candidates" in html
    assert "Modified file: docs/notes.md" in html
    assert [item.id for item in brief.requirements] == ["R1", "R2"]


def test_claims_are_fallback_review_axis_when_acceptance_is_missing() -> None:
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=13,
        title="Report claim evidence",
        source_records=(
            SourceRecord(
                id="pr:13",
                kind="pull_request",
                repository="acme/widget",
                body="## Summary\n- Connect adapter to core processing.",
            ),
        ),
        changed_files=(
            ChangedFile(
                path="src/core_processing.py",
                patch="+def core_processing(): pass",
            ),
        ),
    ).with_revision()

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    html = render_html(brief)

    assert brief.requirements == ()
    assert "Requirement checks" not in html
    assert "Review context" not in html
    assert "Review checks" in html
    assert '<span class="req-id">C1</span>' in html
    assert "No acceptance link" in html
    assert "Modified file: src/core_processing.py" in html
    assert "Acceptance basis" in html


def test_hunk_text_binds_when_filename_has_no_requirement_terms() -> None:
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=14,
        title="Expose debug trace",
        source_records=(
            SourceRecord(
                id="pr:14",
                kind="pull_request",
                repository="acme/widget",
                body=(
                    "## Requirements\n"
                    "- State debug endpoint exposes the semantic trace.\n"
                ),
            ),
        ),
        changed_files=(
            ChangedFile(
                path="src/runtime.py",
                patch=(
                    "@@ -1 +1 @@\n"
                    "-return payload\n"
                    "+return state_debug_semantic_trace(payload)\n"
                ),
            ),
        ),
    ).with_revision()

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    binding = next(
        item
        for item in brief.candidate_bindings.items
        if item.kind == "statement_evidence" and item.source_id == "R1"
    )
    evidence = brief.evidence_catalog.by_id()[binding.target_id]

    assert evidence.kind == "changed_hunk"
    assert "semantic_trace" in evidence.metadata["patch_excerpt"]
    assert "term_overlap" in {reason.feature for reason in binding.reasons}


def test_report_limits_visible_candidates_without_discarding_bindings() -> None:
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=15,
        title="Bound core processing",
        source_records=(
            SourceRecord(
                id="pr:15",
                kind="pull_request",
                repository="acme/widget",
                body="## Requirements\n- Core processing remains bounded.\n",
            ),
        ),
        changed_files=tuple(
            ChangedFile(
                path=f"src/runtime_{index}.py",
                patch=(
                    "@@ -0,0 +1 @@\n"
                    f"+def bounded_core_processing_{index}(): pass\n"
                ),
            )
            for index in range(8)
        ),
    ).with_revision()

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    html = render_html(brief)
    bindings = [
        item
        for item in brief.candidate_bindings.items
        if item.kind == "statement_evidence" and item.source_id == "R1"
    ]

    assert len(bindings) == 8
    assert html.count("Changed hunk: src/runtime_") == 2
    assert len(brief.projection.slices[0].changed_evidence_ids) == 2
