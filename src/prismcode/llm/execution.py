from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from prismcode.llm.admission import (
    ShadowAdmissionDiagnostic,
    ShadowCandidateAdmissionSet,
    admit_shadow_candidates,
)
from prismcode.llm.provider import ShadowEvidenceProvider
from prismcode.llm.runner import ShadowRunRecord, ShadowRunner
from prismcode.model.contracts import LLMShadowExecutionSummary, ReviewBrief


@dataclass(frozen=True)
class ShadowExecutionBundle:
    """Independent shadow result; never consumed by formal assessment."""

    summary: LLMShadowExecutionSummary
    runs: tuple[ShadowRunRecord, ...] = ()
    admission_diagnostics: tuple[ShadowAdmissionDiagnostic, ...] = ()
    schema_version: str = "llm_shadow_execution.v1"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def unavailable_shadow_execution() -> ShadowExecutionBundle:
    return ShadowExecutionBundle(
        summary=LLMShadowExecutionSummary(state="unavailable")
    )


def execute_shadow_admissions(
    admissions: ShadowCandidateAdmissionSet,
    provider: ShadowEvidenceProvider,
) -> ShadowExecutionBundle:
    runs: list[ShadowRunRecord] = []
    diagnostics: list[ShadowAdmissionDiagnostic] = []
    runner = ShadowRunner(provider)
    admitted_count = 0

    for admission in admissions.admissions:
        diagnostics.extend(admission.diagnostics)
        if admission.request is None:
            continue
        admitted_count += 1
        runs.append(
            runner.measure_selection(
                admission.request,
                deterministic_evidence_ids=admission.deterministic_evidence_ids,
            )
        )

    completed_count = sum(item.state == "accepted" for item in runs)
    failed_count = len(runs) - completed_count
    blocked = any(item.state == "blocked" for item in admissions.admissions)
    truncated = any(
        item.state == "ready_truncated" for item in admissions.admissions
    )
    if admitted_count and failed_count == admitted_count:
        state = "failed"
    elif failed_count or blocked or truncated:
        state = "partial"
    else:
        state = "completed"
    return ShadowExecutionBundle(
        summary=LLMShadowExecutionSummary(
            state=state,
            admitted_count=admitted_count,
            completed_count=completed_count,
            failed_count=failed_count,
        ),
        runs=tuple(runs),
        admission_diagnostics=tuple(diagnostics),
    )


def execute_shadow_review(
    brief: ReviewBrief,
    provider: ShadowEvidenceProvider,
) -> ShadowExecutionBundle:
    """Run the canonical admission and measurement pipeline for one brief."""

    admissions = admit_shadow_candidates(
        brief.transformation_contract,
        brief.observed_transformation,
        brief.evidence_catalog,
        brief.transformation_alignment,
        brief.transformation_assessment,
    )
    return execute_shadow_admissions(admissions, provider)


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
