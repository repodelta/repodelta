from __future__ import annotations

import json
import subprocess
from pathlib import Path

from repodelta.evaluation.structural_correctness import (
    build_selection_invariance_baseline,
    load_labels,
    load_observation,
    load_packet,
)
from repodelta.evaluation.association_attribution import (
    load_association_attribution,
)


MANIFEST = Path(
    "evaluations/structural-correctness/campaign-v1/manifest.json"
)
CAMPAIGN = MANIFEST.parent
V1_1_MANIFEST = Path(
    "evaluations/structural-correctness/campaign-v1-1/manifest.json"
)
V1_1_CAMPAIGN = V1_1_MANIFEST.parent


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
    _assert_v3_dimensions(summary, expected_rows)
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


def test_campaign_v1_1_association_sidecars_bind_to_frozen_packets() -> None:
    manifest = json.loads(V1_1_MANIFEST.read_text(encoding="utf-8"))

    for sample in manifest["samples"]:
        pull_request = sample["pull_request"]
        packet = load_packet(
            V1_1_CAMPAIGN / "packets" / f"pr-{pull_request}.packet.json"
        )
        sidecar = load_association_attribution(
            V1_1_CAMPAIGN
            / "associations"
            / f"pr-{pull_request}.association.json"
        )

        assert sidecar.packet_digest == packet.digest
        assert all(
            item.subject_kind in {"requirement", "guardrail"}
            and item.slot == "changed_anchor"
            and item.target_type == "evidence"
            for item in sidecar.rows
        )
        assert tuple(item.relation_id for item in sidecar.rows) == tuple(
            sorted(item.relation_id for item in sidecar.rows)
        )


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
    _assert_v3_dimensions(summary, expected_rows)
    assert summary["focus_exact_relations"] == {
        "false_inclusions": sum(
            row["relation_false_inclusions"] for row in expected_rows
        ),
        "false_exclusions": sum(
            row["relation_false_exclusions"] for row in expected_rows
        ),
    }
    assert summary["selection_invariance"] == _selection_invariance_summary()


def test_campaign_v1_1_selection_invariance_is_machine_checked() -> None:
    assert _selection_invariance_summary()["focuses_checked"] == 113


def _selection_invariance_summary() -> dict[str, int | str]:
    baseline = json.loads(
        (
            V1_1_CAMPAIGN
            / "results"
            / "selection-invariance-baseline.json"
        ).read_text(encoding="utf-8")
    )
    assert baseline["schema_version"] == "structural_focus_selection_invariance.v1"
    assert baseline["baseline_commit"] == "090377e"
    assert baseline["source_commit"] == "090377e11a2897fcc5e6a5dcf0fbf00355c08de0"
    pull_requests = tuple(
        item["pull_request"]
        for item in json.loads(V1_1_MANIFEST.read_text(encoding="utf-8"))["samples"]
    )
    assert baseline == _rebuild_selection_invariance_baseline(
        baseline, pull_requests
    )
    current_by_pr = {}
    for sample in json.loads(V1_1_MANIFEST.read_text(encoding="utf-8"))["samples"]:
        pull_request = sample["pull_request"]
        observation = load_observation(
            V1_1_CAMPAIGN
            / "observations"
            / f"pr-{pull_request}.observation.json"
        )
        current_by_pr[pull_request] = {
            item.subject_id: item for item in observation.focuses
        }
    checked = 0
    for sample in baseline["per_pull_request"]:
        pull_request = sample["pull_request"]
        current = current_by_pr[pull_request]
        assert {item["subject_id"] for item in sample["focuses"]} == set(current)
        for expected in sample["focuses"]:
            observed = current[expected["subject_id"]]
            assert set(observed.selected_file_node_ids) == set(
                expected["selected_file_node_ids"]
            )
            assert set(observed.selected_node_ids) == set(
                expected["selected_node_ids"]
            )
            assert set(observed.exact_relation_ids) == set(
                expected["exact_relation_ids"]
            )
            assert observed.disposition_state == expected["disposition_state"]
            checked += 1
    return {
        "status": "passed",
        "baseline_commit": baseline["baseline_commit"],
        "source_commit": baseline["source_commit"],
        "pull_requests": len(baseline["per_pull_request"]),
        "focuses_checked": checked,
        "file_universes_checked": checked,
        "node_universes_checked": checked,
        "relations_checked": checked,
        "dispositions_checked": checked,
    }


def _assert_v3_dimensions(summary, expected_rows) -> None:
    assert summary["schema_version"] == "structural_correctness_campaign_summary.v4"
    assert "focus_nodes" not in summary
    assert summary["selected_membership"] == {
        "files": {
            "false_inclusions": sum(
                row["file_membership_false_inclusions"] for row in expected_rows
            ),
            "false_exclusions": sum(
                row["file_membership_false_exclusions"] for row in expected_rows
            ),
        },
        "nodes": {
            "false_inclusions": sum(
                row["node_membership_false_inclusions"] for row in expected_rows
            ),
            "false_exclusions": sum(
                row["node_membership_false_exclusions"] for row in expected_rows
            ),
        },
    }
    assert summary["claimed_direct"] == {
        "files": {
            "false_inclusions": sum(
                row["file_claimed_direct_false_inclusions"] for row in expected_rows
            ),
            "false_exclusions": sum(
                row["file_claimed_direct_false_exclusions"] for row in expected_rows
            ),
        },
        "nodes": {
            "false_inclusions": sum(
                row["node_claimed_direct_false_inclusions"] for row in expected_rows
            ),
            "false_exclusions": sum(
                row["node_claimed_direct_false_exclusions"] for row in expected_rows
            ),
        },
    }
    assert summary["structural_context"] == {
        "files": {
            "false_inclusions": sum(
                row["file_context_false_inclusions"] for row in expected_rows
            ),
            "false_exclusions": sum(
                row["file_context_false_exclusions"] for row in expected_rows
            ),
        },
        "nodes": {
            "false_inclusions": sum(
                row["node_context_false_inclusions"] for row in expected_rows
            ),
            "false_exclusions": sum(
                row["node_context_false_exclusions"] for row in expected_rows
            ),
        },
    }
    assert summary["suggestions"] == {
        "files_observed": sum(row["file_suggestion_count"] for row in expected_rows),
        "nodes_observed": sum(row["node_suggestion_count"] for row in expected_rows),
        "focuses_with_suggestions": sum(
            row["focuses_with_suggestions"] for row in expected_rows
        ),
    }
    assert summary["legacy_role_comparison"] == {
        "false_inclusions": sum(row["node_false_inclusions"] for row in expected_rows),
        "false_exclusions": sum(row["node_false_exclusions"] for row in expected_rows),
        "role_disagreements": sum(row["node_role_disagreements"] for row in expected_rows),
    }


