"""Run a replacement source-isolated R/G lifecycle-review subject for PR 208."""

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
PLAN_SCHEMA = "rg_semantic_canonical_subject_lifecycle_plan.v1"
OUTPUT_SCHEMA = "rg_semantic_canonical_subject_lifecycle_output.v1"
ATTEMPT_SCHEMA = "rg_semantic_canonical_subject_lifecycle_replacement_attempt.v1"
_RELATIONS = frozenset(
    {
        "implements",
        "constrains",
        "removes",
        "directly_verifies",
        "contextual_support",
        "unrelated",
        "insufficient",
    }
)
_PROOFABILITY = frozenset(
    {"direct_capable", "suggested_only", "not_applicable", "insufficient"}
)
_PROOF_BASIS = frozenset(
    {
        "explicit_authoring",
        "typed_predicate",
        "bounded_evidence",
        "deterministic_mapping",
        "heuristic",
        "model_suggestion",
        "none",
    }
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _bundle_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
    ).hexdigest()


def _read_json(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"canonical subject lifecycle {label} is invalid") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"canonical subject lifecycle {label} must be an object")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"canonical subject lifecycle {field} is invalid")
    return value


def _root_relative_path(value: object) -> Path:
    path = (ROOT / _text(value, "artifact path")).resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError("canonical subject lifecycle artifact escapes repository") from exc
    return path


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_canonical_json(value), encoding="utf-8")


def _load(
    plan_path: Path,
) -> tuple[Mapping[str, Any], Mapping[str, Path], Mapping[str, Any]]:
    plan = _read_json(plan_path, "plan")
    if plan.get("schema_version") != PLAN_SCHEMA:
        raise ValueError("unsupported canonical subject lifecycle plan")
    runner = plan.get("runner")
    if (
        not isinstance(runner, Mapping)
        or runner.get("path") != str(Path(__file__).relative_to(ROOT))
        or runner.get("sha256") != _digest(Path(__file__))
    ):
        raise ValueError("canonical subject lifecycle runner identity is invalid")
    records = plan.get("authorized_input_artifacts")
    if not isinstance(records, Mapping):
        raise ValueError("canonical subject lifecycle artifacts are invalid")
    artifacts: dict[str, Path] = {}
    for name, record in records.items():
        if not isinstance(name, str) or not isinstance(record, Mapping):
            raise ValueError("canonical subject lifecycle artifact record is invalid")
        path = _root_relative_path(record.get("path"))
        if record.get("sha256") != _digest(path):
            raise ValueError("canonical subject lifecycle artifact digest mismatch")
        artifacts[name] = path
    if set(artifacts) != {"protocol", "rubric", "labeler_input", "proposal", "prompt", "output_schema"}:
        raise ValueError("canonical subject lifecycle artifact set is invalid")
    execution = plan.get("execution")
    if not isinstance(execution, Mapping):
        raise ValueError("canonical subject lifecycle execution contract is invalid")
    subjects = plan.get("subject_ids")
    if (
        not isinstance(subjects, list)
        or not subjects
        or any(not isinstance(item, str) or not item for item in subjects)
        or len(subjects) != len(set(subjects))
    ):
        raise ValueError("canonical subject lifecycle subject partition is invalid")
    return plan, artifacts, execution


def _config(execution: Mapping[str, Any]) -> OpenAIShadowConfig:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip()
    if not api_key or base_url != execution.get("base_url"):
        raise ValueError("canonical subject lifecycle provider configuration is unavailable")
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
        raise ValueError("canonical subject lifecycle policy identity is invalid")
    return config


def _objects(value: object, field: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"canonical subject lifecycle {field} is invalid")
    return list(value)


