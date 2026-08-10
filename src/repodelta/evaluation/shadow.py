from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping

from repodelta.llm.contracts import (
    ShadowEvidenceRequest,
    ShadowEvidenceSelection,
    parse_shadow_selection,
)
from repodelta.llm.execution import (
    ShadowExecutionBundle,
    ShadowExecutionState,
)
from repodelta.llm.labeling import ShadowLabelingPacket


ShadowEvaluationProfile = Literal["replay", "live", "none"]
HUMAN_SHADOW_LABEL_SCHEMA_VERSION = "llm_shadow_human_labels.v1"


@dataclass(frozen=True)
class HumanShadowLabel:
    claim_id: str
    rubric_version: str
    selection: ShadowEvidenceSelection
    authority: Literal["human_review"] = "human_review"


@dataclass(frozen=True)
class HumanShadowLabelSet:
    labels: tuple[HumanShadowLabel, ...]
    schema_version: str = HUMAN_SHADOW_LABEL_SCHEMA_VERSION

    def by_claim_id(self) -> dict[str, HumanShadowLabel]:
        return {item.claim_id: item for item in self.labels}


@dataclass(frozen=True)
class ExpectedShadowOutcome:
    claim_id: str
    execution_state: ShadowExecutionState
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
    expected_rejected_ids: tuple[str, ...]
    observed_rejected_ids: tuple[str, ...]
    expected_insufficient_ids: tuple[str, ...]
    observed_insufficient_ids: tuple[str, ...]
    expected_unresolved_surfaces: tuple[str, ...]
    observed_unresolved_surfaces: tuple[str, ...]
    expected_diagnostic_codes: tuple[str, ...]
    observed_diagnostic_codes: tuple[str, ...]
    deterministic_evidence_ids: tuple[str, ...]
    input_tokens: int
    output_tokens: int
    duration_ms: float
    execution_policy_id: str | None
    label_authority: str | None = None
    rubric_version: str | None = None

    @property
    def human_labeled(self) -> bool:
        return self.label_authority == "human_review"

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
    human_labeled_outcome_count: int
    candidate_label_count: int
    selection_precision: float
    selection_recall: float
    role_accuracy: float
    disposition_accuracy: float
    false_rejection_rate: float
    insufficient_recall: float
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
    execution_policy_ids: tuple[str, ...]


@dataclass(frozen=True)
class ShadowEvaluationThresholds:
    selection_precision: float = 0.0
    selection_recall: float = 0.0
    role_accuracy: float = 0.0
    disposition_accuracy: float = 0.0
    max_false_rejection_rate: float = 1.0
    insufficient_recall: float = 0.0
    baseline_retention: float = 0.0
    unresolved_precision: float = 0.0
    unresolved_recall: float = 0.0
    state_accuracy: float = 0.0
    diagnostic_accuracy: float = 0.0


def load_human_shadow_labels(
    path: str | Path,
    bundle: ShadowExecutionBundle,
) -> HumanShadowLabelSet:
    """Validate independent human labels against recorded bounded requests."""

    return _load_human_shadow_labels(
        path,
        {
            item.claim_id: item.request
            for item in bundle.observations
            if item.request is not None
        },
        require_complete=False,
    )


def load_human_shadow_labels_from_packet(
    path: str | Path,
    packet: ShadowLabelingPacket,
) -> HumanShadowLabelSet:
    """Validate a complete label set before any provider execution."""

    return _load_human_shadow_labels(
        path,
        packet.requests_by_claim_id,
        require_complete=True,
    )


