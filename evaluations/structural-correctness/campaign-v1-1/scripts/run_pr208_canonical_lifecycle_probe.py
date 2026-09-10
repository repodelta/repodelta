"""Run the one non-semantic execution-observability probe for PR 208 batch 001."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from repodelta.llm import (
    OpenAIShadowConfig,
    ShadowProviderFailure,
    complete_json_object,
)


ROOT = Path(__file__).resolve().parents[4]
PLAN_SCHEMA = "rg_semantic_canonical_lifecycle_probe_plan.v1"
OUTPUT_SCHEMA = "rg_semantic_canonical_lifecycle_probe_output.v1"
ATTEMPT_SCHEMA = "rg_semantic_canonical_lifecycle_probe_attempt.v1"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("canonical lifecycle probe plan is invalid") from exc
    if not isinstance(value, Mapping):
        raise ValueError("canonical lifecycle probe plan must be an object")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"canonical lifecycle probe {field} is invalid")
    return value


def _root_relative_path(value: object) -> Path:
    path = (ROOT / _text(value, "artifact path")).resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError("canonical lifecycle probe artifact escapes repository") from exc
    return path


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_canonical_json(value), encoding="utf-8")


def _load(plan_path: Path) -> tuple[Mapping[str, Any], Path, Mapping[str, Any]]:
    plan = _read_json(plan_path)
    if plan.get("schema_version") != PLAN_SCHEMA:
        raise ValueError("unsupported canonical lifecycle probe plan")
    runner = plan.get("runner")
    if (
        not isinstance(runner, Mapping)
        or runner.get("path") != str(Path(__file__).relative_to(ROOT))
        or runner.get("sha256") != _digest(Path(__file__))
    ):
        raise ValueError("canonical lifecycle probe runner identity is invalid")
    artifacts = plan.get("authorized_input_artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("canonical lifecycle probe input artifacts are invalid")
    prompt_record = artifacts.get("prompt")
    if not isinstance(prompt_record, Mapping):
        raise ValueError("canonical lifecycle probe prompt record is invalid")
    prompt = _root_relative_path(prompt_record.get("path"))
    if prompt_record.get("sha256") != _digest(prompt):
        raise ValueError("canonical lifecycle probe prompt digest mismatch")
    execution = plan.get("execution")
    if not isinstance(execution, Mapping):
        raise ValueError("canonical lifecycle probe execution contract is invalid")
    return plan, prompt, execution


def _attempt_base(plan_path: Path, plan: Mapping[str, Any], execution: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": ATTEMPT_SCHEMA,
        "attempt_id": _text(plan.get("attempt_id"), "attempt_id"),
        "phase": "non_semantic_execution_probe",
        "plan_path": str(plan_path.relative_to(ROOT)),
        "plan_sha256": _digest(plan_path),
        "runner_path": str(Path(__file__).relative_to(ROOT)),
        "runner_sha256": _digest(Path(__file__)),
        "execution_date": _text(plan.get("execution_date"), "execution_date"),
        "provider": _text(execution.get("provider"), "provider"),
        "endpoint_class": _text(execution.get("endpoint_class"), "endpoint_class"),
        "configured_model_id": _text(
            execution.get("configured_model_id"), "configured_model_id"
        ),
        "raw_provider_response_retained": False,
        "provider_error_text_retained": False,
        "repository_or_candidate_data_sent": False,
    }


def _config(execution: Mapping[str, Any]) -> OpenAIShadowConfig:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip()
    if not api_key or base_url != execution.get("base_url"):
        raise ValueError("canonical lifecycle probe provider configuration is unavailable")
    config = OpenAIShadowConfig(
        api_key=api_key,
        model=_text(execution.get("configured_model_id"), "configured_model_id"),
        base_url=base_url,
        timeout_seconds=float(execution.get("timeout_seconds")),
        max_output_tokens=int(execution.get("max_output_tokens")),
        api_profile=_text(execution.get("api_profile"), "api_profile"),
        thinking_mode=_text(execution.get("thinking_mode"), "thinking_mode"),
        reasoning_effort=_text(execution.get("reasoning_effort"), "reasoning_effort"),
    )
    if config.execution_policy.identity != execution.get("policy_identity"):
        raise ValueError("canonical lifecycle probe policy identity is invalid")
    return config


def run(plan_path: Path, output_path: Path, attempt_path: Path) -> int:
    plan, prompt_path, execution = _load(plan_path)
    config = _config(execution)
    attempt = _attempt_base(plan_path, plan, execution)
    _write(attempt_path, {**attempt, "state": "started"})
    try:
        completion = complete_json_object(
            config,
            system_prompt=prompt_path.read_text(encoding="utf-8"),
            user_content="Return the frozen probe result.",
            require_provider_reported_model=True,
        )
        if completion.output != {"status": "ok"}:
            raise ValueError("canonical lifecycle probe response contract is invalid")
        output = {
            "schema_version": OUTPUT_SCHEMA,
            "attempt_id": attempt["attempt_id"],
            "status": "ok",
            "configured_model_id": completion.configured_model_id,
            "provider_reported_model_id": completion.provider_reported_model_id,
            "policy_identity": config.execution_policy.identity,
        }
        _write(output_path, output)
        _write(
            attempt_path,
            {
                **attempt,
                "state": "succeeded",
                "provider_reported_model_id": completion.provider_reported_model_id,
                "policy_identity": config.execution_policy.identity,
                "input_tokens": completion.input_tokens,
                "output_tokens": completion.output_tokens,
                "structured_output_path": str(output_path),
                "structured_output_sha256": _digest(output_path),
                "structured_output_retained": True,
            },
        )
        print(json.dumps({"outcome": "success", "attempt_id": attempt["attempt_id"]}))
        return 0
    except ShadowProviderFailure as exc:
        _write(
            attempt_path,
            {
                **attempt,
                "state": "provider_failure",
                "failure_category": exc.kind,
                "structured_output_retained": False,
            },
        )
        print(json.dumps({"outcome": "provider_failure", "failure_category": exc.kind}))
        return 2
    except Exception:
        _write(
            attempt_path,
            {**attempt, "state": "local_contract_failure", "structured_output_retained": False},
        )
        print(json.dumps({"outcome": "local_contract_failure"}))
        return 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--attempt", type=Path, required=True)
    args = parser.parse_args()
    try:
        return run(args.plan.resolve(), args.output.resolve(), args.attempt.resolve())
    except Exception:
        print(json.dumps({"outcome": "local_contract_failure"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
