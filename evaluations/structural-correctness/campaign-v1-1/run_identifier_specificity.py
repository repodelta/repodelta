"""Generate the evaluation-only R/G identifier shadow for frozen v1.1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from repodelta.evaluation.association_attribution import load_association_attribution
from repodelta.evaluation.identifier_specificity import (
    aggregate_identifier_policy_shadows,
    compare_identifier_policies,
    observe_identifier_specificity_from_artifacts,
    write_identifier_policy_shadow,
    write_identifier_specificity,
)
from repodelta.evaluation.structural_correctness import (
    load_labels,
    load_observation,
    load_packet,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate frozen v1.1 identifier specificity policy shadows"
    )
    parser.add_argument(
        "--campaign",
        type=Path,
        default=Path(__file__).parent,
        help="Frozen campaign directory",
    )
    args = parser.parse_args()
    campaign = args.campaign
    manifest = json.loads((campaign / "manifest.json").read_text(encoding="utf-8"))
    result_dir = campaign / "results" / "identifier-specificity"
    probe_dir = result_dir / "probes"
    policy_dir = result_dir / "policies"
    shadows = {}
    for sample in manifest["samples"]:
        pull_request = int(sample["pull_request"])
        packet = load_packet(campaign / "packets" / f"pr-{pull_request}.packet.json")
        observation = load_observation(
            campaign / "observations" / f"pr-{pull_request}.observation.json"
        )
        labels = load_labels(
            campaign / "references" / f"pr-{pull_request}.reference.json", packet
        )
        attribution = load_association_attribution(
            campaign / "associations" / f"pr-{pull_request}.association.json"
        )
        specificity = observe_identifier_specificity_from_artifacts(packet, attribution)
        write_identifier_specificity(
            specificity, probe_dir / f"pr-{pull_request}.json"
        )
        shadow = compare_identifier_policies(
            packet, observation, labels, attribution, specificity
        )
        write_identifier_policy_shadow(
            shadow, policy_dir / f"pr-{pull_request}.json"
        )
        shadows[f"pr-{pull_request}"] = shadow
    summary = aggregate_identifier_policy_shadows(shadows)
    write_identifier_policy_shadow(summary, result_dir / "summary.json")
    print(result_dir / "summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

