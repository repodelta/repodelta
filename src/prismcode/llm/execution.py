from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from prismcode.llm.admission import (
    ShadowAdmissionDiagnostic,
    ShadowAdmissionPolicy,
    ShadowAdmissionState,
    ShadowCandidateAdmission,
    ShadowCandidateAdmissionSet,
    admit_shadow_candidates,
)
from prismcode.llm.contracts import ShadowEvidenceRequest
from prismcode.llm.provider import ShadowEvidenceProvider
from prismcode.llm.runner import ShadowRunRecord, ShadowRunner
from prismcode.model.contracts import LLMShadowExecutionSummary, ReviewBrief


@dataclass(frozen=True)
class ShadowExecutionBundle:
    """Independent shadow result; never consumed by formal assessment."""

    summary: LLMShadowExecutionSummary
    observations: tuple["ShadowExecutionObservation", ...] = ()
    schema_version: str = "llm_shadow_execution.v2"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def __post_init__(self) -> None:
        claim_ids = tuple(item.claim_id for item in self.observations)
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("shadow observations must contain each claim at most once")
        if self.summary.state == "unavailable":
            if self.observations:
                raise ValueError("unavailable shadow execution cannot carry observations")
            return
        expected = _summary_for_observations(self.observations)
        if self.summary != LLMShadowExecutionSummary(
            **{
                **asdict(expected),
                "artifact_written": self.summary.artifact_written,
            }
        ):
            raise ValueError("shadow execution summary must derive from observations")


@dataclass(frozen=True)
class ShadowExecutionPolicy:
    max_requests: int = 3

    def __post_init__(self) -> None:
        if not 1 <= self.max_requests <= 100:
            raise ValueError("max_requests must be between 1 and 100")


ShadowExecutionState = Literal[
    "accepted",
    "invalid_output",
    "provider_error",
    "deferred",
    "blocked",
    "empty",
]


