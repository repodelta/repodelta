from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from repodelta.evaluation.focus_attribution import (
    load_structural_focus_attribution,
    summarize_attribution_campaign,
)
from repodelta.evaluation.structural_correctness import (
    load_labels,
    load_observation,
    load_packet,
)


MANIFEST = Path(
    "evaluations/structural-correctness/campaign-v1/manifest.json"
)
CAMPAIGN = MANIFEST.parent
V1_1_MANIFEST = Path(
    "evaluations/structural-correctness/campaign-v1-1/manifest.json"
)
V1_1_CAMPAIGN = V1_1_MANIFEST.parent
V1_2_MANIFEST = Path(
    "evaluations/structural-correctness/campaign-v1-2/manifest.json"
)
V1_2_CAMPAIGN = V1_2_MANIFEST.parent


def test_campaign_v1_manifest_freezes_diverse_real_pr_sample() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    samples = manifest["samples"]

    assert manifest["schema_version"] == (
        "structural_correctness_campaign_manifest.v1"
    )
    assert manifest["repository"] == "repodelta/repodelta"
    assert manifest["requirements"] == {
        "human_exclusion_required": True,
        "human_unresolved_required": True,
        "real_pull_request_count": 8,
        "synthetic_counterexample_policy": "complement_only",
    }
    assert [item["pull_request"] for item in samples] == [
        208,
        238,
        245,
        250,
        235,
        262,
        267,
        240,
    ]
    assert len({item["pull_request"] for item in samples}) == 8
    assert len({item["change_shape"] for item in samples}) == 8
    assert all(item["purpose"].strip() for item in samples)


def test_campaign_material_is_separate_from_product_documentation() -> None:
    assert Path("evaluations/structural-correctness/README.md").is_file()
    assert not Path("docs/structural-correctness.md").exists()


def test_campaign_v1_freezes_complete_separate_inputs_and_results() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    excluded_files = 0
    unresolved_focuses = 0

    for sample in manifest["samples"]:
        pull_request = sample["pull_request"]
        packet = load_packet(CAMPAIGN / "packets" / f"pr-{pull_request}.packet.json")
        labels = load_labels(
            CAMPAIGN / "labels" / f"pr-{pull_request}.labels.json",
            packet,
        )
        observation = load_observation(
            CAMPAIGN
            / "observations"
            / f"pr-{pull_request}.observation.json"
        )

        assert observation.packet_digest == packet.digest
        assert (CAMPAIGN / "results" / f"pr-{pull_request}.comparison.html").is_file()
        excluded_files += sum(
            item.disposition == "excluded" for item in labels.files
        )
        unresolved_focuses += sum(item.unresolved for item in labels.focuses)

    assert excluded_files > 0
    assert unresolved_focuses > 0


def test_campaign_v1_summary_is_derived_from_frozen_truth() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    summary = json.loads(
        (CAMPAIGN / "results" / "summary.json").read_text(encoding="utf-8")
    )
    expected_rows = []

    for sample in manifest["samples"]:
        pull_request = sample["pull_request"]
        packet = load_packet(CAMPAIGN / "packets" / f"pr-{pull_request}.packet.json")
        labels = load_labels(
            CAMPAIGN / "labels" / f"pr-{pull_request}.labels.json",
            packet,
        )
        observation = load_observation(
            CAMPAIGN
            / "observations"
            / f"pr-{pull_request}.observation.json"
        )
        expected_rows.append(
            _campaign_row(pull_request, labels, observation)
        )

    assert summary["sample_count"] == len(expected_rows)
    assert summary["reference_status"] == "proposed_agent_prepared"
    assert summary["per_pull_request"] == expected_rows
    assert summary["focuses_resolved"] == sum(
        row["focuses_resolved"] for row in expected_rows
    )
    assert summary["focuses_unresolved"] == sum(
        row["focuses_unresolved"] for row in expected_rows
    )
    assert summary["overview"] == {
        "false_inclusions": sum(
            row["overview_false_inclusions"] for row in expected_rows
        ),
        "false_exclusions": sum(
            row["overview_false_exclusions"] for row in expected_rows
        ),
        "role_disagreements": sum(
            row["overview_role_disagreements"] for row in expected_rows
        ),
    }
    assert summary["focus_nodes"] == {
        "false_inclusions": sum(
            row["node_false_inclusions"] for row in expected_rows
        ),
        "false_exclusions": sum(
            row["node_false_exclusions"] for row in expected_rows
        ),
        "role_disagreements": sum(
            row["node_role_disagreements"] for row in expected_rows
        ),
    }
    assert summary["focus_exact_relations"] == {
        "false_inclusions": sum(
            row["relation_false_inclusions"] for row in expected_rows
        ),
        "false_exclusions": sum(
            row["relation_false_exclusions"] for row in expected_rows
        ),
    }
    assert summary["next_investment"] == "correct_underlying_projection"


