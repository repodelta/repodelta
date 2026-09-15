"""Materialize the bounded PR #208 R/G retrieval ablation for Issue #322."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from repodelta.evaluation.rg_candidate_universe import (
    load_rg_candidate_universe,
    load_rg_retrieval_observation,
    load_rg_semantic_reference,
    write_rg_candidate_artifact,
)
from repodelta.evaluation.rg_retrieval_ablation import (
    build_ablation_input,
    run_retrieval_ablation,
)


REVIEWED_HEAD = "e6d94bd9c414a09c1027aac0bc658ba025ddf3ad"
PRESENT_REPOSITORY_HEAD = "4f5b310c2ec173386e46edc70f41daec09205ecc"
PR208_UNIVERSE_DIGEST = "6ee61bf0f516385acfce02172b1b2466a0ffb3a7cec58165e4fcc4b1c5a86502"
KNOWN_MISS_IDS = (
    "C:G2:E:structural_change:5d2be31cc60dea3d2f3b",
    "C:G2:E:structural_change:7c4162e02e623fea377f",
    "C:G2:E:structural_change:d0cf036a1010c1207bc5",
    "C:R2:E:structural_change:9ff44326982c1acafe85",
    "C:R3:E:structural_change:5d2be31cc60dea3d2f3b",
    "C:R3:E:structural_change:d0cf036a1010c1207bc5",
    "C:R5:E:structural_change:7c4162e02e623fea377f",
)


def build_pr208_rg_retrieval_ablation(
    campaign: Path, repository: Path
) -> dict[str, object]:
    """Build input, deterministic retrieval observation, and staleness controls."""

    universe_path = campaign / "rg-candidate-universes/pr-208.json"
    retrieval_path = campaign / "rg-retrieval-observations/pr-208.json"
    declaration_path = (
        campaign
        / "rg-semantic-proposals/pr-208.batch-001.ai-adjudicated.proposed.json"
    )
    history_path = campaign / "rg-retrieval-ablation-history/pr-208.json"
    universe = load_rg_candidate_universe(universe_path)
    retrieval = load_rg_retrieval_observation(retrieval_path)
    declaration = load_rg_semantic_reference(declaration_path)
    if universe.digest != PR208_UNIVERSE_DIGEST:
        raise ValueError("PR #208 retrieval ablation requires the frozen universe")
    known_misses = _historical_known_misses(declaration, retrieval)
    if known_misses != KNOWN_MISS_IDS:
        raise ValueError("PR #208 retrieval ablation known-miss selection drifted")
    history_manifest = _read_json(history_path)
    _require_commit(repository, REVIEWED_HEAD)
    _require_commit(repository, PRESENT_REPOSITORY_HEAD)
    history_resolution = _resolve_history(repository, history_manifest)
    ablation_input = build_ablation_input(
        universe,
        retrieval,
        known_miss_candidate_ids=known_misses,
        reviewed_head=REVIEWED_HEAD,
        repository_head=PRESENT_REPOSITORY_HEAD,
        history_manifest=history_manifest,
    )
    result = run_retrieval_ablation(
        ablation_input,
        read_revision_file=lambda revision, path: _git_show(repository, revision, path),
        history_resolution=history_resolution,
    )
    result["input_provenance"] = {
        "candidate_universe": _file_identity(campaign, universe_path),
        "observed_retrieval": _file_identity(campaign, retrieval_path),
        "historical_calibration_selection": _file_identity(campaign, declaration_path),
        "historical_vocabulary_and_controls": _file_identity(campaign, history_path),
        "known_miss_selection_boundary": (
            "The historical calibration selects seven diagnostic candidate IDs only. "
            "The retrieval input excludes semantic relation, proofability, proof "
            "basis, and label content."
        ),
    }
    return result


def _historical_known_misses(declaration: Any, retrieval: Any) -> tuple[str, ...]:
    direct_relations = {
        "implements",
        "constrains",
        "removes",
        "directly_verifies",
    }
    retrieval_rows = {row.candidate_id: row for row in retrieval.rows}
    return tuple(
        sorted(
            label.candidate_id
            for label in declaration.labels
            if label.semantic_relation in direct_relations
            and retrieval_rows[label.candidate_id].retrieval_state == "not_retrieved"
        )
    )


def _resolve_history(
    repository: Path, history_manifest: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Resolve declared historical vocabulary/controls at the pinned present head."""

    result: dict[str, dict[str, Any]] = {}
    for vocabulary in history_manifest["vocabulary"]:
        term = vocabulary["term"]
        active_paths = _git_grep_paths(repository, PRESENT_REPOSITORY_HEAD, term)
        result[vocabulary["record_id"]] = {
            "term": term,
            "source_url": vocabulary["source_url"],
            "status": "active_current_vocabulary" if active_paths else "unresolved_or_stale",
            "current_head_paths": active_paths,
            "authority_boundary": (
                "Vocabulary resolution permits a search term only; it does not emit "
                "a current owner, responsibility, semantic relation, or admission."
            ),
        }
    for control in history_manifest["negative_controls"]:
        result[control["control_id"]] = _resolve_control(repository, control)
    return result


