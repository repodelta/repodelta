#!/usr/bin/env python3
"""Replay the Issue #270 protocol decision matrix deterministically.

This is a normative decision replay, not a claim about live agent behavior.
The case labels are source-backed (observed) or explicitly declared synthetic
controls; the two protocol profiles are checked against the exact source text
at their pinned commits before scoring.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EVALUATION = Path(__file__).resolve().parent
CORPUS_PATH = EVALUATION / "corpus.json"
PROFILES_PATH = EVALUATION / "profiles.json"
RESULTS_DIR = EVALUATION / "results"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _git_file(commit: str, path: str) -> str:
    return subprocess.check_output(
        ["git", "show", f"{commit}:{path}"],
        cwd=ROOT,
        text=True,
    )


def _validate_profile_sources(profile: dict[str, Any]) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    for evidence in profile["evidence"]:
        source = _git_file(profile["commit"], evidence["path"])
        found = evidence["contains"] in source
        checks.append(
            {
                "path": evidence["path"],
                "contains": evidence["contains"],
                "status": "pass" if found else "fail",
            }
        )
        if not found:
            raise AssertionError(
                f"profile source marker missing: {profile['label']} "
                f"{evidence['path']}: {evidence['contains']!r}"
            )
    return checks


def _predict_replan(profile: dict[str, Any], case: dict[str, Any]) -> bool:
    trigger = case["trigger"]
    return (
        trigger in profile["replan_triggers"]
        and trigger not in profile["replan_exemptions"]
    )


def _case_result(profile: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    capabilities = profile["capabilities"]
    required = set(case["required_dimensions"])
    missing = sorted(
        dimension
        for dimension in required
        if not capabilities.get(dimension, False)
    )
    predicted_replan = _predict_replan(profile, case)
    expected_replan = case["expected_replan"]
    scope_ok = case["expected_scope"] in profile["recognized_scopes"]
    unsafe_ok = (
        not case["expected_unsafe_rejection"]
        or capabilities["fail_closed"]
    )
    # Noise is measured only on controls that introduce no changed semantic
    # result. A non-conditional protocol spends an obligation on that case.
    noise = int(
        not case.get("semantic_change", True)
        and not capabilities.get("conditional_obligations", False)
    )
    return {
        "case_id": case["id"],
        "provenance": case["provenance"],
        "held_out": case.get("held_out", False),
        "required_dimensions": sorted(required),
        "recognized_dimensions": sorted(required - set(missing)),
        "missing_dimensions": missing,
        "scope_expected": case["expected_scope"],
        "scope_recognized": scope_ok,
        "replan_expected": expected_replan,
        "replan_predicted": predicted_replan,
        "replan_correct": predicted_replan == expected_replan,
        "unsafe_rejection_expected": case["expected_unsafe_rejection"],
        "unsafe_rejection_preserved": unsafe_ok,
        "noise_units": noise,
    }


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    required = sum(len(item["required_dimensions"]) for item in results)
    recognized = sum(len(item["recognized_dimensions"]) for item in results)
    scope_cases = [item for item in results if item["scope_expected"] != "none"]
    replan_positive = [item for item in results if item["replan_expected"]]
    replan_negative = [item for item in results if not item["replan_expected"]]
    true_positive = sum(
        item["replan_predicted"] for item in replan_positive
    )
    false_positive = sum(
        item["replan_predicted"] for item in replan_negative
    )
    unsafe_cases = [
        item for item in results if item["unsafe_rejection_expected"]
    ]
    held_out = [item for item in results if item["held_out"]]
    return {
        "recognition": {
            "required_obligations": required,
            "recognized_obligations": recognized,
            "missing_obligations": required - recognized,
            "accuracy": _rate(recognized, required),
        },
        "scope_precision": {
            "cases": len(scope_cases),
            "correct": sum(item["scope_recognized"] for item in scope_cases),
            "accuracy": _rate(
                sum(item["scope_recognized"] for item in scope_cases),
                len(scope_cases),
            ),
        },
        "replan": {
            "true_positive": true_positive,
            "false_positive": false_positive,
            "positive_cases": len(replan_positive),
            "negative_cases": len(replan_negative),
            "recall": _rate(true_positive, len(replan_positive)),
            "precision": _rate(
                true_positive,
                true_positive + false_positive,
            ),
            "accuracy": _rate(
                sum(item["replan_correct"] for item in results),
                len(results),
            ),
        },
        "unsafe_rejection": {
            "cases": len(unsafe_cases),
            "preserved": sum(
                item["unsafe_rejection_preserved"] for item in unsafe_cases
            ),
            "hard_gate": all(
                item["unsafe_rejection_preserved"] for item in unsafe_cases
            ),
        },
        "planning_noise": {
            "units": sum(item["noise_units"] for item in results),
            "held_out_units": sum(item["noise_units"] for item in held_out),
        },
    }


def _build_output(
    corpus: dict[str, Any], profiles_doc: dict[str, Any]
) -> dict[str, Any]:
    cases = corpus["cases"]
    profile_results: dict[str, Any] = {}
    for name, profile in profiles_doc["profiles"].items():
        source_checks = _validate_profile_sources(profile)
        per_case = [_case_result(profile, case) for case in cases]
        profile_results[name] = {
            "label": profile["label"],
            "commit": profile["commit"],
            "source_checks": source_checks,
            "cases": per_case,
            "metrics": _metrics(per_case),
        }

    baseline = profile_results["pre_v1_2"]["metrics"]
    candidate = profile_results["v1_2"]["metrics"]
    acceptance = {
        "recognition_improves": candidate["recognition"]["accuracy"]
        > baseline["recognition"]["accuracy"],
        "scope_precision_improves": candidate["scope_precision"]["accuracy"]
        > baseline["scope_precision"]["accuracy"],
        "replan_recall_improves": candidate["replan"]["recall"]
        > baseline["replan"]["recall"],
        "replan_precision_not_lower": (
            candidate["replan"]["precision"] or 0
        ) >= (baseline["replan"]["precision"] or 0),
        "unsafe_rejection_not_lower": candidate["unsafe_rejection"]["hard_gate"]
        >= baseline["unsafe_rejection"]["hard_gate"],
        "noise_not_higher": candidate["planning_noise"]["units"]
        <= baseline["planning_noise"]["units"],
    }
    acceptance["replay_accepts_v1_2"] = all(acceptance.values())

    return {
        "schema_version": "repodelta_protocol_v1_2_replay.v1",
        "corpus_digest": _digest(corpus),
        "profiles_digest": _digest(profiles_doc),
        "case_count": len(cases),
        "observed_case_count": sum(
            item["provenance"] == "observed" for item in cases
        ),
        "held_out_case_count": sum(item.get("held_out", False) for item in cases),
        "profiles": profile_results,
        "comparison": {
            "pre_v1_2": baseline,
            "v1_2": candidate,
            "acceptance": acceptance,
        },
        "limitations": [
            "This is a deterministic protocol-decision replay, not a live coding-agent trial.",
            "Historical cases are source-backed; synthetic controls are declared and held out from the historical examples.",
            "The profile capabilities are a checked interpretation of pinned protocol text, not runtime telemetry.",
            "A later live-agent study is required to estimate actual recognition or execution behavior.",
        ],
    }


def main() -> int:
    corpus = _load(CORPUS_PATH)
    profiles_doc = _load(PROFILES_PATH)
    output = _build_output(corpus, profiles_doc)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "summary.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(output["comparison"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
