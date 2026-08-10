from pathlib import Path

import pytest

from repodelta.evaluation.shadow import (
    ExpectedShadowOutcome,
    HumanShadowLabelSet,
    evaluate_shadow_outcomes,
    load_human_shadow_labels,
    shadow_metrics,
)
from repodelta.llm.execution import load_shadow_execution


CORPUS = Path("fixtures/llm-shadow/campaign-v1")


def _recorded_expectations(bundle):
    return tuple(
        ExpectedShadowOutcome(
            claim_id=observation.claim_id,
            execution_state=observation.execution_state,
            diagnostic_codes=(
                *(item.code for item in observation.diagnostics),
                *(
                    item.code
                    for item in (
                        observation.run.diagnostics
                        if observation.run is not None
                        else ()
                    )
                ),
            ),
        )
        for observation in bundle.observations
    )


def _outcomes(pr_number: int, *, labeled: bool):
    bundle = load_shadow_execution(
        CORPUS / f"pr-{pr_number}.observation.json"
    )
    labels = (
        load_human_shadow_labels(
            CORPUS / f"pr-{pr_number}.human-labels.json", bundle
        )
        if labeled
        else HumanShadowLabelSet(labels=())
    )
    return evaluate_shadow_outcomes(
        f"pr-{pr_number}",
        _recorded_expectations(bundle),
        labels,
        bundle,
    )


def test_campaign_v1_preserves_blinded_labels_and_recorded_metrics() -> None:
    outcomes = (
        *_outcomes(203, labeled=True),
        *_outcomes(208, labeled=True),
        *_outcomes(215, labeled=False),
    )

    metrics = shadow_metrics(outcomes)

    assert metrics.outcome_count == 10
    assert metrics.human_labeled_outcome_count == 6
    assert metrics.candidate_label_count == 16
    assert metrics.selection_precision == 1.0
    assert metrics.selection_recall == 0.75
    assert metrics.role_accuracy == 0.5
    assert metrics.disposition_accuracy == 0.75
    assert metrics.false_rejection_rate == 0.0
    assert metrics.baseline_retention == 0.6
    # Provider-error runs intentionally carry no provider identity and are
    # therefore kept out of the evaluator's live-response count.
    assert metrics.live_count == 5
    assert metrics.total_input_tokens == 8_852
    assert metrics.total_output_tokens == 1_654
    assert metrics.total_duration_ms == pytest.approx(44_592.78, abs=0.01)
    assert metrics.execution_policy_ids == (
        "shadow-policy:f5d9af55c704e40e04a6",
    )


def test_campaign_v1_executed_labels_isolate_semantic_selection_quality() -> None:
    labeled = (*_outcomes(203, labeled=True), *_outcomes(208, labeled=True))
    accepted = tuple(
        outcome
        for outcome in labeled
        if outcome.observed_execution_state == "accepted"
    )

    metrics = shadow_metrics(accepted)

    assert metrics.human_labeled_outcome_count == 5
    assert metrics.candidate_label_count == 12
    assert metrics.selection_precision == 1.0
    assert metrics.selection_recall == 1.0
    assert metrics.disposition_accuracy == 1.0
    assert metrics.role_accuracy == pytest.approx(8 / 12)
    assert metrics.false_rejection_rate == 0.0


def test_campaign_v1_keeps_operational_failures_distinct_from_disagreement() -> None:
    outcomes = _outcomes(215, labeled=False)

    assert tuple(item.observed_execution_state for item in outcomes) == (
        "provider_error",
        "provider_error",
        "provider_error",
        "deferred",
    )
    assert all(not item.human_labeled for item in outcomes)
    assert all(not item.observed_selection_ids for item in outcomes)