def test_campaign_v1_1_binds_verified_references_before_comparison() -> None:
    manifest = json.loads(V1_1_MANIFEST.read_text(encoding="utf-8"))

    assert manifest["campaign_id"] == "structural-correctness-v1.1"
    assert manifest["reference_contract"] == {
        "authority": "independently_verified",
        "observation_isolated_until_reference_freeze": True,
        "relation_endpoints_required": True,
        "unresolved_preserved": True,
    }
    for sample in manifest["samples"]:
        pull_request = sample["pull_request"]
        packet = load_packet(
            V1_1_CAMPAIGN / "packets" / f"pr-{pull_request}.packet.json"
        )
        proposal = load_labels(
            V1_1_CAMPAIGN / "proposals" / f"pr-{pull_request}.proposal.json",
            packet,
        )
        reference = load_labels(
            V1_1_CAMPAIGN / "references" / f"pr-{pull_request}.reference.json",
            packet,
        )
        observation = load_observation(
            V1_1_CAMPAIGN
            / "observations"
            / f"pr-{pull_request}.observation.json"
        )

        assert proposal.authority.status == "proposed"
        assert reference.authority.status == "verified"
        assert reference.authority.proposal_digest == proposal.proposal_digest
        assert reference.authority.system_under_test_isolated is True
        assert reference.authority.verification_evidence
        assert observation.packet_digest == packet.digest
        assert (
            V1_1_CAMPAIGN
            / "results"
            / f"pr-{pull_request}.comparison.html"
        ).is_file()


def test_campaign_v1_1_summary_is_derived_from_verified_references() -> None:
    manifest = json.loads(V1_1_MANIFEST.read_text(encoding="utf-8"))
    summary = json.loads(
        (V1_1_CAMPAIGN / "results" / "summary.json").read_text(
            encoding="utf-8"
        )
    )
    expected_rows = []
    for sample in manifest["samples"]:
        pull_request = sample["pull_request"]
        packet = load_packet(
            V1_1_CAMPAIGN / "packets" / f"pr-{pull_request}.packet.json"
        )
        labels = load_labels(
            V1_1_CAMPAIGN / "references" / f"pr-{pull_request}.reference.json",
            packet,
        )
        observation = load_observation(
            V1_1_CAMPAIGN
            / "observations"
            / f"pr-{pull_request}.observation.json"
        )
        row = _campaign_row(pull_request, labels, observation)
        row["focus_coverage"] = _focus_coverage_counts(packet, labels)
        expected_rows.append(row)

    assert summary["reference_status"] == "independently_verified"
    assert summary["sample_count"] == len(expected_rows)
    assert summary["per_pull_request"] == expected_rows
    assert summary["focuses_resolved"] == sum(
        row["focuses_resolved"] for row in expected_rows
    )
    assert summary["focuses_unresolved"] == sum(
        row["focuses_unresolved"] for row in expected_rows
    )
    assert summary["focus_coverage"] == {
        key: sum(row["focus_coverage"][key] for row in expected_rows)
        for key in ("complete", "limited", "empty", "unknown", "unresolved")
    }
    assert summary["overview"] == {
        "false_inclusions": sum(
            row["overview_false_inclusions"] for row in expected_rows
        ),
        "false_exclusions": sum(
            row["overview_false_exclusions"] for row in expected_rows
        ),
        "role_disagreements": sum(
            row["overview_role_disagreements"] for row in expected_rows
        ),
    }
    assert summary["focus_nodes"] == {
        "false_inclusions": sum(
            row["node_false_inclusions"] for row in expected_rows
        ),
        "false_exclusions": sum(
            row["node_false_exclusions"] for row in expected_rows
        ),
        "role_disagreements": sum(
            row["node_role_disagreements"] for row in expected_rows
        ),
    }
    assert summary["focus_exact_relations"] == {
        "false_inclusions": sum(
            row["relation_false_inclusions"] for row in expected_rows
        ),
        "false_exclusions": sum(
            row["relation_false_exclusions"] for row in expected_rows
        ),
    }


