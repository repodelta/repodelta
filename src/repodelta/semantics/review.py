from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from repodelta.model.contracts import Diagnostic, ReviewSourcePacket, SourceRef
from repodelta.semantics.criteria import ReviewSemantics, extract_review_semantics


GoverningIssueResolution = Literal[
    "non_github", "unique", "confirmed_absent", "ambiguous", "unavailable"
]
_GITHUB_ISSUE_UNAVAILABLE = "github_linked_issues_unavailable"
_GITHUB_ISSUE_AMBIGUOUS = "github_linked_issues_ambiguous"
_GITHUB_ISSUE_NOT_FOUND = "github_linked_issue_not_found"


def _governing_issue_resolution(
    packet: ReviewSourcePacket,
    *,
    issue_count: int,
) -> GoverningIssueResolution:
    """Derive local fallback permission without replacing canonical packet facts."""

    if packet.metadata.get("source") != "github":
        return "non_github"
    diagnostic_codes = {item.code for item in packet.diagnostics}
    if _GITHUB_ISSUE_UNAVAILABLE in diagnostic_codes:
        return "unavailable"
    if _GITHUB_ISSUE_AMBIGUOUS in diagnostic_codes or issue_count > 1:
        return "ambiguous"
    if issue_count == 1:
        return "unique"
    if _GITHUB_ISSUE_NOT_FOUND in diagnostic_codes:
        return "confirmed_absent"
    return "unavailable"


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
    issue_resolution = _governing_issue_resolution(
        packet,
        issue_count=len(issue_records),
    )
    issue_record = (
        issue_records[0]
        if len(issue_records) == 1
        and issue_resolution in {"non_github", "unique"}
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
        allow_pr_obligation_fallback=issue_resolution
        in {"non_github", "unique", "confirmed_absent"},
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
