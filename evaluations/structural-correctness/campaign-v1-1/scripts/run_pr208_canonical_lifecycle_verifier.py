from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

from repodelta.llm import (
    OpenAIShadowConfig,
    ShadowProviderFailure,
    complete_json_object,
)


ROOT = Path(__file__).resolve().parents[4]
PLAN_SCHEMA = "rg_semantic_canonical_lifecycle_execution_plan.v1"
OUTPUT_SCHEMA = "rg_semantic_ai_lifecycle_verifier_output.v1"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative_path(value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("execution plan contains an invalid artifact path")
    path = (ROOT / value).resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError("execution plan artifact escapes the repository") from exc
    return path


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("execution plan JSON is invalid") from exc
    if not isinstance(value, Mapping):
        raise ValueError("execution plan must be a JSON object")
    return value


def _load_frozen_inputs(plan: Mapping[str, Any]) -> dict[str, Path]:
    if plan.get("schema_version") != PLAN_SCHEMA:
        raise ValueError("unsupported canonical lifecycle execution plan")
    raw = plan.get("authorized_input_artifacts")
    if not isinstance(raw, Mapping) or not raw:
        raise ValueError("execution plan has no authorized input artifacts")
    paths: dict[str, Path] = {}
    for name, value in raw.items():
        if not isinstance(name, str) or not isinstance(value, Mapping):
            raise ValueError("execution plan input record is invalid")
        path = _relative_path(value.get("path"))
        expected = value.get("sha256")
        if not isinstance(expected, str) or _digest(path) != expected:
            raise ValueError("frozen input digest mismatch")
        paths[name] = path
    return paths


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"lifecycle output {field} is invalid")
    return value


def _validate_recommended_label(value: object) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "semantic_relation",
        "proofability",
        "proof_basis",
        "evidence_witnesses",
    }:
        raise ValueError("lifecycle output recommended_label is invalid")
    if value.get("semantic_relation") not in {
        "implements",
        "constrains",
        "removes",
        "directly_verifies",
        "contextual_support",
        "unrelated",
        "insufficient",
    }:
        raise ValueError("lifecycle output recommended_label relation is invalid")
    if value.get("proofability") not in {
        "direct_capable",
        "suggested_only",
        "not_applicable",
        "insufficient",
    }:
        raise ValueError("lifecycle output recommended_label proofability is invalid")
    if value.get("proof_basis") not in {
        "explicit_authoring",
        "typed_predicate",
        "bounded_evidence",
        "deterministic_mapping",
        "heuristic",
        "model_suggestion",
        "none",
    }:
        raise ValueError("lifecycle output recommended_label basis is invalid")
    witnesses = value.get("evidence_witnesses")
    if not isinstance(witnesses, list) or any(
        not isinstance(item, str) or not item.strip() for item in witnesses
    ):
        raise ValueError("lifecycle output recommended_label witnesses are invalid")


