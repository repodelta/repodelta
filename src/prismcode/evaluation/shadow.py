from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from prismcode.llm.contracts import ShadowEvidenceRole, ShadowSemanticRole
from prismcode.llm.execution import (
    ShadowExecutionBundle,
    ShadowExecutionState,
)


ShadowEvaluationProfile = Literal["replay", "live", "none"]


@dataclass(frozen=True)
class ExpectedShadowSelection:
    evidence_id: str
    role: ShadowEvidenceRole
    semantic_role: ShadowSemanticRole


@dataclass(frozen=True)
class ExpectedShadowOutcome:
    claim_id: str
    execution_state: ShadowExecutionState
    selections: tuple[ExpectedShadowSelection, ...] = ()
    unresolved_surfaces: tuple[str, ...] = ()
    diagnostic_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ShadowOutcomeEvaluation:
    case_id: str
    claim_id: str
    profile: ShadowEvaluationProfile
    expected_execution_state: ShadowExecutionState
    observed_execution_state: str | None
    expected_selection_ids: tuple[str, ...]
    observed_selection_ids: tuple[str, ...]
    missing_selection_ids: tuple[str, ...]
    unexpected_selection_ids: tuple[str, ...]
    expected_roles: tuple[tuple[str, str, str], ...]
    observed_roles: tuple[tuple[str, str, str], ...]
    expected_unresolved_surfaces: tuple[str, ...]
    observed_unresolved_surfaces: tuple[str, ...]
    expected_diagnostic_codes: tuple[str, ...]
    observed_diagnostic_codes: tuple[str, ...]
    deterministic_evidence_ids: tuple[str, ...]
    input_tokens: int
    output_tokens: int
    duration_ms: float

    @property
    def state_matched(self) -> bool:
        return self.observed_execution_state == self.expected_execution_state

    @property
    def diagnostics_matched(self) -> bool:
        return set(self.observed_diagnostic_codes) == set(
            self.expected_diagnostic_codes
        )


@dataclass(frozen=True)
class ShadowEvaluationMetrics:
    outcome_count: int
    selection_precision: float
    selection_recall: float
    role_accuracy: float
    baseline_retention: float
    unresolved_precision: float
    unresolved_recall: float
    state_accuracy: float
    diagnostic_accuracy: float
    replay_count: int
    live_count: int
    total_input_tokens: int
    total_output_tokens: int
    total_duration_ms: float


@dataclass(frozen=True)
class ShadowEvaluationThresholds:
    selection_precision: float = 0.0
    selection_recall: float = 0.0
    role_accuracy: float = 0.0
    baseline_retention: float = 0.0
    unresolved_precision: float = 0.0
    unresolved_recall: float = 0.0
    state_accuracy: float = 0.0
    diagnostic_accuracy: float = 0.0


def evaluate_shadow_outcomes(
    case_id: str,
    expected: tuple[ExpectedShadowOutcome, ...],
    bundle: ShadowExecutionBundle,
) -> tuple[ShadowOutcomeEvaluation, ...]:
    observed = {item.claim_id: item for item in bundle.observations}
    results = []
    for item in expected:
        observation = observed.get(item.claim_id)
        run = observation.run if observation is not None else None
        selection = run.selection if run is not None else None
        selected_items = selection.selections if selection is not None else ()
        expected_roles = tuple(
            (selected.evidence_id, selected.role, selected.semantic_role)
            for selected in item.selections
        )
        observed_roles = tuple(
            (selected.evidence_id, selected.role, selected.semantic_role)
            for selected in selected_items
        )
        expected_ids = tuple(selected[0] for selected in expected_roles)
        observed_ids = tuple(selected[0] for selected in observed_roles)
        diagnostics = (
            tuple(value.code for value in observation.diagnostics)
            if observation is not None
            else ()
        )
        if run is not None:
            diagnostics = (*diagnostics, *(value.code for value in run.diagnostics))
        results.append(
            ShadowOutcomeEvaluation(
                case_id=case_id,
                claim_id=item.claim_id,
                profile=_profile(run.provider_id if run is not None else None),
                expected_execution_state=item.execution_state,
                observed_execution_state=(
                    observation.execution_state if observation is not None else None
                ),
                expected_selection_ids=expected_ids,
                observed_selection_ids=observed_ids,
                missing_selection_ids=tuple(
                    value for value in expected_ids if value not in observed_ids
                ),
                unexpected_selection_ids=tuple(
                    value for value in observed_ids if value not in expected_ids
                ),
                expected_roles=expected_roles,
                observed_roles=observed_roles,
                expected_unresolved_surfaces=item.unresolved_surfaces,
                observed_unresolved_surfaces=(
                    selection.unresolved_surfaces if selection is not None else ()
                ),
                expected_diagnostic_codes=item.diagnostic_codes,
                observed_diagnostic_codes=diagnostics,
                deterministic_evidence_ids=(
                    observation.deterministic_evidence_ids
                    if observation is not None
                    else ()
                ),
                input_tokens=(run.input_tokens or 0) if run is not None else 0,
                output_tokens=(run.output_tokens or 0) if run is not None else 0,
                duration_ms=run.duration_ms if run is not None else 0.0,
            )
        )
    return tuple(results)


