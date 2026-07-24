from __future__ import annotations

from typing import Protocol

from .contracts import (
    AnalysisInput,
    EvidenceCatalog,
    EvidenceHint,
    ImplementationAssessment,
    Requirement,
    RequirementAssessment,
    ReviewBrief,
    ReviewSourcePacket,
    SourceRef,
    VerificationAssessment,
)
from .criteria import extract_review_semantics
from .binding import build_deterministic_evidence_hints
from .candidate_binding import build_candidate_bindings
from .evidence_graph import build_evidence_catalog


class ReviewAnalyzer(Protocol):
    def analyze(self, analysis_input: AnalysisInput) -> ReviewBrief: ...


class DeterministicAnalyzer:
    """The only layer allowed to turn source facts and hints into assessments."""

    def analyze(self, analysis_input: AnalysisInput) -> ReviewBrief:
        packet = analysis_input.packet
        packet.validate_consistency()
        pr_record = next(
            (r for r in packet.source_records if r.kind == "pull_request"),
            None,
        )
        pr_body = pr_record.body if pr_record else ""
        issue_records = tuple(
            r for r in packet.source_records if r.kind in {"linked_issue", "ticket"}
        )
        issue_record = issue_records[0] if len(issue_records) == 1 else None
        semantics = extract_review_semantics(
            issue_body=issue_record.body if issue_record else None,
            issue_source=(
                SourceRef(label="linked issue", url=issue_record.url)
                if issue_record
                else None
            ),
            pr_body=pr_body,
            pr_source=SourceRef(
                label="pull request description",
                url=(pr_record.url if pr_record else None) or packet.source_url,
            ),
            pr_title=packet.title,
        )
        requirements = analysis_input.requirements or semantics.obligations
        supplied = (
            analysis_input.evidence_catalog.items
            if analysis_input.evidence_catalog is not None
            else ()
        )
        evidence_catalog = build_evidence_catalog(
            packet,
            analysis_input.structural_graph,
            supplied=supplied,
        )
        provided_hints = analysis_input.evidence_hints or build_deterministic_evidence_hints(
            requirements,
            packet,
            evidence_catalog,
        )
        _validate_hint_evidence(provided_hints, evidence_catalog)
        hints = {hint.requirement_id: hint for hint in provided_hints}
        deliverables = tuple(item for item in requirements if item.kind != "guardrail")
        guardrails = tuple(item for item in requirements if item.kind == "guardrail")
        candidate_bindings = build_candidate_bindings(
            requirements=requirements,
            objectives=semantics.objectives,
            claims=semantics.claims,
            evidence_catalog=evidence_catalog,
        )
        assessments = tuple(
            self._assess(
                requirement,
                hints.get(requirement.id),
                packet=packet,
                evidence_catalog=evidence_catalog,
            )
            for requirement in deliverables
        )
        return ReviewBrief(
            packet=packet,
            intent=semantics.intent,
            assessments=assessments,
            guardrails=guardrails,
            objectives=semantics.objectives,
            claims=semantics.claims,
            structural_graph=analysis_input.structural_graph,
            evidence_catalog=evidence_catalog,
            candidate_bindings=candidate_bindings,
        )

    @staticmethod
    def _assess(
        requirement: Requirement,
        hint: EvidenceHint | None,
        *,
        packet: ReviewSourcePacket,
        evidence_catalog: EvidenceCatalog,
    ) -> RequirementAssessment:
        if hint is None:
            return RequirementAssessment(
                requirement=requirement,
                implementation=ImplementationAssessment(status="not_observed"),
                verification=VerificationAssessment(
                    status="manual_required" if requirement.kind == "manual_acceptance" else "not_observed"
                ),
                gaps=("No requirement-specific implementation or verification evidence has been established.",),
            )

        registry = evidence_catalog.by_id()
        implementation_evidence = tuple(
            registry[evidence_id]
            for evidence_id in hint.implementation_evidence_ids
        )
        implementation_status = (
            "observed" if implementation_evidence else "not_observed"
        )
        observations = [
            registry[evidence_id]
            for evidence_id in hint.verification_evidence_ids
        ]
        current = [
            item
            for item in observations
            if not item.metadata.get("head_sha")
            or item.metadata.get("head_sha") == packet.head_sha
        ]
        verification_status = "not_observed"
        if observations and not current:
            verification_status = "stale"
        elif any(
            str(item.metadata.get("status", "")).casefold()
            in {"queued", "pending", "in_progress"}
            for item in current
        ):
            verification_status = "pending"
        elif any(
            str(item.metadata.get("conclusion", "")).casefold()
            in {"failure", "error", "cancelled", "timed_out"}
            for item in current
        ):
            verification_status = "failed"
        elif (
            any(
                str(item.metadata.get("conclusion", "")).casefold() == "success"
                for item in current
            )
            and hint.assertion_coverage == "adequate"
        ):
            verification_status = "passed"
        verification_evidence = tuple(observations)
        gaps = list(hint.gaps)
        if not observations:
            gaps.append("No requirement-specific CI, check, workflow, or runtime execution was observed.")
        elif hint.assertion_coverage != "adequate":
            gaps.append("Assertion coverage for this requirement is not explicitly established.")
        return RequirementAssessment(
            requirement=requirement,
            implementation=ImplementationAssessment(
                status=implementation_status,
                evidence=implementation_evidence,
            ),
            verification=VerificationAssessment(
                status=verification_status,
                evidence=verification_evidence,
            ),
            gaps=tuple(dict.fromkeys(gaps)),
        )


def _validate_hint_evidence(
    hints: tuple[EvidenceHint, ...], catalog: EvidenceCatalog
) -> None:
    known = set(catalog.by_id())
    referenced = {
        evidence_id
        for hint in hints
        for evidence_id in (
            *hint.implementation_evidence_ids,
            *hint.verification_evidence_ids,
        )
    }
    unknown = sorted(referenced - known)
    if unknown:
        raise ValueError(
            "evidence hints reference unknown canonical evidence IDs: "
            + ", ".join(unknown)
        )