def _validate_output(
    output: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    proposal_path: Path,
) -> None:
    if set(output) != {
        "schema_version",
        "batch_id",
        "proposed_reference_sha256",
        "decisions",
        "out_of_universe_review",
        "final_status",
    }:
        raise ValueError("lifecycle output fields are invalid")
    if output.get("schema_version") != OUTPUT_SCHEMA:
        raise ValueError("lifecycle output schema version is invalid")
    if output.get("batch_id") != plan.get("batch_id"):
        raise ValueError("lifecycle output batch identity is invalid")
    if output.get("proposed_reference_sha256") != _digest(proposal_path):
        raise ValueError("lifecycle output proposal identity is invalid")
    if output.get("out_of_universe_review") != "accept_empty":
        raise ValueError("lifecycle output coverage review is invalid")
    final_status = output.get("final_status")
    if final_status not in {"accepted", "unverified"}:
        raise ValueError("lifecycle output final status is invalid")
    proposal = _read_json(proposal_path)
    labels = proposal.get("labels")
    review_contract = plan.get("review_contract")
    candidate_count = (
        review_contract.get("candidate_count")
        if isinstance(review_contract, Mapping)
        else None
    )
    expected_ids = (
        [item.get("candidate_id") for item in labels]
        if isinstance(labels, list) and all(isinstance(item, Mapping) for item in labels)
        else None
    )
    decisions = output.get("decisions")
    if (
        not isinstance(expected_ids, list)
        or any(not isinstance(item, str) or not item for item in expected_ids)
        or not isinstance(candidate_count, int)
        or len(expected_ids) != candidate_count
        or len(expected_ids) != len(set(expected_ids))
        or not isinstance(decisions, list)
    ):
        raise ValueError("lifecycle output decisions are invalid")
    seen: set[str] = set()
    accepted = True
    for decision in decisions:
        if not isinstance(decision, Mapping) or set(decision) - {
            "candidate_id",
            "decision",
            "note",
            "recommended_label",
        }:
            raise ValueError("lifecycle output decision fields are invalid")
        candidate_id = _text(decision.get("candidate_id"), "candidate_id")
        if candidate_id in seen:
            raise ValueError("lifecycle output has duplicate decisions")
        seen.add(candidate_id)
        kind = decision.get("decision")
        if kind not in {"accept", "challenge"}:
            raise ValueError("lifecycle output decision kind is invalid")
        accepted = accepted and kind == "accept"
        _text(decision.get("note"), "note")
        if "recommended_label" in decision:
            _validate_recommended_label(decision["recommended_label"])
    if seen != set(expected_ids) or len(decisions) != len(expected_ids):
        raise ValueError("lifecycle output candidate universe is incomplete")
    if final_status == "accepted" and not accepted:
        raise ValueError("lifecycle output accepted state has challenges")


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def run(plan_path: Path, output_path: Path, run_record_path: Path) -> int:
    plan = _read_json(plan_path)
    inputs = _load_frozen_inputs(plan)
    runner = plan.get("runner")
    if (
        not isinstance(runner, Mapping)
        or runner.get("path") != str(Path(__file__).relative_to(ROOT))
        or runner.get("sha256") != _digest(Path(__file__))
    ):
        raise ValueError("canonical lifecycle runner identity is invalid")
    execution = plan.get("execution")
    if not isinstance(execution, Mapping):
        raise ValueError("execution plan has no execution contract")
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip()
    if not api_key or base_url != execution.get("base_url"):
        raise ValueError("canonical lifecycle provider configuration is unavailable")
    config = OpenAIShadowConfig(
        api_key=api_key,
        model=_text(execution.get("configured_model_id"), "configured_model_id"),
        base_url=base_url,
        timeout_seconds=float(execution.get("timeout_seconds")),
        max_output_tokens=int(execution.get("max_output_tokens")),
        api_profile=_text(execution.get("api_profile"), "api_profile"),
        thinking_mode=_text(execution.get("thinking_mode"), "thinking_mode"),
        reasoning_effort=_text(
            execution.get("reasoning_effort"), "reasoning_effort"
        ),
    )
    if config.execution_policy.identity != execution.get("policy_identity"):
        raise ValueError("canonical lifecycle policy identity is invalid")
    source = "\n\n".join(
        f"--- {name}: {path.relative_to(ROOT)} ---\n{path.read_text(encoding='utf-8')}"
        for name, path in sorted(inputs.items())
    )
    schema = inputs["output_schema"].read_text(encoding="utf-8")
    user_content = (
        "Return one JSON object matching this schema:\n"
        f"{schema}\n\n"
        "Frozen execution plan and authorized source evidence follow. Do not use "
        "other information:\n"
        f"{plan_path.read_text(encoding='utf-8')}\n\n{source}"
    )
    try:
        completion = complete_json_object(
            config,
            system_prompt=inputs["prompt"].read_text(encoding="utf-8"),
            user_content=user_content,
            require_provider_reported_model=True,
        )
    except ShadowProviderFailure as exc:
        print(json.dumps({"outcome": "provider_failure", "failure_category": exc.kind}))
        return 2
    proposal_path = inputs["proposed_reference"]
    _validate_output(completion.output, plan=plan, proposal_path=proposal_path)
    output_path.write_text(_canonical_json(completion.output), encoding="utf-8")
    run_record = {
        "schema_version": "rg_semantic_canonical_lifecycle_run.v1",
        "batch_id": plan["batch_id"],
        "plan_path": str(plan_path.relative_to(ROOT)),
        "plan_sha256": _digest(plan_path),
        "runner_path": str(Path(__file__).relative_to(ROOT)),
        "runner_sha256": _digest(Path(__file__)),
        "execution_date": plan["execution_date"],
        "provider": execution["provider"],
        "endpoint_class": execution["endpoint_class"],
        "configured_model_id": completion.configured_model_id,
        "provider_reported_model_id": completion.provider_reported_model_id,
        "policy_identity": config.execution_policy.identity,
        "input_tokens": completion.input_tokens,
        "output_tokens": completion.output_tokens,
        "structured_output_path": str(output_path),
        "structured_output_sha256": _digest(output_path),
        "structured_output_retained": True,
        "raw_provider_response_retained": False,
        "provider_error_text_retained": False,
        "final_status": completion.output["final_status"],
        "decision_count": len(completion.output["decisions"]),
        "authority_boundary": plan["authority_boundary"],
    }
    run_record_path.write_text(_canonical_json(run_record), encoding="utf-8")
    print(
        json.dumps(
            {
                "outcome": "success",
                "final_status": run_record["final_status"],
                "decision_count": run_record["decision_count"],
                "structured_output_sha256": run_record["structured_output_sha256"],
                "provider_reported_model_id": completion.provider_reported_model_id,
            },
            sort_keys=True,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-record", type=Path, required=True)
    args = parser.parse_args()
    try:
        return run(args.plan.resolve(), args.output.resolve(), args.run_record.resolve())
    except (OSError, TypeError, ValueError):
        print(json.dumps({"outcome": "local_contract_failure"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
