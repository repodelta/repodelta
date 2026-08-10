from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from repodelta.evaluation.comparison import load_shadow_comparison_inputs
from repodelta.evaluation.shadow import (
    ExpectedShadowOutcome,
    evaluate_shadow_outcomes,
    load_human_shadow_labels_from_packet,
    shadow_metrics,
)
from repodelta.llm import load_shadow_labeling_packet


CORPUS = Path("fixtures/llm-shadow/campaign-v2")
PULL_REQUESTS = (148, 168, 193, 200, 205, 206, 213, 218)


def _outcomes(pull_request: int):
    inputs = load_shadow_comparison_inputs(
        CORPUS / f"pr-{pull_request}.labeling.json",
        CORPUS / f"pr-{pull_request}.observation.json",
        CORPUS / f"pr-{pull_request}.human-labels.json",
    )
    bundle = inputs.execution
    expected = tuple(
        ExpectedShadowOutcome(
            claim_id=item.claim_id,
            execution_state=item.execution_state,
            diagnostic_codes=(
                *(value.code for value in item.diagnostics),
                *(
                    value.code
                    for value in (
                        item.run.diagnostics if item.run is not None else ()
                    )
                ),
            ),
        )
        for item in bundle.observations
    )
    return bundle, evaluate_shadow_outcomes(
        f"pr-{pull_request}",
        expected,
        inputs.labels,
        bundle,
    )


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

        historical_repository = "prism" + "code-ai/" + "prism" + "code"
        assert packet.repository == historical_repository
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


def test_campaign_v2_records_bounded_live_execution_without_provider_failure() -> None:
    states = Counter()
    outcomes = []
    execution_policies = set()

    for pull_request in PULL_REQUESTS:
        bundle, observed = _outcomes(pull_request)
        states.update(item.execution_state for item in bundle.observations)
        execution_policies.update(
            (
                item.run.execution_policy.api_profile,
                item.run.execution_policy.endpoint,
                item.run.execution_policy.model_id,
                item.run.execution_policy.thinking_mode,
                item.run.execution_policy.max_output_tokens,
                item.run.execution_policy.timeout_seconds,
            )
            for item in bundle.observations
            if item.run is not None
        )
        outcomes.extend(observed)

    metrics = shadow_metrics(tuple(outcomes))

    assert states == {"accepted": 20, "deferred": 18}
    assert execution_policies == {
        (
            "deepseek",
            "https://api.deepseek.com/chat/completions",
            "deepseek-v4-flash",
            "disabled",
            4_000,
            180.0,
        )
    }
    assert metrics.outcome_count == 38
    assert metrics.live_count == 20
    assert metrics.execution_policy_ids == (
        "shadow-policy:f49ded2093e7837149c4",
    )
    assert metrics.total_input_tokens == 60_435
    assert metrics.total_output_tokens == 10_971
    assert metrics.total_duration_ms == pytest.approx(99_335.875, abs=0.01)
    assert metrics.state_accuracy == 1.0
    assert metrics.diagnostic_accuracy == 1.0


def test_campaign_v2_accepted_runs_measure_semantic_quality_separately() -> None:
    accepted = tuple(
        outcome
        for pull_request in PULL_REQUESTS
        for outcome in _outcomes(pull_request)[1]
        if outcome.observed_execution_state == "accepted"
    )

    metrics = shadow_metrics(accepted)

    assert metrics.human_labeled_outcome_count == 20
    assert metrics.candidate_label_count == 108
    assert metrics.selection_precision == 0.75
    assert metrics.selection_recall == 1.0
    assert metrics.disposition_accuracy == pytest.approx(82 / 108)
    assert metrics.role_accuracy == pytest.approx(55 / 78)
    assert metrics.baseline_retention == 1.0
    assert metrics.false_rejection_rate == 0.0
    assert metrics.insufficient_recall == 0.0


def test_campaign_v2_exposes_recall_gain_and_ambiguity_cost() -> None:
    counts = Counter()
    disposition_confusion = Counter()
    role_mismatch_count = 0

    for pull_request in PULL_REQUESTS:
        for outcome in _outcomes(pull_request)[1]:
            if outcome.observed_execution_state != "accepted":
                continue
            human = set(outcome.expected_selection_ids)
            model = set(outcome.observed_selection_ids)
            deterministic = set(outcome.deterministic_evidence_ids)
            counts.update(
                {
                    "human_selected": len(human),
                    "deterministic_selected": len(deterministic),
                    "deterministic_tp": len(deterministic & human),
                    "deterministic_fp": len(deterministic - human),
                    "deterministic_fn": len(human - deterministic),
                    "model_selected": len(model),
                    "model_tp": len(model & human),
                    "model_fp": len(model - human),
                    "model_fn": len(human - model),
                    "llm_only_tp": len((model - deterministic) & human),
                    "llm_only_fp": len((model - deterministic) - human),
                }
            )

            human_dispositions = {
                **{
                    evidence_id: "selected"
                    for evidence_id in outcome.expected_selection_ids
                },
                **{
                    evidence_id: "rejected"
                    for evidence_id in outcome.expected_rejected_ids
                },
                **{
                    evidence_id: "insufficient"
                    for evidence_id in outcome.expected_insufficient_ids
                },
            }
            model_dispositions = {
                **{
                    evidence_id: "selected"
                    for evidence_id in outcome.observed_selection_ids
                },
                **{
                    evidence_id: "rejected"
                    for evidence_id in outcome.observed_rejected_ids
                },
                **{
                    evidence_id: "insufficient"
                    for evidence_id in outcome.observed_insufficient_ids
                },
            }
            disposition_confusion.update(
                (
                    human_disposition,
                    model_dispositions[evidence_id],
                )
                for evidence_id, human_disposition in human_dispositions.items()
            )
            human_roles = {
                evidence_id: (role, semantic_role)
                for evidence_id, role, semantic_role in outcome.expected_roles
            }
            model_roles = {
                evidence_id: (role, semantic_role)
                for evidence_id, role, semantic_role in outcome.observed_roles
            }
            role_mismatch_count += sum(
                human_roles[evidence_id] != model_roles[evidence_id]
                for evidence_id in human & model
            )

    assert counts == {
        "human_selected": 78,
        "deterministic_selected": 31,
        "deterministic_tp": 30,
        "deterministic_fp": 1,
        "deterministic_fn": 48,
        "model_selected": 104,
        "model_tp": 78,
        "model_fp": 26,
        "model_fn": 0,
        "llm_only_tp": 48,
        "llm_only_fp": 25,
    }
    assert disposition_confusion == {
        ("selected", "selected"): 78,
        ("rejected", "selected"): 10,
        ("rejected", "rejected"): 4,
        ("insufficient", "selected"): 16,
    }
    assert role_mismatch_count == 23