def _rebuild_selection_invariance_baseline(baseline, pull_requests):
    try:
        return build_selection_invariance_baseline(
            repo_root=Path.cwd(),
            baseline_commit=baseline["baseline_commit"],
            campaign_root=V1_1_CAMPAIGN,
            pull_requests=pull_requests,
        )
    except subprocess.CalledProcessError:
        # CI's shallow checkout may omit the pinned ancestor. Fetch only that
        # immutable commit, then rerun the same source-bound generator.
        try:
            subprocess.run(
                ["git", "fetch", "--no-tags", "origin", baseline["baseline_commit"]],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError:
            # The pinned commit predates the remote PR ref in some CI
            # checkouts. The committed byte-for-byte extraction remains the
            # same source artifact and is verified by its Git blob identities.
            return build_selection_invariance_baseline(
                repo_root=Path.cwd(),
                baseline_commit=baseline["baseline_commit"],
                campaign_root=V1_1_CAMPAIGN,
                pull_requests=pull_requests,
                source_snapshot_root=(
                    V1_1_CAMPAIGN
                    / "results"
                    / "baseline-sources"
                    / baseline["baseline_commit"]
                ),
                source_commit=baseline["source_commit"],
            )
        return build_selection_invariance_baseline(
            repo_root=Path.cwd(),
            baseline_commit=baseline["baseline_commit"],
            campaign_root=V1_1_CAMPAIGN,
            pull_requests=pull_requests,
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
        "node_membership_false_inclusions": 0,
        "node_membership_false_exclusions": 0,
        "node_claimed_direct_false_inclusions": 0,
        "node_claimed_direct_false_exclusions": 0,
        "node_context_false_inclusions": 0,
        "node_context_false_exclusions": 0,
        "node_suggestion_count": 0,
        "file_membership_false_inclusions": 0,
        "file_membership_false_exclusions": 0,
        "file_claimed_direct_false_inclusions": 0,
        "file_claimed_direct_false_exclusions": 0,
        "file_context_false_inclusions": 0,
        "file_context_false_exclusions": 0,
        "file_suggestion_count": 0,
        "focuses_with_suggestions": 0,
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
        expected_node_selected = set(expected.direct_node_ids) | set(
            expected.context_node_ids
        )
        observed_node_selected = set(observed.selected_node_ids)
        row["node_membership_false_inclusions"] += len(
            observed_node_selected - expected_node_selected
        )
        row["node_membership_false_exclusions"] += len(
            expected_node_selected - observed_node_selected
        )
        row["node_claimed_direct_false_inclusions"] += len(
            set(observed.direct_node_ids) - set(expected.direct_node_ids)
        )
        row["node_claimed_direct_false_exclusions"] += len(
            set(expected.direct_node_ids) - set(observed.direct_node_ids)
        )
        row["node_context_false_inclusions"] += len(
            set(observed.context_node_ids) - set(expected.context_node_ids)
        )
        row["node_context_false_exclusions"] += len(
            set(expected.context_node_ids) - set(observed.context_node_ids)
        )
        row["node_suggestion_count"] += len(observed.suggested_node_ids)
        observed_relations = set(observed.exact_relation_ids)
        expected_relations = set(expected.relation_ids)
        row["relation_false_inclusions"] += len(
            observed_relations - expected_relations
        )
        row["relation_false_exclusions"] += len(
            expected_relations - observed_relations
        )
        expected_file_selected = set(expected.direct_file_node_ids) | set(
            expected.context_file_node_ids
        )
        observed_file_selected = set(observed.selected_file_node_ids)
        row["file_membership_false_inclusions"] += len(
            observed_file_selected - expected_file_selected
        )
        row["file_membership_false_exclusions"] += len(
            expected_file_selected - observed_file_selected
        )
        row["file_claimed_direct_false_inclusions"] += len(
            set(observed.direct_file_node_ids) - set(expected.direct_file_node_ids)
        )
        row["file_claimed_direct_false_exclusions"] += len(
            set(expected.direct_file_node_ids) - set(observed.direct_file_node_ids)
        )
        row["file_context_false_inclusions"] += len(
            set(observed.context_file_node_ids) - set(expected.context_file_node_ids)
        )
        row["file_context_false_exclusions"] += len(
            set(expected.context_file_node_ids) - set(observed.context_file_node_ids)
        )
        row["file_suggestion_count"] += len(observed.suggested_file_node_ids)
        if observed.suggested_node_ids or observed.suggested_file_node_ids:
            row["focuses_with_suggestions"] += 1
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