@dataclass(frozen=True)
class ShadowExecutionObservation:
    """Canonical audit record for one claim's admission and execution fate."""

    claim_id: str
    admission_state: ShadowAdmissionState
    execution_state: ShadowExecutionState
    eligible_count: int
    deterministic_evidence_ids: tuple[str, ...] = ()
    request: ShadowEvidenceRequest | None = None
    run: ShadowRunRecord | None = None
    diagnostics: tuple[ShadowAdmissionDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        executed = self.execution_state in {
            "accepted",
            "invalid_output",
            "provider_error",
        }
        if (self.run is not None) != executed:
            raise ValueError("only executed shadow observations carry a run")
        if (self.request is not None) != (
            executed or self.execution_state == "deferred"
        ):
            raise ValueError("only admitted shadow observations carry a request")
        if self.request is not None and self.request.subject_id != self.claim_id:
            raise ValueError("shadow observation request must match its claim")
        if self.run is not None and self.run.subject_id != self.claim_id:
            raise ValueError("shadow observation run must match its claim")
        if self.admission_state in {"ready", "ready_truncated"} and (
            self.execution_state in {"blocked", "empty"}
        ):
            raise ValueError("ready admission must be executed or deferred")
        if self.admission_state in {"blocked", "empty"} and (
            self.execution_state != self.admission_state
        ):
            raise ValueError("non-ready admission must preserve its execution fate")


def unavailable_shadow_execution() -> ShadowExecutionBundle:
    return ShadowExecutionBundle(
        summary=LLMShadowExecutionSummary(state="unavailable")
    )


def execute_shadow_admissions(
    admissions: ShadowCandidateAdmissionSet,
    provider: ShadowEvidenceProvider,
    *,
    policy: ShadowExecutionPolicy = ShadowExecutionPolicy(),
) -> ShadowExecutionBundle:
    observations: list[ShadowExecutionObservation] = []
    runner = ShadowRunner(provider)
    ready = tuple(item for item in admissions.admissions if item.request is not None)
    selected_claim_ids = {
        item.claim_id for item in ready[: policy.max_requests]
    }

    for admission in admissions.admissions:
        if admission.request is None:
            observations.append(
                _observation(
                    admission,
                    execution_state=(
                        "blocked" if admission.state == "blocked" else "empty"
                    ),
                )
            )
            continue
        if admission.claim_id not in selected_claim_ids:
            observations.append(
                _observation(
                    admission,
                    execution_state="deferred",
                    diagnostics=(
                        *admission.diagnostics,
                        ShadowAdmissionDiagnostic(
                            code="shadow_execution_budget_deferred",
                            message=(
                                "Admitted shadow request was deferred by the "
                                f"review safety limit of {policy.max_requests}."
                            ),
                        ),
                    ),
                )
            )
            continue
        run = runner.measure_selection(
            admission.request,
            deterministic_evidence_ids=admission.deterministic_evidence_ids,
        )
        observations.append(
            _observation(admission, execution_state=run.state, run=run)
        )

    canonical_observations = tuple(observations)
    if tuple(item.claim_id for item in canonical_observations) != tuple(
        item.claim_id for item in admissions.admissions
    ):
        raise ValueError("shadow execution must preserve every admission in order")
    return ShadowExecutionBundle(
        summary=_summary_for_observations(canonical_observations),
        observations=canonical_observations,
    )


def _observation(
    admission: ShadowCandidateAdmission,
    *,
    execution_state: ShadowExecutionState,
    run: ShadowRunRecord | None = None,
    diagnostics: tuple[ShadowAdmissionDiagnostic, ...] | None = None,
) -> ShadowExecutionObservation:
    return ShadowExecutionObservation(
        claim_id=admission.claim_id,
        admission_state=admission.state,
        execution_state=execution_state,
        eligible_count=admission.eligible_count,
        deterministic_evidence_ids=admission.deterministic_evidence_ids,
        request=admission.request,
        run=run,
        diagnostics=(
            admission.diagnostics if diagnostics is None else diagnostics
        ),
    )


def _summary_for_observations(
    observations: tuple[ShadowExecutionObservation, ...],
) -> LLMShadowExecutionSummary:
    admitted_count = sum(item.request is not None for item in observations)
    completed_count = sum(
        item.execution_state == "accepted" for item in observations
    )
    failed_count = sum(
        item.execution_state in {"invalid_output", "provider_error"}
        for item in observations
    )
    deferred_count = sum(
        item.execution_state == "deferred" for item in observations
    )
    blocked = any(item.execution_state == "blocked" for item in observations)
    truncated = any(
        item.admission_state == "ready_truncated" for item in observations
    )
    if admitted_count and failed_count == admitted_count:
        state = "failed"
    elif failed_count or blocked or truncated or deferred_count:
        state = "partial"
    else:
        state = "completed"
    return LLMShadowExecutionSummary(
        state=state,
        admitted_count=admitted_count,
        completed_count=completed_count,
        failed_count=failed_count,
        deferred_count=deferred_count,
    )


def execute_shadow_review(
    brief: ReviewBrief,
    provider: ShadowEvidenceProvider,
    *,
    admission_policy: ShadowAdmissionPolicy = ShadowAdmissionPolicy(
        max_candidates=40
    ),
    policy: ShadowExecutionPolicy = ShadowExecutionPolicy(),
) -> ShadowExecutionBundle:
    """Run the canonical admission and measurement pipeline for one brief."""

    admissions = admit_shadow_candidates(
        brief.transformation_contract,
        brief.observed_transformation,
        brief.evidence_catalog,
        brief.transformation_alignment,
        brief.transformation_assessment,
        policy=admission_policy,
    )
    return execute_shadow_admissions(admissions, provider, policy=policy)


def write_shadow_execution(
    bundle: ShadowExecutionBundle, output: str | Path
) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(bundle.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
