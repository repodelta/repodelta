from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from repodelta.model.contracts import Diagnostic, ReviewSourcePacket, SourceRef
from repodelta.semantics.criteria import ReviewSemantics, extract_review_semantics


_UNRESOLVED_GITHUB_ISSUE_CODES = frozenset(
    {
        "github_linked_issues_ambiguous",
        "github_linked_issues_unavailable",
    }
)


@dataclass(frozen=True)
class ExtractedReviewSemantics:
    statements: ReviewSemantics
    claim_source_state: Literal[
        "source_absent", "extraction_missing", "available"
    ]
    contract_diagnostics: tuple[Diagnostic, ...] = ()


def extract_packet_semantics(
    packet: ReviewSourcePacket,
) -> ExtractedReviewSemantics:
    """Own source-record selection and statement extraction."""

    pr_record = next(
        (item for item in packet.source_records if item.kind == "pull_request"),
        None,
    )
    pr_body = pr_record.body if pr_record else ""
    issue_records = tuple(
        item
        for item in packet.source_records
        if item.kind in {"linked_issue", "ticket"}
    )
    diagnostic_codes = {item.code for item in packet.diagnostics}
    github_issue_resolution_unresolved = packet.metadata.get("source") == "github" and (
        len(issue_records) > 1
        or bool(diagnostic_codes & _UNRESOLVED_GITHUB_ISSUE_CODES)
        or (not issue_records and "github_linked_issue_not_found" not in diagnostic_codes)
    )
    issue_record = (
        issue_records[0]
        if len(issue_records) == 1 and not github_issue_resolution_unresolved
        else None
    )
    statements = extract_review_semantics(
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
        allow_pr_obligation_fallback=not github_issue_resolution_unresolved,
    )
    return ExtractedReviewSemantics(
        statements=statements,
        claim_source_state=(
            "source_absent"
            if pr_record is None or not pr_body.strip()
            else "extraction_missing"
            if not statements.claims
            else "available"
        ),
        contract_diagnostics=statements.contract_diagnostics,
    )
