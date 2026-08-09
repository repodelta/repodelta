from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from prismcode.cli import main
from prismcode.evaluation.core import (
    evaluate_suite,
    load_evaluation_suite,
    write_evaluation_json,
    write_evaluation_markdown,
)


SUITE_PATH = Path("fixtures/evaluation-suite.json")
HUMAN_LABELS_PATH = Path("fixtures/llm-shadow/human-labels.json")


def _absolute_case_paths(case: dict[str, object]) -> dict[str, object]:
    resolved = {
        **case,
        "fixture": str((SUITE_PATH.parent / str(case["fixture"])).resolve()),
    }
    if case.get("shadow_execution") is not None:
        resolved["shadow_execution"] = str(
            (SUITE_PATH.parent / str(case["shadow_execution"])).resolve()
        )
    if case.get("human_shadow_labels") is not None:
        resolved["human_shadow_labels"] = str(
            (SUITE_PATH.parent / str(case["human_shadow_labels"])).resolve()
        )
    return resolved


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
    assert result.metrics.focus_accuracy == 1.0
    assert len(result.statements) == 10
    assert len(result.assessments) == 13
    assert len(result.focus_outcomes) == 8
    assert result.shadow_metrics.outcome_count == 4
    assert result.shadow_metrics.human_labeled_outcome_count == 1
    assert result.shadow_metrics.candidate_label_count == 4
    assert result.shadow_metrics.selection_precision == 1.0
    assert result.shadow_metrics.selection_recall == 1.0
    assert result.shadow_metrics.role_accuracy == 1.0
    assert result.shadow_metrics.disposition_accuracy == 1.0
    assert result.shadow_metrics.false_rejection_rate == 0.0
    assert result.shadow_metrics.insufficient_recall == 1.0
    assert result.shadow_metrics.baseline_retention == 1.0
    assert result.shadow_metrics.unresolved_precision == 1.0
    assert result.shadow_metrics.unresolved_recall == 1.0
    assert result.shadow_metrics.state_accuracy == 1.0
    assert result.shadow_metrics.diagnostic_accuracy == 1.0
    assert result.shadow_metrics.replay_count == 2
    assert result.shadow_metrics.live_count == 0
    assert result.shadow_metrics.total_input_tokens == 160
    assert result.shadow_metrics.total_output_tokens == 30
    assert result.shadow_metrics.execution_policy_ids == (
        "shadow-policy:47e3c8427289b932d231",
    )
    assert result.shadow_metrics.total_duration_ms == 20.5


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
    assert payload["schema_version"] == "evaluation_result.v6"
    assert payload["queries"][0]["case_id"] == "direct-hunk-and-no-match"


def test_wrong_slot_expectation_fails_the_gate_and_cli(
    tmp_path: Path,
    monkeypatch,
) -> None:
    raw = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    raw["cases"][0]["expected_selections"][0]["target_id"] = "E:not-present"
    raw["cases"] = [_absolute_case_paths(case) for case in raw["cases"]]
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
                expected_focus_outcomes=(),
                shadow_execution=None,
                human_shadow_labels=None,
                expected_shadow_outcomes=(),
            )
            for case in suite.cases
        ),
    )

    result = evaluate_suite(empty, suite_path=SUITE_PATH)

    assert result.passed is False
    assert (
        "threshold_failed: no projection, assessment, focus, or shadow assertions were declared"
        in result.diagnostics
    )


def test_wrong_shadow_mapping_fails_the_gate(tmp_path: Path) -> None:
    raw = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    shadow_case = next(
        case for case in raw["cases"] if case["id"] == "llm-shadow-semantic-mapping"
    )
    labels = json.loads(HUMAN_LABELS_PATH.read_text(encoding="utf-8"))
    labels["labels"][0]["response"]["selections"][0]["semantic_role"] = (
        "consumer"
    )
    label_path = tmp_path / "human-labels.json"
    label_path.write_text(json.dumps(labels), encoding="utf-8")
    shadow_case["human_shadow_labels"] = str(label_path)
    raw["cases"] = [_absolute_case_paths(case) for case in raw["cases"]]
    suite_path = tmp_path / "failing-shadow-suite.json"
    suite_path.write_text(json.dumps(raw), encoding="utf-8")

    result = evaluate_suite(load_evaluation_suite(suite_path), suite_path=suite_path)

    assert result.passed is False
    assert result.shadow_metrics.role_accuracy < 1.0
    assert any("shadow_role_mismatch" in item for item in result.diagnostics)