def _load_human_shadow_labels(
    path: str | Path,
    requests: Mapping[str, ShadowEvidenceRequest],
    *,
    require_complete: bool,
) -> HumanShadowLabelSet:

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    unexpected_fields = set(raw) - {
        "schema_version",
        "authority",
        "rubric_version",
        "labels",
    }
    if unexpected_fields:
        raise ValueError(
            "human shadow labels contain unsupported fields: "
            + ", ".join(sorted(unexpected_fields))
        )
    if raw.get("schema_version") != HUMAN_SHADOW_LABEL_SCHEMA_VERSION:
        raise ValueError(
            "human shadow labels must use schema_version "
            f"{HUMAN_SHADOW_LABEL_SCHEMA_VERSION}"
        )
    if raw.get("authority") != "human_review":
        raise ValueError("human shadow labels require human_review authority")
    rubric_version = raw.get("rubric_version")
    if not isinstance(rubric_version, str) or not rubric_version.strip():
        raise ValueError("human shadow labels require a rubric_version")
    raw_labels = raw.get("labels")
    if not isinstance(raw_labels, list) or not raw_labels:
        raise ValueError("human shadow labels require a non-empty labels list")

    labels = []
    seen_claim_ids: set[str] = set()
    for index, raw_label in enumerate(raw_labels):
        if not isinstance(raw_label, Mapping):
            raise ValueError(f"human shadow label {index} must be an object")
        unexpected_label_fields = set(raw_label) - {"claim_id", "response"}
        if unexpected_label_fields:
            raise ValueError(
                f"human shadow label {index} contains unsupported fields: "
                + ", ".join(sorted(unexpected_label_fields))
            )
        claim_id = raw_label.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id:
            raise ValueError(f"human shadow label {index} requires claim_id")
        if claim_id in seen_claim_ids:
            raise ValueError(f"duplicate human shadow label claim_id: {claim_id}")
        request = requests.get(claim_id)
        if request is None:
            raise ValueError(
                f"human shadow label {claim_id} has no recorded bounded request"
            )
        response = raw_label.get("response")
        if not isinstance(response, Mapping):
            raise ValueError(
                f"human shadow label {claim_id} requires a response object"
            )
        validation = parse_shadow_selection(response, request)
        if not validation.accepted or validation.selection is None:
            codes = ", ".join(item.code for item in validation.diagnostics)
            raise ValueError(
                f"invalid human shadow label {claim_id}: {codes or 'unknown'}"
            )
        labels.append(
            HumanShadowLabel(
                claim_id=claim_id,
                rubric_version=rubric_version,
                selection=validation.selection,
            )
        )
        seen_claim_ids.add(claim_id)
    if require_complete and seen_claim_ids != set(requests):
        missing = set(requests) - seen_claim_ids
        raise ValueError(
            "pre-execution human shadow labels must cover every request; missing: "
            + ", ".join(sorted(missing))
        )
    return HumanShadowLabelSet(labels=tuple(labels))


def evaluate_shadow_outcomes(
    case_id: str,
    expected: tuple[ExpectedShadowOutcome, ...],
    human_labels: HumanShadowLabelSet,
    bundle: ShadowExecutionBundle,
) -> tuple[ShadowOutcomeEvaluation, ...]:
    observed = {item.claim_id: item for item in bundle.observations}
    labels = human_labels.by_claim_id()
    expected_claim_ids = {item.claim_id for item in expected}
    unexpected_labels = set(labels) - expected_claim_ids
    if unexpected_labels:
        raise ValueError(
            "human shadow labels reference undeclared expected claims: "
            + ", ".join(sorted(unexpected_labels))
        )
    results = []
    for item in expected:
        observation = observed.get(item.claim_id)
        run = observation.run if observation is not None else None
        selection = run.selection if run is not None else None
        human_label = labels.get(item.claim_id)
        expected_selection = (
            human_label.selection if human_label is not None else None
        )
        selected_items = selection.selections if selection is not None else ()
        expected_roles = tuple(
            (selected.evidence_id, selected.role, selected.semantic_role)
            for selected in (
                expected_selection.selections
                if expected_selection is not None
                else ()
            )
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
                expected_rejected_ids=(
                    expected_selection.rejected_evidence_ids
                    if expected_selection is not None
                    else ()
                ),
                observed_rejected_ids=(
                    selection.rejected_evidence_ids
                    if selection is not None
                    else ()
                ),
                expected_insufficient_ids=(
                    expected_selection.insufficient_evidence_ids
                    if expected_selection is not None
                    else ()
                ),
                observed_insufficient_ids=(
                    selection.insufficient_evidence_ids
                    if selection is not None
                    else ()
                ),
                expected_unresolved_surfaces=(
                    expected_selection.unresolved_surfaces
                    if expected_selection is not None
                    else ()
                ),
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
                execution_policy_id=(
                    run.execution_policy.identity if run is not None else None
                ),
                label_authority=(
                    human_label.authority if human_label is not None else None
                ),
                rubric_version=(
                    human_label.rubric_version
                    if human_label is not None
                    else None
                ),
            )
        )
    return tuple(results)


