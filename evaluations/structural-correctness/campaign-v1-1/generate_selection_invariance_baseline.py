"""Rebuild the v1.1 pre-provenance selection baseline from a pinned Git commit.

Run from the repository root, for example:

    PYTHONPATH=src python \
      evaluations/structural-correctness/campaign-v1-1/\
      generate_selection_invariance_baseline.py \
      --baseline-commit 090377e

The command reads only the pinned commit's observation artifacts and records
their Git blob identities in the output.  It never reads the current
observation files to manufacture the baseline.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from repodelta.evaluation.structural_correctness import (
    build_selection_invariance_baseline,
)


DEFAULT_CAMPAIGN = Path("evaluations/structural-correctness/campaign-v1-1")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-commit", required=True)
    parser.add_argument("--campaign-root", type=Path, default=DEFAULT_CAMPAIGN)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest = json.loads(
        (args.campaign_root / "manifest.json").read_text(encoding="utf-8")
    )
    pull_requests = tuple(item["pull_request"] for item in manifest["samples"])
    artifact = build_selection_invariance_baseline(
        repo_root=Path.cwd(),
        baseline_commit=args.baseline_commit,
        campaign_root=args.campaign_root,
        pull_requests=pull_requests,
    )
    output = args.output or (
        args.campaign_root / "results" / "selection-invariance-baseline.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(output)


if __name__ == "__main__":
    main()
