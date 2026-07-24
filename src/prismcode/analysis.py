from __future__ import annotations

from typing import Protocol

from .contracts import (
    AnalysisInput,
    Requirement,
    ReviewBrief,
    SourceRef,
)
from .criteria import extract_review_semantics
from .candidate_binding import build_candidate_bindings
from .evidence_graph import build_evidence_catalog


class ReviewAnalyzer(Protocol):
    def analyze(self, analysis_input: AnalysisInput) -> ReviewBrief: ...


class DeterministicAnalyzer:
    """Build one conclusion-free requirement-to-evidence candidate graph."""

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
        evidence_catalog = build_evidence_catalog(
            packet,
            analysis_input.structural_graph,
            supplied=analysis_input.supplied_evidence,
        )
        deliverables = tuple(item for item in requirements if item.kind != "guardrail")
        guardrails = tuple(item for item in requirements if item.kind == "guardrail")
        candidate_bindings = build_candidate_bindings(
            requirements=requirements,
            objectives=semantics.objectives,
            scope=semantics.scope,
            claims=semantics.claims,
            evidence_catalog=evidence_catalog,
        )
        return ReviewBrief(
            packet=packet,
            intent=semantics.intent,
            requirements=deliverables,
            guardrails=guardrails,
            objectives=semantics.objectives,
            scope=semantics.scope,
            claims=semantics.claims,
            structural_graph=analysis_input.structural_graph,
            evidence_catalog=evidence_catalog,
            candidate_bindings=candidate_bindings,
        )
