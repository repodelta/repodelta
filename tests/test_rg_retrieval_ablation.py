from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from repodelta.evaluation.rg_candidate_universe import (
    load_rg_candidate_universe,
    load_rg_retrieval_observation,
    load_rg_semantic_reference,
)
from repodelta.evaluation.rg_retrieval_ablation import (
    authored_query_terms,
    build_ablation_input,
    run_retrieval_ablation,
)


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "evaluations/structural-correctness/campaign-v1-1"
RUNNER = CAMPAIGN / "run_pr208_rg_retrieval_ablation.py"


def _runner_module():
    spec = importlib.util.spec_from_file_location("pr208_rg_retrieval_ablation", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _inputs():
    return (
        load_rg_candidate_universe(CAMPAIGN / "rg-candidate-universes/pr-208.json"),
        load_rg_retrieval_observation(
            CAMPAIGN / "rg-retrieval-observations/pr-208.json"
        ),
        load_rg_semantic_reference(
            CAMPAIGN
            / "rg-semantic-proposals/pr-208.batch-001.ai-adjudicated.proposed.json"
        ),
        json.loads(
            (
                CAMPAIGN / "rg-retrieval-ablation-history/pr-208.json"
            ).read_text(encoding="utf-8")
        ),
    )


def test_authored_terms_are_normalized_and_do_not_depend_on_semantic_labels() -> None:
    terms = authored_query_terms(
        "Focus-relative evidence annotation remains available for reviewer presentation."
    )
    assert terms == (
        "annotation",
        "evidence",
        "focus_relative",
        "presentation",
        "reviewer",
    )

    universe, retrieval, _, history = _inputs()
    known_ids = _runner_module().KNOWN_MISS_IDS
    ablation_input = build_ablation_input(
        universe,
        retrieval,
        known_miss_candidate_ids=known_ids,
        reviewed_head=_runner_module().REVIEWED_HEAD,
        repository_head=_runner_module().PRESENT_REPOSITORY_HEAD,
        history_manifest=history,
    )
    assert all(
        {"semantic_relation", "proofability", "proof_basis", "label"}
        .isdisjoint(diagnostic)
        for diagnostic in ablation_input["diagnostics"]
    )
    assert ablation_input["classification"]["semantic_relation"] == "not_input"


def test_history_terms_fail_closed_without_current_resolution() -> None:
    universe, retrieval, _, history = _inputs()
    runner = _runner_module()
    ablation_input = build_ablation_input(
        universe,
        retrieval,
        known_miss_candidate_ids=runner.KNOWN_MISS_IDS,
        reviewed_head=runner.REVIEWED_HEAD,
        repository_head=runner.PRESENT_REPOSITORY_HEAD,
        history_manifest=history,
    )
    source_index = ablation_input["candidate_source_index"]
    spans = {
        (item["source_span"] or {"path": None})["path"]
        for item in source_index
        if item["source_span"] is not None
    }
    legacy_package = "prism" + "code"
    assert spans == {f"src/{legacy_package}/projection/build.py", "tests/test_projection.py"}

    result = run_retrieval_ablation(
        ablation_input,
        read_revision_file=lambda _revision, path: "changed_anchor" if path else "",
        history_resolution={
            "H:issue-207:changed-anchor": {
                "term": "changed_anchor",
                "status": "superseded",
            }
        },
    )
    q2 = next(
        item
        for item in result["aggregate"]
        if item["mechanism"] == "Q2_history_vocabulary_then_reviewed_head_lexical"
    )
    assert q2["known_misses_recovered"] == 0
    assert q2["stale_history_candidates_introduced"] == 0


def test_pr208_ablation_is_reproducible_and_preserves_boundaries() -> None:
    runner = _runner_module()
    result = runner.build_pr208_rg_retrieval_ablation(CAMPAIGN, ROOT)
    committed = json.loads(
        (
            CAMPAIGN / "results/rg-retrieval-ablation/pr-208.json"
        ).read_text(encoding="utf-8")
    )
    assert json.loads(json.dumps(result)) == committed
    assert result["classification"] == {
        "kind": "evaluation_only_retrieval_ablation",
        "semantic_relation": "not_emitted",
        "proofability": "not_emitted",
        "admission_authority": "not_emitted",
        "production_changed": False,
        "semantic_or_model_search_run": False,
    }
    assert result["input"]["diagnostic_selection"]["candidate_ids"] == list(
        runner.KNOWN_MISS_IDS
    )
    assert result["completion"]["state"] == "sufficient_for_bounded_retrieval_hypothesis"
    aggregate = {item["mechanism"]: item for item in result["aggregate"]}
    assert aggregate["baseline_current_association"]["known_misses_recovered"] == 0
    assert aggregate["Q1_identifier_variants"]["known_misses_recovered"] == 0
    assert aggregate["Q0_authored_lexical"] == {
        "mechanism": "Q0_authored_lexical",
        "known_misses_recovered": 7,
        "incremental_recoveries": 7,
        "additional_candidate_count": 10,
        "additional_candidate_ids": [
            "C:G2:E:structural_change:44a2370ce77a6e66f8e7",
            "C:G2:E:structural_change:9ff44326982c1acafe85",
            "C:R2:E:structural_change:44a2370ce77a6e66f8e7",
            "C:R2:E:structural_change:5d2be31cc60dea3d2f3b",
            "C:R2:E:structural_change:7c4162e02e623fea377f",
            "C:R2:E:structural_change:d0cf036a1010c1207bc5",
            "C:R3:E:structural_change:9ff44326982c1acafe85",
            "C:R5:E:structural_change:5d2be31cc60dea3d2f3b",
            "C:R5:E:structural_change:9ff44326982c1acafe85",
            "C:R5:E:structural_change:d0cf036a1010c1207bc5",
        ],
        "stale_history_candidates_introduced": 0,
        "unresolved_cases": 0,
        "additional_candidate_interpretation": "unassessed retrieval candidates, not semantic-noise labels",
    }
    assert aggregate["Q2_history_vocabulary_then_reviewed_head_lexical"][
        "incremental_recoveries"
    ] == 0
    controls = {
        key: value
        for key, value in result["history_resolution"].items()
        if key.startswith("NC:")
    }
    assert {value["status"] for value in controls.values()} == {
        "renamed_or_replaced",
        "superseded",
    }
    assert all(value["current_fact_emitted"] is False for value in controls.values())


def test_materialized_input_replays_without_historical_git_objects() -> None:
    ablation_input = json.loads(
        (
            CAMPAIGN / "results/rg-retrieval-ablation/pr-208.input.json"
        ).read_text(encoding="utf-8")
    )
    replayed = run_retrieval_ablation(ablation_input)
    committed = json.loads(
        (
            CAMPAIGN / "results/rg-retrieval-ablation/pr-208.json"
        ).read_text(encoding="utf-8")
    )
    assert replayed["input_digest"] == committed["input_digest"]
    assert replayed["aggregate"] == committed["aggregate"]
    assert replayed["per_miss"] == committed["per_miss"]
    assert replayed["history_resolution"] == committed["history_resolution"]


def test_retrieval_input_rejects_semantic_label_leak() -> None:
    with pytest.raises(ValueError, match="leaked semantic-label input"):
        run_retrieval_ablation(
            {
                "schema_version": "rg_retrieval_ablation_input.v1",
                "classification": {
                    "semantic_relation": "not_input",
                    "proofability": "not_input",
                },
                "diagnostics": [{"candidate_id": "C:1", "semantic_relation": "implements"}],
            },
            read_revision_file=lambda _revision, _path: "",
            history_resolution={},
        )
