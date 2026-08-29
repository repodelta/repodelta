"""Regenerate frozen v1.1 R/G candidate-universe artifacts from live reviews.

The historical v1.1 packets preserve only the already projected structural
surface.  They cannot reconstruct changed anchors that production association
did not retrieve.  This script therefore re-runs the exact reviewed PRs,
checks that their ordinary blind packets remain byte-identical, and commits
only the additional evaluation-only candidate and retrieval artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from repodelta.evaluation.rg_candidate_universe import load_rg_candidate_universe


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate frozen v1.1 R/G semantic-candidate artifacts"
    )
    parser.add_argument(
        "--campaign",
        type=Path,
        default=Path(__file__).parent,
        help="Frozen campaign directory",
    )
    parser.add_argument(
        "--repo",
        default="repodelta/repodelta",
        help="GitHub repository containing the reviewed pull requests",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python interpreter with the current RepoDelta source on PYTHONPATH",
    )
    parser.add_argument(
        "--pull-request",
        action="append",
        type=int,
        default=[],
        help="Regenerate only one or more listed campaign pull requests",
    )
    args = parser.parse_args()
    campaign = args.campaign.resolve()
    manifest = json.loads((campaign / "manifest.json").read_text(encoding="utf-8"))
    candidate_dir = campaign / "rg-candidate-universes"
    retrieval_dir = campaign / "rg-retrieval-observations"
    result_dir = campaign / "results" / "rg-candidate-universe"
    for directory in (candidate_dir, retrieval_dir, result_dir):
        directory.mkdir(parents=True, exist_ok=True)

    requested = set(args.pull_request)
    manifest_samples = [
        sample
        for sample in manifest["samples"]
        if not requested or int(sample["pull_request"]) in requested
    ]
    known_pull_requests = {int(sample["pull_request"]) for sample in manifest["samples"]}
    unknown = requested - known_pull_requests
    if unknown:
        raise ValueError("pull request is not in the frozen campaign: " + ", ".join(map(str, sorted(unknown))))
    if not manifest_samples:
        raise ValueError("candidate-universe regeneration selected no samples")
    with tempfile.TemporaryDirectory(prefix="repodelta-rg-candidates-") as temp:
        workspace = Path(temp)
        for sample in manifest_samples:
            pull_request = int(sample["pull_request"])
            stem = f"pr-{pull_request}.packet.json"
            packet_output = workspace / stem
            report_output = workspace / f"pr-{pull_request}.html"
            command = [
                args.python,
                "-m",
                "repodelta.cli",
                "review",
                "--repo",
                args.repo,
                "--pr",
                str(pull_request),
                "--output",
                str(report_output),
                "--structural-correctness-packet-output",
                str(packet_output),
            ]
            subprocess.run(command, check=True)
            expected_packet = campaign / "packets" / stem
            if _digest(packet_output) != _digest(expected_packet):
                raise ValueError(
                    f"PR #{pull_request}: ordinary frozen packet changed; "
                    "refusing to write candidate artifacts"
                )
            candidates_path = Path(f"{packet_output}.rg-candidates.json")
            retrieval_path = Path(f"{packet_output}.rg-retrieval.json")
            for path in (candidates_path, retrieval_path):
                if not path.exists():
                    raise ValueError(
                        f"PR #{pull_request}: review omitted {path.name}"
                    )
            candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            retrieval = json.loads(retrieval_path.read_text(encoding="utf-8"))
            shutil.copyfile(
                candidates_path, candidate_dir / f"pr-{pull_request}.json"
            )
            shutil.copyfile(
                retrieval_path, retrieval_dir / f"pr-{pull_request}.json"
            )
    expected_paths = [
        candidate_dir / f"pr-{int(sample['pull_request'])}.json"
        for sample in manifest["samples"]
    ]
    if not all(path.exists() for path in expected_paths):
        print("candidate-universe artifacts generated; campaign summary waits for every sample")
        return 0
    aggregate = Counter()
    samples: list[dict[str, object]] = []
    for sample in manifest["samples"]:
        pull_request = int(sample["pull_request"])
        candidates = json.loads(
            (candidate_dir / f"pr-{pull_request}.json").read_text(encoding="utf-8")
        )
        retrieval = json.loads(
            (retrieval_dir / f"pr-{pull_request}.json").read_text(encoding="utf-8")
        )
        universe = load_rg_candidate_universe(candidate_dir / f"pr-{pull_request}.json")
        aggregate["candidate_count"] += len(candidates["candidates"])
        aggregate["subject_count"] += len(candidates["subjects"])
        anchors_by_id = {
            item["evidence_id"]: item for item in candidates["anchors"]
        }
        aggregate.update(
            f"node_state:{anchors_by_id[item['evidence_id']]['node_state']}"
            for item in candidates["candidates"]
        )
        aggregate.update(
            f"retrieval_state:{item['retrieval_state']}" for item in retrieval["rows"]
        )
        aggregate.update(
            f"association:{item['association'] or 'not_retrieved'}" for item in retrieval["rows"]
        )
        samples.append(
            {
                "pull_request": pull_request,
                "candidate_universe_digest": universe.digest,
                "candidate_count": len(candidates["candidates"]),
                "subject_count": len(candidates["subjects"]),
            }
        )
    summary = {
        "schema_version": "rg_semantic_candidate_campaign_summary.v1",
        "campaign_id": manifest["campaign_id"],
        "sample_count": len(samples),
        "samples": samples,
        "aggregate": dict(sorted(aggregate.items())),
        "reference_state": "not_frozen",
        "limits": {
            "authority": "evaluation-only; no production association, projection, assessment, or report changed",
            "packet_invariance": "each regenerated ordinary packet matched its frozen v1.1 packet by SHA-256",
            "semantic_reference": "a blind template is generated from the frozen universe before independent labeling; no semantic reference is committed",
            "coverage": "candidate universe is profile-eligible changed anchors, not repository-wide semantic completeness",
        },
    }
    output = result_dir / "summary.json"
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
