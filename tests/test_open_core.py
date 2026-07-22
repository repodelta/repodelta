from dataclasses import fields
from pathlib import Path

import pytest

from prismcode.analysis import DeterministicAnalyzer
from prismcode.contracts import Requirement, ReviewSourcePacket
from prismcode.fixture import load_fixture
from prismcode.rendering import render_html, write_html


def test_fixture_to_requirement_first_html(tmp_path: Path) -> None:
    analysis_input = load_fixture("fixtures/pr574.json")
    brief = DeterministicAnalyzer().analyze(analysis_input)
    html = render_html(brief)

    assert "Requirement-first review brief" in html
    assert "Produce an inspect-only unit semantic alignment trace." in html
    assert "Implementation: observed · Verification: passed" in html
    assert "Implementation: observed · Verification: not observed" in html
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
    assert brief.assessments[0].verification.status == "passed"


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
