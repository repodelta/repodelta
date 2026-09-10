from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = (
    ROOT
    / "evaluations/structural-correctness/campaign-v1-1/scripts/"
    "run_pr208_canonical_lifecycle_verifier.py"
)
PLAN_PATH = (
    ROOT
    / "evaluations/structural-correctness/campaign-v1-1/"
    "rg-semantic-labeling-runs/"
    "pr-208.batch-001.canonical-lifecycle-execution-plan.json"
)


def _runner_module():
    spec = importlib.util.spec_from_file_location("canonical_lifecycle_runner", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _plan() -> dict:
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def _accepted_output(plan: dict) -> dict:
    proposal_path = ROOT / plan["authorized_input_artifacts"]["proposed_reference"]["path"]
    candidate_ids = [item["candidate_id"] for item in json.loads(proposal_path.read_text())["labels"]]
    return {
        "schema_version": "rg_semantic_ai_lifecycle_verifier_output.v1",
        "batch_id": plan["batch_id"],
        "proposed_reference_sha256": hashlib.sha256(
            proposal_path.read_bytes()
        ).hexdigest(),
        "decisions": [
            {"candidate_id": candidate_id, "decision": "accept", "note": "Reviewed."}
            for candidate_id in candidate_ids
        ],
        "out_of_universe_review": "accept_empty",
        "final_status": "accepted",
    }


def test_canonical_lifecycle_plan_binds_runner_and_frozen_inputs() -> None:
    runner = _runner_module()
    plan = _plan()

    assert plan["execution"]["provider_reported_model_required"] is True
    assert plan["execution"]["payload_contract"]["temperature"] == (
        "not_emitted_by_canonical_adapter"
    )
    assert plan["runner"]["path"] == str(RUNNER_PATH.relative_to(ROOT))
    assert plan["runner"]["sha256"] == hashlib.sha256(RUNNER_PATH.read_bytes()).hexdigest()
    assert set(runner._load_frozen_inputs(plan)) == {
        "protocol",
        "rubric",
        "labeler_input",
        "proposed_reference",
        "prompt",
        "output_schema",
    }


def test_canonical_lifecycle_output_requires_full_exact_candidate_universe() -> None:
    runner = _runner_module()
    plan = _plan()
    proposal_path = ROOT / plan["authorized_input_artifacts"]["proposed_reference"]["path"]
    valid = _accepted_output(plan)

    runner._validate_output(valid, plan=plan, proposal_path=proposal_path)

    invalid = {**valid, "decisions": valid["decisions"][:-1]}
    with pytest.raises(ValueError, match="candidate universe"):
        runner._validate_output(invalid, plan=plan, proposal_path=proposal_path)