def shadow_metrics(
    outcomes: tuple[ShadowOutcomeEvaluation, ...],
) -> ShadowEvaluationMetrics:
    labeled = tuple(item for item in outcomes if item.human_labeled)
    expected_ids = {
        (item.case_id, item.claim_id, evidence_id)
        for item in labeled
        for evidence_id in item.expected_selection_ids
    }
    observed_ids = {
        (item.case_id, item.claim_id, evidence_id)
        for item in labeled
        for evidence_id in item.observed_selection_ids
    }
    shared_ids = expected_ids & observed_ids
    expected_roles = {
        (item.case_id, item.claim_id, *role)
        for item in labeled
        for role in item.expected_roles
    }
    observed_roles = {
        (item.case_id, item.claim_id, *role)
        for item in labeled
        for role in item.observed_roles
    }
    relevant_baseline = {
        (item.case_id, item.claim_id, evidence_id)
        for item in labeled
        for evidence_id in item.deterministic_evidence_ids
        if evidence_id in item.expected_selection_ids
    }
    expected_unresolved = {
        (item.case_id, item.claim_id, value)
        for item in labeled
        for value in item.expected_unresolved_surfaces
    }
    observed_unresolved = {
        (item.case_id, item.claim_id, value)
        for item in labeled
        for value in item.observed_unresolved_surfaces
    }
    expected_dispositions = {
        (item.case_id, item.claim_id, evidence_id): disposition
        for item in labeled
        for disposition, evidence_ids in (
            ("selected", item.expected_selection_ids),
            ("rejected", item.expected_rejected_ids),
            ("insufficient", item.expected_insufficient_ids),
        )
        for evidence_id in evidence_ids
    }
    observed_dispositions = {
        (item.case_id, item.claim_id, evidence_id): disposition
        for item in labeled
        for disposition, evidence_ids in (
            ("selected", item.observed_selection_ids),
            ("rejected", item.observed_rejected_ids),
            ("insufficient", item.observed_insufficient_ids),
        )
        for evidence_id in evidence_ids
    }
    matched_dispositions = sum(
        observed_dispositions.get(identity) == disposition
        for identity, disposition in expected_dispositions.items()
    )
    observed_rejected = {
        (item.case_id, item.claim_id, evidence_id)
        for item in labeled
        for evidence_id in item.observed_rejected_ids
    }
    expected_insufficient = {
        (item.case_id, item.claim_id, evidence_id)
        for item in labeled
        for evidence_id in item.expected_insufficient_ids
    }
    observed_insufficient = {
        (item.case_id, item.claim_id, evidence_id)
        for item in labeled
        for evidence_id in item.observed_insufficient_ids
    }
    return ShadowEvaluationMetrics(
        outcome_count=len(outcomes),
        human_labeled_outcome_count=len(labeled),
        candidate_label_count=len(expected_dispositions),
        selection_precision=_ratio(len(shared_ids), len(observed_ids)),
        selection_recall=_ratio(len(shared_ids), len(expected_ids)),
        role_accuracy=_ratio(
            len(expected_roles & observed_roles),
            len(expected_roles),
        ),
        disposition_accuracy=_ratio(
            matched_dispositions,
            len(expected_dispositions),
        ),
        false_rejection_rate=_ratio(
            len(expected_ids & observed_rejected),
            len(expected_ids),
        ),
        insufficient_recall=_ratio(
            len(expected_insufficient & observed_insufficient),
            len(expected_insufficient),
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
        execution_policy_ids=tuple(
            sorted(
                {
                    item.execution_policy_id
                    for item in outcomes
                    if item.execution_policy_id is not None
                }
            )
        ),
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
        if item.human_labeled and (
            item.missing_selection_ids or item.unexpected_selection_ids
        ):
            diagnostics.append(
                "shadow_selection_mismatch: "
                f"case={item.case_id} claim={item.claim_id} "
                f"missing={','.join(item.missing_selection_ids) or 'none'} "
                f"unexpected={','.join(item.unexpected_selection_ids) or 'none'}"
            )
        if item.human_labeled and set(item.expected_roles) != set(
            item.observed_roles
        ):
            diagnostics.append(
                f"shadow_role_mismatch: case={item.case_id} claim={item.claim_id}"
            )
        if item.human_labeled and set(item.expected_unresolved_surfaces) != set(
            item.observed_unresolved_surfaces
        ):
            diagnostics.append(
                "shadow_unresolved_mismatch: "
                f"case={item.case_id} claim={item.claim_id}"
            )
        if item.human_labeled and (
            set(item.expected_rejected_ids) != set(item.observed_rejected_ids)
            or set(item.expected_insufficient_ids)
            != set(item.observed_insufficient_ids)
        ):
            diagnostics.append(
                f"shadow_disposition_mismatch: case={item.case_id} "
                f"claim={item.claim_id}"
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
    diagnostics = [
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
                "disposition_accuracy",
                metrics.disposition_accuracy,
                thresholds.disposition_accuracy,
            ),
            (
                "insufficient_recall",
                metrics.insufficient_recall,
                thresholds.insufficient_recall,
            ),
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
    ]
    if metrics.false_rejection_rate > thresholds.max_false_rejection_rate:
        diagnostics.append(
            "threshold_failed: "
            f"shadow_false_rejection_rate={metrics.false_rejection_rate:.4f} "
            f"is above {thresholds.max_false_rejection_rate:.4f}"
        )
    semantic_thresholds = (
        thresholds.selection_precision,
        thresholds.selection_recall,
        thresholds.role_accuracy,
        thresholds.disposition_accuracy,
        thresholds.insufficient_recall,
        1.0 - thresholds.max_false_rejection_rate,
    )
    if metrics.human_labeled_outcome_count == 0 and any(
        value > 0 for value in semantic_thresholds
    ):
        diagnostics.append(
            "threshold_failed: no human-labeled shadow outcomes were evaluated"
        )
    return tuple(diagnostics)


def _profile(provider_id: str | None) -> ShadowEvaluationProfile:
    if provider_id is None:
        return "none"
    return "replay" if provider_id == "replay" else "live"


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0