def test_campaign_v1_2_attributes_unchanged_production_observations() -> None:
    manifest = json.loads(V1_2_MANIFEST.read_text(encoding="utf-8"))
    source_manifest = json.loads(V1_1_MANIFEST.read_text(encoding="utf-8"))

    assert manifest["campaign_id"] == "structural-correctness-v1.2"
    assert manifest["pull_requests"] == [
        item["pull_request"] for item in source_manifest["samples"]
    ]
    assert manifest["contract"] == {
        "production_output_unchanged": True,
        "packet_and_observation_digest_equality_required": True,
        "reference_isolated_from_attribution_derivation": True,
        "unsupported_production_paths_fail_closed": True,
        "counterfactual_replay_only_removes_recorded_producer_paths": True,
    }

    cases = []
    for pull_request in manifest["pull_requests"]:
        packet = load_packet(
            V1_1_CAMPAIGN / "packets" / f"pr-{pull_request}.packet.json"
        )
        observation = load_observation(
            V1_1_CAMPAIGN
            / "observations"
            / f"pr-{pull_request}.observation.json"
        )
        reference = load_labels(
            V1_1_CAMPAIGN
            / "references"
            / f"pr-{pull_request}.reference.json",
            packet,
        )
        attribution = load_structural_focus_attribution(
            V1_2_CAMPAIGN
            / "attributions"
            / f"pr-{pull_request}.attribution.json"
        )

        assert observation.packet_digest == packet.digest
        assert attribution.packet_digest == packet.digest
        assert all(
            not membership.unsupported_reason
            for focus in attribution.focuses
            for membership in focus.memberships
        )
        cases.append((packet, observation, attribution, reference))

    expected = json.loads(
        (V1_2_CAMPAIGN / "results" / "summary.json").read_text(
            encoding="utf-8"
        )
    )
    actual = json.loads(
        json.dumps(asdict(summarize_attribution_campaign(cases)))
    )
    assert actual == expected


def test_campaign_v1_2_counterfactuals_expose_distinct_producer_risks() -> None:
    summary = json.loads(
        (V1_2_CAMPAIGN / "results" / "summary.json").read_text(
            encoding="utf-8"
        )
    )
    baseline = {item["subject_kind"]: item for item in summary["baseline"]}
    counterfactuals = {
        item["producer_class"]: {
            outcome["subject_kind"]: outcome for outcome in item["outcomes"]
        }
        for item in summary["counterfactuals"]
    }

    path_requirement = counterfactuals["structural_path"]["requirement"]
    assert path_requirement["node_false_inclusions"] == (
        baseline["requirement"]["node_false_inclusions"] - 189
    )
    assert path_requirement["node_false_exclusions"] == (
        baseline["requirement"]["node_false_exclusions"] + 2
    )

    phrase_requirement = counterfactuals["distinctive_phrase"]["requirement"]
    assert phrase_requirement["node_false_inclusions"] == (
        baseline["requirement"]["node_false_inclusions"] - 516
    )
    assert phrase_requirement["node_false_exclusions"] == (
        baseline["requirement"]["node_false_exclusions"] + 79
    )

    selector_claim = counterfactuals["transformation_selector"][
        "transformation_claim"
    ]
    assert selector_claim["node_false_inclusions"] == 0
    assert counterfactuals["transformation_selector"]["requirement"] == (
        baseline["requirement"]
    )