def _resolve_control(repository: Path, control: dict[str, Any]) -> dict[str, Any]:
    control_id = control["control_id"]
    if control_id == "NC:renamed-path":
        historical_exists = _path_exists(
            repository, PRESENT_REPOSITORY_HEAD, control["historical_path"]
        )
        successor_exists = _path_exists(
            repository, PRESENT_REPOSITORY_HEAD, control["successor_path"]
        )
        rename_recorded = _rename_recorded(
            repository,
            control["resolution_commit"],
            control["historical_path"],
            control["successor_path"],
        )
        return {
            "status": "renamed_or_replaced"
            if not historical_exists and successor_exists and rename_recorded
            else "unresolved_or_stale",
            "historical_path_exists_at_current_head": historical_exists,
            "successor_path_exists_at_current_head": successor_exists,
            "rename_recorded": rename_recorded,
            "current_fact_emitted": False,
            "boundary": control["must_not_become_current_fact"],
        }
    if control_id == "NC:renamed-product-term":
        old_paths = _git_grep_paths(
            repository, PRESENT_REPOSITORY_HEAD, control["historical_term"], paths=("src/repodelta",)
        )
        successor_paths = _git_grep_paths(
            repository, PRESENT_REPOSITORY_HEAD, control["successor_term"], paths=("src/repodelta",)
        )
        return {
            "status": "renamed_or_replaced" if not old_paths and successor_paths else "unresolved_or_stale",
            "historical_term_paths_at_current_head": old_paths,
            "successor_term_paths_at_current_head": successor_paths,
            "current_fact_emitted": False,
            "boundary": control["must_not_become_current_fact"],
        }
    if control_id in {"NC:former-seed-owner", "NC:rejected-primary-gate"}:
        old = _git_show(repository, control["source_revision"], control["source_path"])
        current = _git_show(repository, PRESENT_REPOSITORY_HEAD, control["current_path"])
        old_seed = _function_source(old, "_canonical_backbone_seed_node_ids")
        current_seed = _function_source(current, "_canonical_backbone_seed_node_ids")
        predicate = (
            "relations: dict[str, ProjectionRelation]"
            if control_id == "NC:former-seed-owner"
            else 'evidence_role == "primary"'
        )
        historical_predicate = predicate in old_seed
        current_predicate = predicate in current_seed
        return {
            "status": "superseded" if historical_predicate and not current_predicate else "unresolved_or_stale",
            "historical_predicate_observed": historical_predicate,
            "predicate_observed_at_current_head": current_predicate,
            "current_fact_emitted": False,
            "boundary": control["must_not_become_current_fact"],
        }
    raise ValueError(f"unsupported retrieval-ablation negative control: {control_id}")


def _git_show(repository: Path, revision: str, path: str) -> str:
    return _git(repository, "show", f"{revision}:{path}").stdout


def _path_exists(repository: Path, revision: str, path: str) -> bool:
    return _git(repository, "cat-file", "-e", f"{revision}:{path}", check=False).returncode == 0


def _git_grep_paths(
    repository: Path,
    revision: str,
    term: str,
    *,
    paths: tuple[str, ...] = ("src", "tests"),
) -> list[str]:
    completed = _git(
        repository,
        "grep",
        "-i",
        "-l",
        "--fixed-strings",
        term,
        revision,
        "--",
        *paths,
        check=False,
    )
    if completed.returncode not in {0, 1}:
        raise ValueError(f"git grep failed for history term {term!r}")
    return sorted(
        line.split(":", 1)[1] if ":" in line else line
        for line in completed.stdout.splitlines()
        if line
    )


def _rename_recorded(repository: Path, commit: str, old_path: str, new_path: str) -> bool:
    completed = _git(
        repository,
        "diff-tree",
        "--find-renames",
        "--no-commit-id",
        "--name-status",
        "-r",
        commit,
    )
    return any(
        line.endswith(f"\t{old_path}\t{new_path}") and line.startswith("R")
        for line in completed.stdout.splitlines()
    )


def _function_source(source: str, name: str) -> str:
    marker = f"def {name}("
    start = source.find(marker)
    if start < 0:
        raise ValueError(f"missing expected function {name}")
    end = source.find("\ndef ", start + len(marker))
    return source[start:] if end < 0 else source[start:end]


def _git(repository: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", *args),
        cwd=repository,
        check=check,
        text=True,
        capture_output=True,
    )