def _subject_bundle(
    artifacts: Mapping[str, Path], subject_id: str
) -> tuple[Mapping[str, Any], list[str]]:
    labeler_input = _read_json(artifacts["labeler_input"], "labeler input")
    universe = labeler_input.get("candidate_universe")
    if not isinstance(universe, Mapping):
        raise ValueError("canonical subject lifecycle candidate universe is invalid")
    subjects = _objects(universe.get("subjects"), "subjects")
    subject_matches = [item for item in subjects if item.get("subject_id") == subject_id]
    if len(subject_matches) != 1:
        raise ValueError("canonical subject lifecycle subject is unavailable")
    candidates = [
        item
        for item in _objects(universe.get("candidates"), "candidates")
        if item.get("subject_id") == subject_id
    ]
    candidate_ids = sorted(_text(item.get("candidate_id"), "candidate_id") for item in candidates)
    if not candidate_ids or len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("canonical subject lifecycle candidates are invalid")
    anchors_by_id = {
        _text(item.get("evidence_id"), "evidence_id"): item
        for item in _objects(universe.get("anchors"), "anchors")
    }
    evidence_ids = {_text(item.get("evidence_id"), "evidence_id") for item in candidates}
    if evidence_ids - set(anchors_by_id):
        raise ValueError("canonical subject lifecycle anchor is unavailable")
    proposal = _read_json(artifacts["proposal"], "proposal")
    labels_by_id = {
        _text(item.get("candidate_id"), "candidate_id"): item
        for item in _objects(proposal.get("labels"), "proposal labels")
    }
    if set(candidate_ids) - set(labels_by_id):
        raise ValueError("canonical subject lifecycle proposal is incomplete")
    bundle: Mapping[str, Any] = {
        "authored_contract": labeler_input.get("authored_contract"),
        "exact_diff": labeler_input.get("exact_diff"),
        "protocol": artifacts["protocol"].read_text(encoding="utf-8"),
        "rubric": artifacts["rubric"].read_text(encoding="utf-8"),
        "subject": subject_matches[0],
        "anchors": [anchors_by_id[item] for item in sorted(evidence_ids)],
        "candidates": sorted(candidates, key=lambda item: str(item.get("candidate_id"))),
        "proposed_labels": [labels_by_id[item] for item in candidate_ids],
    }
    return bundle, candidate_ids


def _validate_recommended_label(value: object) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "semantic_relation",
        "proofability",
        "proof_basis",
        "evidence_witnesses",
    }:
        raise ValueError("canonical subject lifecycle recommendation is invalid")
    if value.get("semantic_relation") not in _RELATIONS:
        raise ValueError("canonical subject lifecycle recommendation relation is invalid")
    if value.get("proofability") not in _PROOFABILITY:
        raise ValueError("canonical subject lifecycle recommendation proofability is invalid")
    if value.get("proof_basis") not in _PROOF_BASIS:
        raise ValueError("canonical subject lifecycle recommendation basis is invalid")
    witnesses = value.get("evidence_witnesses")
    if not isinstance(witnesses, list) or any(
        not isinstance(item, str) or not item.strip() for item in witnesses
    ):
        raise ValueError("canonical subject lifecycle recommendation witnesses are invalid")


def _validate_output(
    output: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    subject_id: str,
    bundle: Mapping[str, Any],
    candidate_ids: list[str],
) -> None:
    if set(output) != {
        "schema_version",
        "batch_id",
        "subject_id",
        "subject_bundle_sha256",
        "decisions",
        "out_of_universe_review",
        "final_status",
    }:
        raise ValueError("canonical subject lifecycle output fields are invalid")
    if output.get("schema_version") != OUTPUT_SCHEMA:
        raise ValueError("canonical subject lifecycle output schema is invalid")
    if output.get("batch_id") != plan.get("batch_id") or output.get("subject_id") != subject_id:
        raise ValueError("canonical subject lifecycle output identity is invalid")
    if output.get("subject_bundle_sha256") != _bundle_digest(bundle):
        raise ValueError("canonical subject lifecycle output bundle identity is invalid")
    if output.get("out_of_universe_review") != "accept_empty":
        raise ValueError("canonical subject lifecycle coverage review is invalid")
    decisions = _objects(output.get("decisions"), "decisions")
    seen: set[str] = set()
    accepted = True
    for decision in decisions:
        if set(decision) - {"candidate_id", "decision", "note", "recommended_label"}:
            raise ValueError("canonical subject lifecycle decision fields are invalid")
        candidate_id = _text(decision.get("candidate_id"), "candidate_id")
        note = _text(decision.get("note"), "note")
        if len(note) > 240 or candidate_id in seen:
            raise ValueError("canonical subject lifecycle decision is invalid")
        seen.add(candidate_id)
        kind = decision.get("decision")
        if kind not in {"accept", "challenge"}:
            raise ValueError("canonical subject lifecycle decision kind is invalid")
        accepted = accepted and kind == "accept"
        if "recommended_label" in decision:
            _validate_recommended_label(decision["recommended_label"])
    if seen != set(candidate_ids) or len(decisions) != len(candidate_ids):
        raise ValueError("canonical subject lifecycle decision coverage is incomplete")
    final_status = output.get("final_status")
    if final_status not in {"accepted", "unverified"}:
        raise ValueError("canonical subject lifecycle final status is invalid")
    if final_status == "accepted" and not accepted:
        raise ValueError("canonical subject lifecycle accepted output has challenges")


