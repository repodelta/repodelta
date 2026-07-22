from pathlib import Path

from prismcode.analysis import DeterministicAnalyzer
from prismcode.fixture import load_fixture
from prismcode.rendering import render_html, write_html


def test_fixture_to_requirement_first_html(tmp_path: Path) -> None:
    review = load_fixture("fixtures/pr574.json")
    brief = DeterministicAnalyzer().analyze(review)
    html = render_html(brief)

    assert "Requirement-first review brief" in html
    assert "Produce an inspect-only unit semantic alignment trace." in html
    assert "Implemented" in html
    assert "Verification" in html
    assert "Gaps" in html
    assert "private" not in html.lower()

    output = write_html(brief, tmp_path / "review.html")
    assert output.exists()
    assert output.read_text(encoding="utf-8") == html


def test_missing_verification_is_explicit() -> None:
    brief = DeterministicAnalyzer().analyze(load_fixture("fixtures/pr574.json"))
    html = render_html(brief)
    assert "No verification evidence recorded." in html


def test_unsafe_source_url_is_not_rendered_as_link(tmp_path: Path) -> None:
    raw = """{
      "repository": "example/repo",
      "title": "Unsafe link",
      "intent": "Verify safe rendering.",
      "source_url": "javascript:alert(1)",
      "requirements": []
    }"""
    fixture = tmp_path / "unsafe.json"
    fixture.write_text(raw, encoding="utf-8")
    html = render_html(DeterministicAnalyzer().analyze(load_fixture(fixture)))
    assert 'href="javascript:' not in html
