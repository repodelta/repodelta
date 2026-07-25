from dataclasses import fields, replace
from pathlib import Path

import pytest

from prismcode.pipeline import DeterministicAnalyzer
from prismcode.model.contracts import (
    AnalysisInput,
    Requirement,
    ReviewSourcePacket,
    VerificationObservation,
)
from prismcode.intake.fixture import load_fixture
from prismcode.presentation.html import render_html, write_html


def test_fixture_to_requirement_first_html(tmp_path: Path) -> None:
    analysis_input = load_fixture("fixtures/pr574.json")
    brief = DeterministicAnalyzer().analyze(analysis_input)
    html = render_html(brief)

    assert "AI review brief · requirement-first" not in html
    assert "What this PR is trying to do" not in html
    assert '<details class="requirement" open>' in html
    assert 'class="brand-mark"' in html
    assert "Existing semantic spine artifacts are reused." in html
    assert "unit_semantic_alignment_trace" in html
    assert "inspect_only_debug_artifacts" in html
    assert "R1" in html and "R5" in html
    assert "G1" in html and "G5" in html
    assert "Implementation observed · Verification not observed" not in html
    assert "Implemented across" not in html
    assert "Tests present across" not in html
    assert "CI not observed" not in html
    assert "6 changed files" in html
    assert "5 delivery requirements" not in html
    assert "CI/Actions observations" not in html
    assert "PR #574" in html and "Merged" in html and "CI: no run observed" in html
    assert "Needs attention" in html
    assert "Implemented" in html
    assert '<span class="block-title">Verification</span>' not in html
    assert '<span class="block-title">Gaps</span>' not in html
    assert "No verification evidence recorded." not in html
    assert "Scope guardrails" in html
    assert "G5, R5 have no canonical evidence candidate" not in html
    assert "Collection notes" not in html
    assert "The trace builder consumes existing inspection units" in html
    assert "unit_semantic_alignment_trace.py" in html
    assert "test_workspace_public_review_map_routes.py" in html
    assert "https://github.com/interact-space/PrismCode/blob/7de0211956a35e8f9c6c576cd2dbb7acd7fd5560/prismcode/workspace/unit_semantic_alignment_trace.py" in html
    assert "Data sources &amp; coverage" not in html
    assert "Issue #573" in html and "PR #574" in html
    assert "Issue #573 · Acceptance criteria" in html
    assert "#acceptance-criteria" in html
    assert ">linked issue<" not in html
    assert '<span class="block-title">Expected</span>' not in html

    output = write_html(brief, tmp_path / "review.html")
    assert output.read_text(encoding="utf-8") == html


def test_requirements_and_brief_are_conclusion_free() -> None:
    analysis_input = load_fixture("fixtures/pr574.json")
    requirement_fields = {item.name for item in fields(Requirement)}
    assert not {"status", "implemented", "verification", "gaps"} & requirement_fields

    brief = DeterministicAnalyzer().analyze(analysis_input)
    brief_fields = {item.name for item in fields(type(brief))}
    assert "assessments" not in brief_fields
    assert len(brief.requirements) == 5
    assert len(brief.guardrails) == 5


def test_source_packet_detects_content_inconsistency() -> None:
    packet = load_fixture("fixtures/pr574.json").packet
    tampered = ReviewSourcePacket(
        **{**packet.__dict__, "title": "tampered"}
    )
    with pytest.raises(ValueError, match="packet_revision"):
        tampered.validate_consistency()


def test_top_level_ci_uses_only_canonical_current_head_state() -> None:
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=7,
        title="Stale CI",
        source_records=(),
        head_sha="current",
        verification_observations=(
            VerificationObservation(
                id="old",
                name="test",
                kind="check_run",
                status="completed",
                conclusion="success",
                head_sha="previous",
            ),
        ),
    ).with_revision()

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    assert brief.overview.ci_state == "not_observed"
    assert "CI: no run observed" in render_html(brief)
    assert "CI: passing" not in render_html(brief)


def test_unsafe_source_url_is_not_rendered_as_link(tmp_path: Path) -> None:
    analysis_input = load_fixture("fixtures/pr574.json")
    packet = analysis_input.packet
    source_records = tuple(
        replace(item, url="javascript:alert(1)")
        if item.kind == "pull_request"
        else item
        for item in packet.source_records
    )
    unsafe = ReviewSourcePacket(
        **{
            **packet.__dict__,
            "source_records": source_records,
            "source_url": "javascript:alert(1)",
            "packet_revision": "",
        }
    ).with_revision()
    html = render_html(
        DeterministicAnalyzer().analyze(
            type(analysis_input)(packet=unsafe, requirements=analysis_input.requirements)
        )
    )
    assert 'href="javascript:' not in html
