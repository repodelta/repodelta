from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

from prismcode.cli import main
from prismcode.evaluation.core import (
    evaluate_suite,
    load_evaluation_suite,
    write_evaluation_json,
    write_evaluation_markdown,
)


SUITE_PATH = Path("fixtures/evaluation-suite.json")


def test_golden_suite_covers_typed_slots_structure_and_profiles() -> None:
    suite = load_evaluation_suite(SUITE_PATH)
    result = evaluate_suite(suite, suite_path=SUITE_PATH)

    assert result.passed is True
    assert result.metrics.query_count == 10
    assert result.metrics.positive_query_count == 9
    assert result.metrics.negative_query_count == 1
    assert result.metrics.precision_at_k == 1.0
    assert result.metrics.recall_at_k == 1.0
    assert result.metrics.no_match_accuracy == 1.0
    assert result.metrics.classification_accuracy == 1.0
    assert result.metrics.statement_accuracy == 1.0
    assert result.metrics.assessment_accuracy == 1.0
    assert len(result.statements) == 10
    assert len(result.assessments) == 13


def test_evaluation_outputs_are_byte_stable(tmp_path: Path) -> None:
    suite = load_evaluation_suite(SUITE_PATH)
    result = evaluate_suite(suite, suite_path=SUITE_PATH)
    first_json = write_evaluation_json(result, tmp_path / "first.json")
    second_json = write_evaluation_json(result, tmp_path / "second.json")
    first_markdown = write_evaluation_markdown(result, tmp_path / "first.md")
    second_markdown = write_evaluation_markdown(result, tmp_path / "second.md")

    assert first_json.read_bytes() == second_json.read_bytes()
    assert first_markdown.read_bytes() == second_markdown.read_bytes()
    payload = json.loads(first_json.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "evaluation_result.v3"
    assert payload["queries"][0]["case_id"] == "direct-hunk-and-no-match"


def test_wrong_slot_expectation_fails_the_gate_and_cli(
    tmp_path: Path,
    monkeypatch,
) -> None:
    raw = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    raw["cases"][0]["expected_selections"][0]["target_id"] = "E:not-present"
    raw["cases"] = [
        {
            **case,
            "fixture": str((SUITE_PATH.parent / case["fixture"]).resolve()),
        }
        for case in raw["cases"]
    ]
    suite_path = tmp_path / "failing-suite.json"
    suite_path.write_text(json.dumps(raw), encoding="utf-8")
    suite = load_evaluation_suite(suite_path)
    result = evaluate_suite(suite, suite_path=suite_path)

    assert result.passed is False
    assert any("slot=changed_anchor" in item for item in result.diagnostics)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prismcode",
            "evaluate",
            "--suite",
            str(suite_path),
            "--json-output",
            str(tmp_path / "result.json"),
            "--markdown-output",
            str(tmp_path / "result.md"),
        ],
    )
    assert main() == 1


def test_evaluation_requires_declared_projection_expectations() -> None:
    suite = load_evaluation_suite(SUITE_PATH)
    empty = replace(
        suite,
        cases=tuple(
            replace(
                case,
                expected_selections=(),
                expected_no_selections=(),
                expected_assessments=(),
            )
            for case in suite.cases
        ),
    )

    result = evaluate_suite(empty, suite_path=SUITE_PATH)

    assert result.passed is False
    assert "threshold_failed: no projection or assessment assertions were declared" in (
        result.diagnostics
    )


def test_wrong_assessment_expectation_fails_the_gate_and_cli(
    tmp_path: Path,
    monkeypatch,
) -> None:
    raw = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    assessment_case = next(
        case for case in raw["cases"] if case["id"] == "transformation-assessment-proof"
    )
    assessment_case["expected_assessments"][0]["status"] = "partial"
    raw["cases"] = [
        {
            **case,
            "fixture": str((SUITE_PATH.parent / case["fixture"]).resolve()),
        }
        for case in raw["cases"]
    ]
    suite_path = tmp_path / "failing-assessment-suite.json"
    suite_path.write_text(json.dumps(raw), encoding="utf-8")

    result = evaluate_suite(load_evaluation_suite(suite_path), suite_path=suite_path)

    assert result.passed is False
    assert result.metrics.assessment_accuracy < 1.0
    assert any("assessment_mismatch" in item for item in result.diagnostics)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prismcode",
            "evaluate",
            "--suite",
            str(suite_path),
            "--json-output",
            str(tmp_path / "assessment-result.json"),
            "--markdown-output",
            str(tmp_path / "assessment-result.md"),
        ],
    )
    assert main() == 1
