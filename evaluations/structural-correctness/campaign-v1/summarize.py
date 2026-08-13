from __future__ import annotations

import json
from pathlib import Path

from repodelta.evaluation.structural_correctness import (
    load_labels,
    load_observation,
    load_packet,
)


ROOT = Path(__file__).parent


def main() -> int:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    samples = []
    totals = {
        "file_match": 0,
        "file_false_inclusion": 0,
        "file_false_exclusion": 0,
        "file_role_disagreement": 0,
        "focus_exact": 0,
        "focus_scored": 0,
        "focus_false_inclusion": 0,
        "focus_false_exclusion": 0,
        "focus_unresolved": 0,
    }
    for sample in manifest["samples"]:
        pull_request = sample["pull_request"]
        packet = load_packet(ROOT / "packets" / f"pr-{pull_request}.json")
        labels = load_labels(ROOT / "labels" / f"pr-{pull_request}.json", packet)
        observation = load_observation(
            ROOT / "observations" / f"pr-{pull_request}.json"
        )
        observed_files = {item.file_node_id: item.role for item in observation.files}
        file_counts = {
            "match": 0,
            "false_inclusion": 0,
            "false_exclusion": 0,
            "role_disagreement": 0,
        }
        for label in labels.files:
            observed_role = observed_files.get(label.file_node_id)
            if label.disposition == "included" and observed_role is None:
                file_counts["false_exclusion"] += 1
            elif label.disposition == "excluded" and observed_role is not None:
                file_counts["false_inclusion"] += 1
            elif label.disposition == "included" and observed_role != label.role:
                file_counts["role_disagreement"] += 1
            else:
                file_counts["match"] += 1
        observed_focuses = {item.subject_id: item for item in observation.focuses}
        focus_counts = {
            "exact": 0,
            "scored": 0,
            "false_inclusion": 0,
            "false_exclusion": 0,
            "unresolved": 0,
        }
        for label in labels.focuses:
            if label.unresolved:
                focus_counts["unresolved"] += 1
                continue
            focus_counts["scored"] += 1
            observed = observed_focuses[label.subject_id]
            expected_ids = set(
                (*label.direct_file_node_ids, *label.context_file_node_ids)
            )
            observed_ids = set(
                (*observed.direct_file_node_ids, *observed.context_file_node_ids)
            )
            focus_counts["exact"] += expected_ids == observed_ids
            focus_counts["false_inclusion"] += len(observed_ids - expected_ids)
            focus_counts["false_exclusion"] += len(expected_ids - observed_ids)
        for name, value in file_counts.items():
            totals[f"file_{name}"] += value
        for name, value in focus_counts.items():
            totals[f"focus_{name}"] += value
        samples.append(
            {
                "pull_request": pull_request,
                "change_shape": sample["change_shape"],
                "coverage": {
                    "state": packet.coverage.state,
                    "complete_seed_count": packet.coverage.complete_seed_count,
                    "seed_count": packet.coverage.seed_count,
                    "truncated_seed_count": packet.coverage.truncated_seed_count,
                },
                "files": file_counts,
                "focuses": focus_counts,
            }
        )
    summary = {
        "campaign_id": manifest["campaign_id"],
        "label_status": "proposed_until_maintainer_merge",
        "samples": samples,
        "totals": totals,
        "decision": {
            "underlying_projection_correction": "required",
            "focus_provenance": "required_after_membership_correction",
            "coverage_truthfulness": "required",
            "large_change_clustering": "defer_until_correctness_improves",
            "workflow_traceability": "independent_later_work",
        },
        "schema_version": "structural_correctness_campaign_summary.v1",
    }
    (ROOT / "results" / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
