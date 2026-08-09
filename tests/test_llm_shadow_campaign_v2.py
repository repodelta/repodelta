from __future__ import annotations

from pathlib import Path

from prismcode.evaluation.shadow import load_human_shadow_labels_from_packet
from prismcode.llm import load_shadow_labeling_packet


CORPUS = Path("fixtures/llm-shadow/campaign-v2")
PULL_REQUESTS = (148, 168, 193, 200, 205, 206, 213, 218)


def test_campaign_v2_freezes_complete_pre_execution_reference_labels() -> None:
    request_count = 0
    selected_count = 0
    rejected_count = 0
    insufficient_count = 0

    for pull_request in PULL_REQUESTS:
        packet_path = CORPUS / f"pr-{pull_request}.labeling.json"
        labels_path = CORPUS / f"pr-{pull_request}.human-labels.json"
        packet = load_shadow_labeling_packet(packet_path)
        labels = load_human_shadow_labels_from_packet(labels_path, packet)

        assert packet.repository == "prismcode-ai/prismcode"
        assert packet.pull_request == pull_request
        assert packet.head_sha
        assert packet.base_sha
        assert '"run"' not in packet_path.read_text(encoding="utf-8")
        assert '"selection"' not in packet_path.read_text(encoding="utf-8")

        request_count += len(labels.labels)
        selected_count += sum(
            len(item.selection.selections) for item in labels.labels
        )
        rejected_count += sum(
            len(item.selection.rejected_evidence_ids) for item in labels.labels
        )
        insufficient_count += sum(
            len(item.selection.insufficient_evidence_ids)
            for item in labels.labels
        )

    assert (
        request_count,
        selected_count,
        rejected_count,
        insufficient_count,
    ) == (38, 134, 92, 25)


def test_campaign_v2_contains_real_negative_and_ambiguous_surfaces() -> None:
    dispositions: dict[int, tuple[int, int]] = {}
    for pull_request in PULL_REQUESTS:
        packet = load_shadow_labeling_packet(
            CORPUS / f"pr-{pull_request}.labeling.json"
        )
        labels = load_human_shadow_labels_from_packet(
            CORPUS / f"pr-{pull_request}.human-labels.json",
            packet,
        )
        dispositions[pull_request] = (
            sum(
                len(item.selection.rejected_evidence_ids)
                for item in labels.labels
            ),
            sum(
                len(item.selection.insufficient_evidence_ids)
                for item in labels.labels
            ),
        )

    assert dispositions[148][0] > 0
    assert dispositions[200][0] > 0
    assert dispositions[193][1] > 0
    assert dispositions[200][1] > 0
    assert dispositions[213][0] > 0
    assert dispositions[213][1] > 0
