from __future__ import annotations

import json
from pathlib import Path

from repodelta.evaluation.structural_correctness import load_labels, load_packet


MANIFEST = Path(
    "evaluations/structural-correctness/campaign-v1/manifest.json"
)


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


def test_campaign_v1_freezes_blind_packets_and_complete_proposed_labels() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    corpus = MANIFEST.parent
    excluded = 0
    unresolved_focuses = 0

    for sample in manifest["samples"]:
        pull_request = sample["pull_request"]
        packet_path = corpus / "packets" / f"pr-{pull_request}.json"
        packet = load_packet(packet_path)
        labels = load_labels(
            corpus / "labels" / f"pr-{pull_request}.json", packet
        )

        assert packet.schema_version == "structural_correctness_packet.v3"
        assert packet.coverage.complete_seed_count <= packet.coverage.seed_count
        serialized = packet_path.read_text(encoding="utf-8")
        assert '"direct_file_node_ids"' not in serialized
        assert '"context_file_node_ids"' not in serialized
        assert '"retained_bridge"' not in serialized
        excluded += sum(item.disposition == "excluded" for item in labels.files)
        unresolved_focuses += sum(item.unresolved for item in labels.focuses)

    assert excluded == 86
    assert unresolved_focuses == 47


def test_campaign_v1_summary_records_membership_failure_before_provenance() -> None:
    summary = json.loads(
        (MANIFEST.parent / "results" / "summary.json").read_text(encoding="utf-8")
    )

    assert summary["label_status"] == "proposed_until_maintainer_merge"
    assert summary["totals"] == {
        "file_false_exclusion": 0,
        "file_false_inclusion": 24,
        "file_match": 192,
        "file_role_disagreement": 8,
        "focus_exact": 21,
        "focus_false_exclusion": 42,
        "focus_false_inclusion": 250,
        "focus_scored": 66,
        "focus_unresolved": 47,
    }
    assert summary["decision"] == {
        "coverage_truthfulness": "required",
        "focus_provenance": "required_after_membership_correction",
        "large_change_clustering": "defer_until_correctness_improves",
        "underlying_projection_correction": "required",
        "workflow_traceability": "independent_later_work",
    }