def shadow_metrics(
    outcomes: tuple[ShadowOutcomeEvaluation, ...],
) -> ShadowEvaluationMetrics:
    expected_ids = {
        (item.case_id, item.claim_id, evidence_id)
        for item in outcomes
        for evidence_id in item.expected_selection_ids
    }
    observed_ids = {
        (item.case_id, item.claim_id, evidence_id)
        for item in outcomes
        for evidence_id in item.observed_selection_ids
    }
    shared_ids = expected_ids & observed_ids
    expected_roles = {
        (item.case_id, item.claim_id, *role)
        for item in outcomes
        for role in item.expected_roles
    }
    observed_roles = {
        (item.case_id, item.claim_id, *role)
        for item in outcomes
        for role in item.observed_roles
    }
    relevant_baseline = {
        (item.case_id, item.claim_id, evidence_id)
        for item in outcomes
        for evidence_id in item.deterministic_evidence_ids
        if evidence_id in item.expected_selection_ids
    }
    expected_unresolved = {
        (item.case_id, item.claim_id, value)
        for item in outcomes
        for value in item.expected_unresolved_surfaces
    }
    observed_unresolved = {
        (item.case_id, item.claim_id, value)
        for item in outcomes
        for value in item.observed_unresolved_surfaces
    }
    return ShadowEvaluationMetrics(
        outcome_count=len(outcomes),
        selection_precision=_ratio(len(shared_ids), len(observed_ids)),
        selection_recall=_ratio(len(shared_ids), len(expected_ids)),
        role_accuracy=_ratio(
            len(expected_roles & observed_roles),
            len(expected_roles),
        ),
        baseline_retention=_ratio(
            len(relevant_baseline & observed_ids),
            len(relevant_baseline),
        ),
        unresolved_precision=_ratio(
            len(expected_unresolved & observed_unresolved),
            len(observed_unresolved),
        ),
        unresolved_recall=_ratio(
            len(expected_unresolved & observed_unresolved),
            len(expected_unresolved),
        ),
        state_accuracy=_ratio(
            sum(item.state_matched for item in outcomes),
            len(outcomes),
        ),
        diagnostic_accuracy=_ratio(
            sum(item.diagnostics_matched for item in outcomes),
            len(outcomes),
        ),
        replay_count=sum(item.profile == "replay" for item in outcomes),
        live_count=sum(item.profile == "live" for item in outcomes),
        total_input_tokens=sum(item.input_tokens for item in outcomes),
        total_output_tokens=sum(item.output_tokens for item in outcomes),
        total_duration_ms=sum(item.duration_ms for item in outcomes),
    )


def shadow_diagnostics(
    outcomes: tuple[ShadowOutcomeEvaluation, ...],
) -> tuple[str, ...]:
    diagnostics = []
    for item in outcomes:
        if not item.state_matched:
            diagnostics.append(
                "shadow_state_mismatch: "
                f"case={item.case_id} claim={item.claim_id} "
                f"expected={item.expected_execution_state} "
                f"observed={item.observed_execution_state or 'missing'}"
            )
        if item.missing_selection_ids or item.unexpected_selection_ids:
            diagnostics.append(
                "shadow_selection_mismatch: "
                f"case={item.case_id} claim={item.claim_id} "
                f"missing={','.join(item.missing_selection_ids) or 'none'} "
                f"unexpected={','.join(item.unexpected_selection_ids) or 'none'}"
            )
        if set(item.expected_roles) != set(item.observed_roles):
            diagnostics.append(
                f"shadow_role_mismatch: case={item.case_id} claim={item.claim_id}"
            )
        if set(item.expected_unresolved_surfaces) != set(
            item.observed_unresolved_surfaces
        ):
            diagnostics.append(
                "shadow_unresolved_mismatch: "
                f"case={item.case_id} claim={item.claim_id}"
            )
        if not item.diagnostics_matched:
            diagnostics.append(
                "shadow_diagnostic_mismatch: "
                f"case={item.case_id} claim={item.claim_id}"
            )
    return tuple(diagnostics)


def shadow_threshold_diagnostics(
    metrics: ShadowEvaluationMetrics,
    thresholds: ShadowEvaluationThresholds,
) -> tuple[str, ...]:
    return tuple(
        "threshold_failed: "
        f"shadow_{name}={observed:.4f} is below {required:.4f}"
        for name, observed, required in (
            (
                "selection_precision",
                metrics.selection_precision,
                thresholds.selection_precision,
            ),
            ("selection_recall", metrics.selection_recall, thresholds.selection_recall),
            ("role_accuracy", metrics.role_accuracy, thresholds.role_accuracy),
            (
                "baseline_retention",
                metrics.baseline_retention,
                thresholds.baseline_retention,
            ),
            (
                "unresolved_precision",
                metrics.unresolved_precision,
                thresholds.unresolved_precision,
            ),
            ("unresolved_recall", metrics.unresolved_recall, thresholds.unresolved_recall),
            ("state_accuracy", metrics.state_accuracy, thresholds.state_accuracy),
            ("diagnostic_accuracy", metrics.diagnostic_accuracy, thresholds.diagnostic_accuracy),
        )
        if observed < required
    )


def _profile(provider_id: str | None) -> ShadowEvaluationProfile:
    if provider_id is None:
        return "none"
    return "replay" if provider_id == "replay" else "live"


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0
