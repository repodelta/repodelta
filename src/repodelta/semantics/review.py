from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from repodelta.model.contracts import ReviewSourcePacket, SourceRef
from repodelta.semantics.criteria import ReviewSemantics, extract_review_semantics


@dataclass(frozen=True)
class ExtractedReviewSemantics:
    statements: ReviewSemantics
    claim_source_state: Literal[
        "source_absent", "extraction_missing", "available"
    ]


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
    issue_record = issue_records[0] if len(issue_records) == 1 else None
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
    )
