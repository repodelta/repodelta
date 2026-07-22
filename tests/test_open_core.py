from dataclasses import fields
from pathlib import Path

import pytest

from prismcode.analysis import DeterministicAnalyzer
from prismcode.contracts import (
    AnalysisInput,
    Evidence,
    EvidenceHint,
    Requirement,
    ReviewSourcePacket,
    VerificationObservation,
)
from prismcode.fixture import load_fixture
from prismcode.rendering import render_html, write_html


def test_fixture_to_requirement_first_html(tmp_path: Path) -> None:
    analysis_input = load_fixture("fixtures/pr574.json")
    brief = DeterministicAnalyzer().analyze(analysis_input)
    html = render_html(brief)

    assert "Requirement-first review brief" in html
    assert "Existing semantic spine artifacts are reused." in html
    assert "unit_semantic_alignment_trace" in html
    assert "inspect_only_debug_artifacts" in html
    assert "R1" in html and "R5" in html
    assert "G1" in html and "G5" in html
    assert "Implementation observed · Verification not observed" in html
    assert "6 changed files" in html
    assert "CI/Actions observations" in html
    assert "Needs attention" in html
    assert "Implemented" in html
    assert "Verification" in html
    assert "Gaps" in html

    output = write_html(brief, tmp_path / "review.html")
    assert output.read_text(encoding="utf-8") == html


def test_requirements_are_conclusion_free_and_analyzer_owns_status() -> None:
    analysis_input = load_fixture("fixtures/pr574.json")
    requirement_fields = {item.name for item in fields(Requirement)}
    assert not {"status", "implemented", "verification", "gaps"} & requirement_fields

    brief = DeterministicAnalyzer().analyze(analysis_input)
    assert brief.assessments[0].implementation.status == "observed"
    assert brief.assessments[0].verification.status == "not_observed"
    assert len(brief.assessments) == 5
    assert len(brief.guardrails) == 5


def test_current_head_requirement_specific_check_can_verify_requirement() -> None:
    base = load_fixture("fixtures/pr574.json")
    packet = ReviewSourcePacket(
        **{
            **base.packet.__dict__,
            "verification_observations": (
                VerificationObservation(
                    id="check:requirement-r1",
                    name="test_r1_trace_reuses_semantic_spine",
                    kind="check_run",
                    status="completed",
                    conclusion="success",
                    head_sha=base.packet.head_sha,
                ),
            ),
            "packet_revision": "",
        }
    ).with_revision()
    hint = EvidenceHint(
        requirement_id="R1",
        implementation=(Evidence(summary="R1 implementation", kind="code"),),
        verification_evidence_ids=("check:requirement-r1",),
        assertion_coverage="adequate",
    )
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet, evidence_hints=(hint,)))
    assert brief.assessments[0].verification.status == "passed"


def test_success_from_another_head_is_stale_not_passed() -> None:
    base = load_fixture("fixtures/pr574.json")
    packet = ReviewSourcePacket(
        **{
            **base.packet.__dict__,
            "verification_observations": (
                VerificationObservation(
                    id="check:stale",
                    name="test_r1",
                    kind="check_run",
                    status="completed",
                    conclusion="success",
                    head_sha="older-head",
                ),
            ),
            "packet_revision": "",
        }
    ).with_revision()
    hint = EvidenceHint(
        requirement_id="R1",
        implementation=(Evidence(summary="R1 implementation", kind="code"),),
        verification_evidence_ids=("check:stale",),
        assertion_coverage="adequate",
    )
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet, evidence_hints=(hint,)))
    assert brief.assessments[0].verification.status == "stale"


def test_source_packet_detects_content_inconsistency() -> None:
    packet = load_fixture("fixtures/pr574.json").packet
    tampered = ReviewSourcePacket(
        **{**packet.__dict__, "title": "tampered"}
    )
    with pytest.raises(ValueError, match="packet_revision"):
        tampered.validate_consistency()


def test_unsafe_source_url_is_not_rendered_as_link(tmp_path: Path) -> None:
    analysis_input = load_fixture("fixtures/pr574.json")
    packet = analysis_input.packet
    unsafe = ReviewSourcePacket(
        **{**packet.__dict__, "source_url": "javascript:alert(1)", "packet_revision": ""}
    ).with_revision()
    html = render_html(
        DeterministicAnalyzer().analyze(
            type(analysis_input)(packet=unsafe, requirements=analysis_input.requirements)
        )
    )
    assert 'href="javascript:' not in html
