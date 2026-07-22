from __future__ import annotations

from typing import Protocol

from .contracts import (
    AnalysisInput,
    EvidenceHint,
    ImplementationAssessment,
    Requirement,
    RequirementAssessment,
    ReviewBrief,
    SourceRef,
    VerificationAssessment,
)
from .criteria import extract_intent, extract_requirements


class ReviewAnalyzer(Protocol):
    def analyze(self, analysis_input: AnalysisInput) -> ReviewBrief: ...


class DeterministicAnalyzer:
    """The only layer allowed to turn source facts and hints into assessments."""

    def analyze(self, analysis_input: AnalysisInput) -> ReviewBrief:
        packet = analysis_input.packet
        packet.validate_consistency()
        pr_body = next(
            (record.body for record in packet.source_records if record.kind == "pull_request"),
            "",
        )
        requirements = analysis_input.requirements or extract_requirements(
            pr_body,
            source=SourceRef(label="pull request description", url=packet.source_url),
        )
        if not requirements:
            requirements = (
                Requirement(
                    id="R1",
                    text=packet.title,
                    sources=(SourceRef(label="pull request title", url=packet.source_url),),
                ),
            )
        hints = {hint.requirement_id: hint for hint in analysis_input.evidence_hints}
        assessments = tuple(
            self._assess(requirement, hints.get(requirement.id))
            for requirement in requirements
        )
        return ReviewBrief(
            packet=packet,
            intent=extract_intent(pr_body, packet.title),
            assessments=assessments,
        )

    @staticmethod
    def _assess(requirement: Requirement, hint: EvidenceHint | None) -> RequirementAssessment:
        if hint is None:
            return RequirementAssessment(
                requirement=requirement,
                implementation=ImplementationAssessment(status="not_observed"),
                verification=VerificationAssessment(
                    status="manual_required" if requirement.kind == "manual_acceptance" else "not_observed"
                ),
                gaps=("No requirement-specific implementation or verification evidence has been established.",),
            )

        implementation_status = "observed" if hint.implementation else "not_observed"
        verification_status = {
            "success": "passed",
            "failure": "failed",
            "pending": "pending",
            "not_observed": "not_observed",
            "stale": "stale",
            "manual_required": "manual_required",
        }[hint.verification_outcome]
        return RequirementAssessment(
            requirement=requirement,
            implementation=ImplementationAssessment(
                status=implementation_status,
                evidence=hint.implementation,
            ),
            verification=VerificationAssessment(
                status=verification_status,
                evidence=hint.verification,
            ),
            gaps=hint.gaps,
        )
