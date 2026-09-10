"""Materialize deterministic, retrieval-isolated PR 208 lifecycle-review shards."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
CAMPAIGN = ROOT / "evaluations/structural-correctness/campaign-v1-1"
RUNS = CAMPAIGN / "rg-semantic-labeling-runs"
INPUT = RUNS / "pr-208.batch-001.labeler-input.json"
PROPOSAL = CAMPAIGN / "rg-semantic-proposals/pr-208.batch-001.ai-adjudicated.proposed.json"
PLAN = RUNS / "pr-208.batch-001.ai-lifecycle-shard-plan.json"
PROMPT = RUNS / "pr-208.batch-001.ai-lifecycle-shard-verifier-prompt.md"
SCHEMA = RUNS / "pr-208.batch-001.ai-lifecycle-shard-verifier-output.schema.json"

SHARDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("guardrails", ("G1", "G2", "G3", "G4")),
    ("requirements-core", ("R1", "R2", "R3")),
    ("requirements-boundaries", ("R4", "R5")),
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    source = json.loads(INPUT.read_text(encoding="utf-8"))
    proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    universe = source["candidate_universe"]
    candidates = universe["candidates"]
    anchors_by_id = {item["evidence_id"]: item for item in universe["anchors"]}
    labels_by_id = {item["candidate_id"]: item for item in proposal["labels"]}
    candidate_ids = {item["candidate_id"] for item in candidates}
    if candidate_ids != set(labels_by_id):
        raise SystemExit("candidate_and_proposal_universe_mismatch")

    shard_specs: list[dict[str, Any]] = []
    assigned: set[str] = set()
    for ordinal, (name, subject_ids) in enumerate(SHARDS, start=1):
        shard_candidates = [
            item for item in candidates if item["subject_id"] in subject_ids
        ]
        ids = tuple(sorted(item["candidate_id"] for item in shard_candidates))
        if not ids or assigned.intersection(ids):
            raise SystemExit("shard_partition_invalid")
        assigned.update(ids)
        shard_specs.append(
            {
                "shard_id": f"pr-208-batch-001-{ordinal:03d}-{name}",
                "subject_ids": list(subject_ids),
                "candidate_ids": list(ids),
            }
        )
    if assigned != candidate_ids:
        raise SystemExit("shard_partition_incomplete")

    plan = {
        "schema_version": "rg_semantic_ai_lifecycle_shard_plan.v1",
        "batch_id": "pr-208-batch-001",
        "status": "frozen_before_shard_review",
        "reason": (
            "The one-shot 54-row lifecycle verifier failed twice with "
            "provider_response_parse_failure and no retained structured output. "
            "This replacement design preserves the same universe and labels while "
            "bounding each source-evidence response."
        ),
        "source_inputs": {
            "labeler_input": {
                "path": str(INPUT.relative_to(ROOT)),
                "sha256": digest(INPUT),
            },
            "proposed_reference": {
                "path": str(PROPOSAL.relative_to(ROOT)),
                "sha256": digest(PROPOSAL),
            },
        },
        "shards": shard_specs,
        "partition_invariants": {
            "candidate_count": len(candidate_ids),
            "each_candidate_exactly_once": True,
            "subject_context_is_preserved_within_each_shard": True,
            "retrieval_or_association_inputs": "prohibited",
            "aggregation": (
                "mechanical only; every shard must accept every assigned label and "
                "all shard candidate sets must exactly partition the frozen proposal"
            ),
        },
        "authority_boundary": (
            "Shards are evaluation lifecycle-review attempts only. They cannot "
            "change production behavior, assessment, reports, or create semantic "
            "metrics before a separate protocol verification transition."
        ),
    }
    write(PLAN, plan)
    plan_digest = digest(PLAN)

    for spec in shard_specs:
        subject_ids = set(spec["subject_ids"])
        ids = set(spec["candidate_ids"])
        shard_candidates = sorted(
            (item for item in candidates if item["candidate_id"] in ids),
            key=lambda item: item["candidate_id"],
        )
        evidence_ids = {item["evidence_id"] for item in shard_candidates}
        payload = {
            "schema_version": "rg_semantic_ai_lifecycle_shard_input.v1",
            "batch_id": "pr-208-batch-001",
            "shard_id": spec["shard_id"],
            "shard_plan": {
                "path": str(PLAN.relative_to(ROOT)),
                "sha256": plan_digest,
            },
            "candidate_ids": spec["candidate_ids"],
            "verifier_execution": {
                "identity": (
                    "deepseek:deepseek-v4-pro:"
                    f"{spec['shard_id']}-verifier"
                ),
                "provider": "DeepSeek",
                "model_identifier": "deepseek-v4-pro",
                "endpoint_class": "deepseek-openai-compatible",
                "decoding": {
                    "temperature": 0,
                    "max_tokens": 9000,
                    "response_format": "json_object",
                    "store": False,
                    "stream": False,
                },
                "known_reasoning_dependencies": [
                    "The verifier shares the DeepSeek provider with the deepseek-v4-flash proposer.",
                    "It also shares the deepseek-v4-pro model identifier with the prior AI adjudicator, while using a fresh execution and a separately authored shard-verifier prompt.",
                    "This is procedural separation, not a claim of independent error modes or semantic correctness.",
                ],
            },
            "required_artifacts": {
                "prompt": {
                    "path": str(PROMPT.relative_to(ROOT)),
                    "sha256": digest(PROMPT),
                },
                "output_schema": {
                    "path": str(SCHEMA.relative_to(ROOT)),
                    "sha256": digest(SCHEMA),
                },
            },
            "source_bundle": {
                "authored_contract": source["authored_contract"],
                "exact_diff": source["exact_diff"],
                "subjects": [
                    item
                    for item in universe["subjects"]
                    if item["subject_id"] in subject_ids
                ],
                "anchors": [anchors_by_id[item] for item in sorted(evidence_ids)],
                "candidates": shard_candidates,
                "proposed_labels": [labels_by_id[item] for item in spec["candidate_ids"]],
            },
            "prohibited_surfaces": [
                "rg-retrieval-observations",
                "association-attribution",
                "structural-focus observations",
                "policy shadows",
                "comparison outputs",
                "generated RepoDelta reports",
            ],
            "authority_boundary": (
                "This shard is source-evidence review input only. It cannot verify "
                "the reference, emit semantic FI/FE, or alter production behavior."
            ),
        }
        output = RUNS / f"{spec['shard_id']}.input.json"
        write(output, payload)
    print(
        json.dumps(
            {
                "plan": str(PLAN.relative_to(ROOT)),
                "plan_sha256": plan_digest,
                "shard_count": len(shard_specs),
                "candidate_count": len(candidate_ids),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