def _require_commit(repository: Path, revision: str) -> None:
    if _git(repository, "cat-file", "-e", f"{revision}^{{commit}}", check=False).returncode:
        raise ValueError(f"retrieval ablation repository lacks pinned commit {revision}")


def _file_identity(campaign: Path, path: Path) -> dict[str, str]:
    return {
        "path": str(path.relative_to(campaign)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def render_findings(result: dict[str, Any]) -> str:
    aggregate = {item["mechanism"]: item for item in result["aggregate"]}
    controls = {
        control_id: value
        for control_id, value in result["history_resolution"].items()
        if control_id.startswith("NC:")
    }
    rows = [
        "# PR #208 R/G retrieval ablation",
        "",
        "This Issue #322 experiment is evaluation-only. The seven diagnostic IDs "
        "were selected by historical calibration, but no semantic label, proof "
        "value, or admission decision enters query generation.",
        "",
        "## Bounded result",
        "",
        "| Mechanism | Recovered | Incremental | Additional candidate memberships | Unresolved |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    labels = {
        "baseline_current_association": "Baseline current association",
        "Q1_identifier_variants": "Explicit identifier variants",
        "Q0_authored_lexical": "Authored terms → reviewed-head lexical spans",
        "Q2_history_vocabulary_then_reviewed_head_lexical": "Historical vocabulary → reviewed-head lexical spans",
    }
    for mechanism, label in labels.items():
        item = aggregate[mechanism]
        rows.append(
            f"| {label} | {item['known_misses_recovered']} | "
            f"{item['incremental_recoveries']} | {item['additional_candidate_count']} | "
            f"{item['unresolved_cases']} |"
        )
    q0 = aggregate["Q0_authored_lexical"]
    q2 = aggregate["Q2_history_vocabulary_then_reviewed_head_lexical"]
    rows.extend(
        [
            "",
            "All seven diagnostics are recovered by normalized authored R/G terms "
            "searched only inside source spans at the frozen PR #208 head. This is "
            "retrieval evidence only: its "
            f"{q0['additional_candidate_count']} additional memberships remain "
            "semantically unassessed.",
            "",
            "Historical Issue/PR vocabulary also finds reviewed-head candidates but "
            f"adds no incremental recovery in this set ({q2['incremental_recoveries']}). "
            "It is therefore not part of the minimum retrieval substrate. There are "
            "no residual misses, so Q3 current-vocabulary expansion, Q4 structural "
            "expansion, and Q5 semantic/LLM/agentic search were not run.",
            "",
            "## History/current boundary",
            "",
            "Present repository state classifies historical vocabulary and controls; "
            "it never overwrites the source fact at the reviewed PR head.",
            "",
            "| Control | Resolution | Current fact emitted? |",
            "| --- | --- | --- |",
        ]
    )
    rows.extend(
        f"| `{control_id}` | `{value['status']}` | `{value['current_fact_emitted']}` |"
        for control_id, value in sorted(controls.items())
    )
    rows.extend(
        [
            "",
            "The renamed `src/prismcode/...` path, old `PrismCode` name, former "
            "relation/evidence-role seed owner, and primary-only gate remain "
            "historical or superseded. None is emitted as a current responsibility, "
            "membership rule, semantic relation, or admission fact.",
            "",
            "## Next bounded hypothesis",
            "",
            "A later, separately scoped production experiment can add "
            "provenance-preserving reviewed-head lexical R/G candidates as "
            "`suggested` retrieval evidence, without changing semantic relation, "
            "proof, or admission authority. This experiment does not itself justify "
            "a production change or LLM/embedding retrieval.",
            "",
        ]
    )
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize the bounded PR #208 R/G retrieval ablation"
    )
    parser.add_argument(
        "--campaign",
        type=Path,
        default=Path(__file__).parent,
        help="Frozen v1.1 campaign directory",
    )
    parser.add_argument(
        "--repository",
        type=Path,
        default=Path(__file__).resolve().parents[3],
        help="Repository containing the pinned historical revisions",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--input-output", type=Path)
    parser.add_argument("--findings-output", type=Path)
    args = parser.parse_args()
    result = build_pr208_rg_retrieval_ablation(args.campaign, args.repository)
    output = args.output or args.campaign / "results/rg-retrieval-ablation/pr-208.json"
    input_output = (
        args.input_output
        or args.campaign / "results/rg-retrieval-ablation/pr-208.input.json"
    )
    findings_output = (
        args.findings_output
        or args.campaign / "results/rg-retrieval-ablation/findings.md"
    )
    write_rg_candidate_artifact(result["input"], input_output)
    write_rg_candidate_artifact(result, output)
    findings_output.parent.mkdir(parents=True, exist_ok=True)
    findings_output.write_text(render_findings(result), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
