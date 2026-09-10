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
    "run_pr208_canonical_lifecycle_probe.py"
)
PLAN = (
    ROOT
    / "evaluations/structural-correctness/campaign-v1-1/rg-semantic-labeling-runs/"
    "pr-208.batch-001.canonical-lifecycle-probe-plan.json"
)


def _module():
    spec = importlib.util.spec_from_file_location("rg_canonical_lifecycle_probe", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_probe_persists_started_record_before_canonical_completion(
    monkeypatch, tmp_path: Path
) -> None:
    module = _module()
    output = tmp_path / "probe-output.json"
    attempt = tmp_path / "probe-attempt.json"
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")

    def complete(config, **kwargs):
        started = json.loads(attempt.read_text(encoding="utf-8"))
        assert started["state"] == "started"
        assert started["repository_or_candidate_data_sent"] is False
        assert kwargs["require_provider_reported_model"] is True
        return SimpleNamespace(
            output={"status": "ok"},
            configured_model_id=config.model,
            provider_reported_model_id="deepseek-v4-pro",
            input_tokens=11,
            output_tokens=3,
        )

    monkeypatch.setattr(module, "complete_json_object", complete)

    assert module.run(PLAN, output, attempt) == 0

    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "ok"
    completed = json.loads(attempt.read_text(encoding="utf-8"))
    assert completed["state"] == "succeeded"
    assert completed["provider_reported_model_id"] == "deepseek-v4-pro"
    assert completed["raw_provider_response_retained"] is False


def test_probe_records_safe_provider_failure_without_output(
    monkeypatch, tmp_path: Path
) -> None:
    module = _module()
    output = tmp_path / "probe-output.json"
    attempt = tmp_path / "probe-attempt.json"
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")

    def complete(*_args, **_kwargs):
        raise ShadowProviderFailure("timeout")

    monkeypatch.setattr(module, "complete_json_object", complete)

    assert module.run(PLAN, output, attempt) == 2

    record = json.loads(attempt.read_text(encoding="utf-8"))
    assert record["state"] == "provider_failure"
    assert record["failure_category"] == "timeout"
    assert record["provider_error_text_retained"] is False
    assert not output.exists()