def _attempt_base(
    plan_path: Path,
    plan: Mapping[str, Any],
    execution: Mapping[str, Any],
    subject_id: str,
    bundle: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": ATTEMPT_SCHEMA,
        "attempt_id": f"{_text(plan.get('batch_id'), 'batch_id')}-{subject_id}-001",
        "phase": "source_evidence_subject_review",
        "subject_id": subject_id,
        "subject_bundle_sha256": _bundle_digest(bundle),
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
        "repository_and_candidate_data_authorized_for_dispatch": True,
    }


def run(
    plan_path: Path,
    subject_id: str,
    output_path: Path,
    attempt_path: Path,
) -> int:
    plan, artifacts, execution = _load(plan_path)
    if subject_id not in plan["subject_ids"]:
        raise ValueError("subject is outside the frozen lifecycle partition")
    config = _config(execution)
    bundle, candidate_ids = _subject_bundle(artifacts, subject_id)
    attempt = _attempt_base(plan_path, plan, execution, subject_id, bundle)
    _write(
        attempt_path,
        {**attempt, "state": "started", "provider_delivery": "unobserved"},
    )
    try:
        schema = artifacts["output_schema"].read_text(encoding="utf-8")
        identity_envelope = {
            "batch_id": plan["batch_id"],
            "subject_id": subject_id,
            "subject_bundle_sha256": _bundle_digest(bundle),
            "candidate_ids": candidate_ids,
            "out_of_universe_review": "accept_empty",
        }
        completion = complete_json_object(
            config,
            system_prompt=artifacts["prompt"].read_text(encoding="utf-8"),
            user_content=(
                "Return one JSON object matching this schema:\n"
                f"{schema}\n\n"
                "Copy this mandatory output identity envelope exactly into the "
                "corresponding output fields; it is not a semantic judgment:\n"
                f"{_canonical_json(identity_envelope)}\n"
                "Frozen source-evidence subject bundle follows. Do not use other information:\n"
                f"{_canonical_json(bundle)}"
            ),
            require_provider_reported_model=True,
        )
        _validate_output(
            completion.output,
            plan=plan,
            subject_id=subject_id,
            bundle=bundle,
            candidate_ids=candidate_ids,
        )
        _write(output_path, completion.output)
        _write(
            attempt_path,
            {
                **attempt,
                "state": "succeeded",
                "provider_delivery": "completed",
                "provider_reported_model_id": completion.provider_reported_model_id,
                "policy_identity": config.execution_policy.identity,
                "input_tokens": completion.input_tokens,
                "output_tokens": completion.output_tokens,
                "structured_output_path": str(output_path),
                "structured_output_sha256": _digest(output_path),
                "structured_output_retained": True,
                "final_status": completion.output["final_status"],
                "decision_count": len(completion.output["decisions"]),
            },
        )
        print(
            json.dumps(
                {
                    "outcome": "success",
                    "subject_id": subject_id,
                    "final_status": completion.output["final_status"],
                    "decision_count": len(completion.output["decisions"]),
                },
                sort_keys=True,
            )
        )
        return 0
    except ShadowProviderFailure as exc:
        _write(
            attempt_path,
            {
                **attempt,
                "state": "provider_failure",
                "provider_delivery": "provider_failure",
                "failure_category": exc.kind,
                "structured_output_retained": False,
            },
        )
        print(json.dumps({"outcome": "provider_failure", "failure_category": exc.kind}))
        return 2
    except Exception:
        _write(
            attempt_path,
            {
                **attempt,
                "state": "local_contract_failure",
                "provider_delivery": "unobserved",
                "structured_output_retained": False,
            },
        )
        print(json.dumps({"outcome": "local_contract_failure"}))
        return 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--subject-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--attempt", type=Path, required=True)
    args = parser.parse_args()
    try:
        return run(
            args.plan.resolve(),
            args.subject_id,
            args.output.resolve(),
            args.attempt.resolve(),
        )
    except Exception:
        print(json.dumps({"outcome": "local_contract_failure"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