def _campaign_row(pull_request, labels, observation):
    observed_files = {item.file_node_id: item for item in observation.files}
    row = {
        "pull_request": pull_request,
        "overview_false_inclusions": 0,
        "overview_false_exclusions": 0,
        "overview_role_disagreements": 0,
        "focuses_resolved": 0,
        "focuses_unresolved": 0,
        "node_false_inclusions": 0,
        "node_false_exclusions": 0,
        "node_role_disagreements": 0,
        "relation_false_inclusions": 0,
        "relation_false_exclusions": 0,
    }
    for expected in labels.files:
        observed = observed_files.get(expected.file_node_id)
        if expected.disposition == "unresolved":
            continue
        if observed is None and expected.disposition == "included":
            row["overview_false_exclusions"] += 1
        elif observed is not None and expected.disposition == "excluded":
            row["overview_false_inclusions"] += 1
        elif observed is not None and observed.role != expected.role:
            row["overview_role_disagreements"] += 1

    observed_focuses = {item.subject_id: item for item in observation.focuses}
    for expected in labels.focuses:
        if expected.unresolved:
            row["focuses_unresolved"] += 1
            continue
        row["focuses_resolved"] += 1
        observed = observed_focuses[expected.subject_id]
        observed_roles = {
            **{item: "direct" for item in observed.direct_node_ids},
            **{item: "context" for item in observed.context_node_ids},
        }
        expected_roles = {
            **{item: "direct" for item in expected.direct_node_ids},
            **{item: "context" for item in expected.context_node_ids},
        }
        shared_ids = observed_roles.keys() & expected_roles.keys()
        row["node_false_inclusions"] += len(
            observed_roles.keys() - expected_roles.keys()
        )
        row["node_false_exclusions"] += len(
            expected_roles.keys() - observed_roles.keys()
        )
        row["node_role_disagreements"] += sum(
            observed_roles[item] != expected_roles[item] for item in shared_ids
        )
        observed_relations = set(observed.exact_relation_ids)
        expected_relations = set(expected.relation_ids)
        row["relation_false_inclusions"] += len(
            observed_relations - expected_relations
        )
        row["relation_false_exclusions"] += len(
            expected_relations - observed_relations
        )
    return row


def _focus_coverage_counts(packet, labels):
    counts = {
        "complete": 0,
        "limited": 0,
        "empty": 0,
        "unknown": 0,
        "unresolved": 0,
    }
    seed_states = {item.node_id: item.state for item in packet.coverage.seeds}
    for focus in labels.focuses:
        if focus.unresolved:
            counts["unresolved"] += 1
            continue
        memberships = {
            *focus.direct_file_node_ids,
            *focus.context_file_node_ids,
            *focus.direct_node_ids,
            *focus.context_node_ids,
            *focus.relation_ids,
        }
        states = [
            seed_states[item]
            for item in focus.direct_node_ids
            if item in seed_states
        ]
        if not memberships:
            counts["empty"] += 1
        elif packet.coverage.seed_mapping_state != "complete" or not states:
            counts["unknown"] += 1
        elif "truncated" in states:
            counts["limited"] += 1
        elif "unknown" in states:
            counts["unknown"] += 1
        else:
            counts["complete"] += 1
    return counts
