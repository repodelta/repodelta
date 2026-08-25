from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVALUATION = ROOT / "evaluations" / "protocol-v1-2"
SPEC = importlib.util.spec_from_file_location(
    "repodelta_protocol_v1_2_replay",
    EVALUATION / "evaluate.py",
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_protocol_v1_2_replay_accepts_candidate_without_unsafe_regression() -> None:
    corpus = MODULE._load(EVALUATION / "corpus.json")
    profiles_doc = MODULE._load(EVALUATION / "profiles.json")
    profiles = profiles_doc["profiles"]

    profile_metrics = {}
    for name, profile in profiles.items():
        MODULE._validate_profile_sources(profile)
        rows = [MODULE._case_result(profile, case) for case in corpus["cases"]]
        profile_metrics[name] = MODULE._metrics(rows)

    baseline = profile_metrics["pre_v1_2"]
    candidate = profile_metrics["v1_2"]

    assert candidate["recognition"]["accuracy"] > baseline["recognition"]["accuracy"]
    assert candidate["scope_precision"]["accuracy"] > baseline["scope_precision"]["accuracy"]
    assert candidate["replan"]["recall"] > baseline["replan"]["recall"]
    assert candidate["replan"]["precision"] >= (baseline["replan"]["precision"] or 0)
    assert candidate["unsafe_rejection"]["hard_gate"]
    assert candidate["unsafe_rejection"]["hard_gate"] >= baseline["unsafe_rejection"]["hard_gate"]
    assert candidate["planning_noise"]["units"] <= baseline["planning_noise"]["units"]


def test_committed_summary_is_machine_derived_from_pinned_inputs() -> None:
    corpus = MODULE._load(EVALUATION / "corpus.json")
    profiles_doc = MODULE._load(EVALUATION / "profiles.json")
    expected = MODULE._build_output(corpus, profiles_doc)
    committed = json.loads(
        (EVALUATION / "results" / "summary.json").read_text(encoding="utf-8")
    )

    assert committed == expected
