from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

from prismcode.analysis import DeterministicAnalyzer
from prismcode.cli import main
from prismcode.evaluation import (
    evaluate_suite,
    load_evaluation_suite,
    write_evaluation_json,
    write_evaluation_markdown,
)
from prismcode.fixture import load_fixture


SUITE_PATH = Path("fixtures/evaluation-suite.json")


def test_golden_suite_covers_hunks_claims_structure_and_classification() -> None:
    suite = load_evaluation_suite(SUITE_PATH)
    result = evaluate_suite(suite, suite_path=SUITE_PATH)

    assert result.passed is True
    assert result.metrics.query_count == 5
    assert result.metrics.precision_at_k == 1.0
    assert result.metrics.recall_at_k == 1.0
    assert result.metrics.mean_reciprocal_rank == 1.0
    assert result.metrics.no_candidate_rate == 0.0
    assert result.metrics.classification_accuracy == 1.0
    no_match = next(
        item
        for item in result.queries
        if item.case_id == "direct-hunk-and-no-match"
        and item.source_id == "R2"
    )
    assert no_match.expected_target_ids == ()
    assert no_match.observed_target_ids == ()
    structural = next(
        item
        for item in result.queries
        if item.case_id == "bounded-y-x-z"
        and item.kind == "statement_evidence"
    )
    assert {
        "E:symbol:9e703e599343229d97c1",
        "E:symbol:51c78d1cf2a276cc9a40",
        "E:symbol:3c8a35c2cab106b983ca",
        "E:structural_path:01124120c3c65a9b12f3",
    } <= set(structural.observed_target_ids)


def test_exact_symbol_replaces_the_mapped_hunk_in_golden_case() -> None:
    suite = load_evaluation_suite(SUITE_PATH)
    case = next(item for item in suite.cases if item.id == "bounded-y-x-z")
    analysis_input = replace(
        load_fixture(case.fixture),
        structural_graph=case.structural_graph,
    )

    brief = DeterministicAnalyzer().analyze(analysis_input)
    evidence = brief.evidence_catalog.by_id()

    assert "E:symbol:9e703e599343229d97c1" in evidence
    assert not [
        item
        for item in evidence.values()
        if item.kind == "changed_hunk"
        and item.metadata.get("hunk_id") == "hunk:src/adapter.py:0"
    ]


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
    assert payload["schema_version"] == "evaluation_result.v1"
    assert payload["queries"][0]["case_id"] == "direct-hunk-and-no-match"


def test_threshold_failure_is_explicit_and_returns_nonzero(
    tmp_path: Path,
    monkeypatch,
) -> None:
    suite = load_evaluation_suite(SUITE_PATH)
    structural_path_id = "E:structural_path:01124120c3c65a9b12f3"
    failing = replace(
        suite,
        cases=tuple(
            replace(
                case,
                expected_bindings=tuple(
                    item
                    for item in case.expected_bindings
                    if item.target_id != structural_path_id
                ),
            )
            for case in suite.cases
        ),
    )
    result = evaluate_suite(failing, suite_path=SUITE_PATH)

    assert result.passed is False
    assert result.diagnostics == (
        "threshold_failed: precision_at_k=0.9500 is below 1.0000",
    )

    raw = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    raw["cases"][1]["expected_bindings"] = [
        item
        for item in raw["cases"][1]["expected_bindings"]
        if item["target_id"] != structural_path_id
    ]
    suite_path = tmp_path / "failing-suite.json"
    raw["cases"] = [
        {
            **case,
            "fixture": str((SUITE_PATH.parent / case["fixture"]).resolve()),
        }
        for case in raw["cases"]
    ]
    suite_path.write_text(json.dumps(raw), encoding="utf-8")
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
