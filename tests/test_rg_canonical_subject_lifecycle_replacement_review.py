from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from repodelta.llm import ShadowProviderFailure


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "evaluations/structural-correctness/campaign-v1-1/scripts/"
    "run_pr208_canonical_subject_lifecycle_replacement_review.py"
)
PLAN = (
    ROOT
    / "evaluations/structural-correctness/campaign-v1-1/rg-semantic-labeling-runs/"
    "pr-208.batch-001.canonical-subject-lifecycle-replacement-plan.json"
)


def _module():
    spec = importlib.util.spec_from_file_location(
        "rg_canonical_subject_lifecycle_replacement", SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _accepted_output(module, subject_id: str) -> dict[str, object]:
    plan, artifacts, _execution = module._load(PLAN)
    bundle, candidate_ids = module._subject_bundle(artifacts, subject_id)
    return {
        "schema_version": "rg_semantic_canonical_subject_lifecycle_output.v1",
        "batch_id": plan["batch_id"],
        "subject_id": subject_id,
        "subject_bundle_sha256": module._bundle_digest(bundle),
        "decisions": [
            {"candidate_id": candidate_id, "decision": "accept", "note": "Source evidence supports the proposed label."}
            for candidate_id in candidate_ids
        ],
        "out_of_universe_review": "accept_empty",
        "final_status": "accepted",
    }


def test_subject_plan_partitions_the_frozen_universe_into_six_candidate_reviews() -> None:
    module = _module()
    plan, artifacts, _execution = module._load(PLAN)

    candidate_ids: list[str] = []
    for subject_id in plan["subject_ids"]:
        _bundle, subject_candidates = module._subject_bundle(artifacts, subject_id)
        assert len(subject_candidates) == 6
        candidate_ids.extend(subject_candidates)

    assert len(candidate_ids) == 54
    assert len(candidate_ids) == len(set(candidate_ids))
    assert plan["execution"]["thinking_mode"] == "disabled"


def test_subject_review_persists_started_before_canonical_completion(
    monkeypatch, tmp_path: Path
) -> None:
    module = _module()
    output = tmp_path / "subject-output.json"
    attempt = tmp_path / "subject-attempt.json"
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")

    def complete(config, **kwargs):
        started = json.loads(attempt.read_text(encoding="utf-8"))
        assert started["state"] == "started"
        assert started["subject_id"] == "G1"
        assert started["repository_and_candidate_data_authorized_for_dispatch"]
        assert kwargs["require_provider_reported_model"] is True
        assert started["subject_bundle_sha256"] in kwargs["user_content"]
        return SimpleNamespace(
            output=_accepted_output(module, "G1"),
            configured_model_id=config.model,
            provider_reported_model_id="deepseek-v4-pro",
            input_tokens=400,
            output_tokens=120,
        )

    monkeypatch.setattr(module, "complete_json_object", complete)

    assert module.run(PLAN, "G1", output, attempt) == 0

    assert json.loads(output.read_text(encoding="utf-8"))["final_status"] == "accepted"
    record = json.loads(attempt.read_text(encoding="utf-8"))
    assert record["state"] == "succeeded"
    assert record["decision_count"] == 6
    assert record["raw_provider_response_retained"] is False


def test_subject_review_preserves_safe_provider_failure_without_output(
    monkeypatch, tmp_path: Path
) -> None:
    module = _module()
    output = tmp_path / "subject-output.json"
    attempt = tmp_path / "subject-attempt.json"
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setattr(
        module,
        "complete_json_object",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ShadowProviderFailure("structured_output_missing")
        ),
    )

    assert module.run(PLAN, "G1", output, attempt) == 2

    record = json.loads(attempt.read_text(encoding="utf-8"))
    assert record["state"] == "provider_failure"
    assert record["failure_category"] == "structured_output_missing"
    assert record["provider_error_text_retained"] is False
    assert not output.exists()