def test_human_shadow_disposition_divergence_fails_the_gate(
    tmp_path: Path,
) -> None:
    raw = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    shadow_case = next(
        case for case in raw["cases"] if case["id"] == "llm-shadow-semantic-mapping"
    )
    labels = json.loads(HUMAN_LABELS_PATH.read_text(encoding="utf-8"))
    response = labels["labels"][0]["response"]
    response["selections"][0] = {
        "evidence_id": "E:context",
        "role": "context",
        "semantic_role": "documentation",
        "rationale": "Human review treats the document as claim context.",
    }
    response["rejected_evidence_ids"] = ["E:authority"]
    label_path = tmp_path / "divergent-human-labels.json"
    label_path.write_text(json.dumps(labels), encoding="utf-8")
    shadow_case["human_shadow_labels"] = str(label_path)
    raw["cases"] = [_absolute_case_paths(case) for case in raw["cases"]]
    suite_path = tmp_path / "divergent-shadow-suite.json"
    suite_path.write_text(json.dumps(raw), encoding="utf-8")

    result = evaluate_suite(load_evaluation_suite(suite_path), suite_path=suite_path)

    assert result.passed is False
    assert result.shadow_metrics.disposition_accuracy == 0.5
    assert result.shadow_metrics.false_rejection_rate == 0.5
    assert any("shadow_disposition_mismatch" in item for item in result.diagnostics)


def test_incomplete_human_shadow_labels_fail_closed(tmp_path: Path) -> None:
    raw = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    shadow_case = next(
        case for case in raw["cases"] if case["id"] == "llm-shadow-semantic-mapping"
    )
    labels = json.loads(HUMAN_LABELS_PATH.read_text(encoding="utf-8"))
    labels["labels"][0]["response"]["rejected_evidence_ids"] = []
    label_path = tmp_path / "incomplete-human-labels.json"
    label_path.write_text(json.dumps(labels), encoding="utf-8")
    shadow_case["human_shadow_labels"] = str(label_path)
    raw["cases"] = [_absolute_case_paths(case) for case in raw["cases"]]
    suite_path = tmp_path / "incomplete-shadow-suite.json"
    suite_path.write_text(json.dumps(raw), encoding="utf-8")

    suite = load_evaluation_suite(suite_path)
    with pytest.raises(ValueError, match="incomplete_candidate_partition"):
        evaluate_suite(suite, suite_path=suite_path)


def test_mismatched_human_shadow_request_fails_closed(tmp_path: Path) -> None:
    raw = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    shadow_case = next(
        case for case in raw["cases"] if case["id"] == "llm-shadow-semantic-mapping"
    )
    labels = json.loads(HUMAN_LABELS_PATH.read_text(encoding="utf-8"))
    labels["labels"][0]["response"]["request_id"] = "shadow:other-request"
    label_path = tmp_path / "mismatched-human-labels.json"
    label_path.write_text(json.dumps(labels), encoding="utf-8")
    shadow_case["human_shadow_labels"] = str(label_path)
    raw["cases"] = [_absolute_case_paths(case) for case in raw["cases"]]
    suite_path = tmp_path / "mismatched-shadow-suite.json"
    suite_path.write_text(json.dumps(raw), encoding="utf-8")

    suite = load_evaluation_suite(suite_path)
    with pytest.raises(ValueError, match="request_mismatch"):
        evaluate_suite(suite, suite_path=suite_path)


def test_legacy_embedded_shadow_semantics_are_rejected(tmp_path: Path) -> None:
    raw = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    shadow_case = next(
        case for case in raw["cases"] if case["id"] == "llm-shadow-semantic-mapping"
    )
    shadow_case["expected_shadow_outcomes"][0]["selections"] = []
    raw["cases"] = [_absolute_case_paths(case) for case in raw["cases"]]
    suite_path = tmp_path / "legacy-shadow-suite.json"
    suite_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported fields: selections"):
        load_evaluation_suite(suite_path)


def test_wrong_assessment_expectation_fails_the_gate_and_cli(
    tmp_path: Path,
    monkeypatch,
) -> None:
    raw = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    assessment_case = next(
        case for case in raw["cases"] if case["id"] == "transformation-assessment-proof"
    )
    assessment_case["expected_assessments"][0]["status"] = "partial"
    raw["cases"] = [_absolute_case_paths(case) for case in raw["cases"]]
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


def test_wrong_focus_expectation_fails_the_gate_and_cli(
    tmp_path: Path,
    monkeypatch,
) -> None:
    raw = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    focus_case = next(
        case for case in raw["cases"] if case["id"] == "focus-and-closure-outcomes"
    )
    focus_case["expected_focus_outcomes"][0]["disposition"] = "projected"
    raw["cases"] = [_absolute_case_paths(case) for case in raw["cases"]]
    suite_path = tmp_path / "failing-focus-suite.json"
    suite_path.write_text(json.dumps(raw), encoding="utf-8")

    result = evaluate_suite(load_evaluation_suite(suite_path), suite_path=suite_path)

    assert result.passed is False
    assert result.metrics.focus_accuracy < 1.0
    assert any("focus_mismatch" in item for item in result.diagnostics)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prismcode",
            "evaluate",
            "--suite",
            str(suite_path),
            "--json-output",
            str(tmp_path / "focus-result.json"),
            "--markdown-output",
            str(tmp_path / "focus-result.md"),
        ],
    )
    assert main() == 1
