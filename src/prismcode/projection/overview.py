from __future__ import annotations

import hashlib
from typing import Literal

from prismcode.model.contracts import (
    ProjectionCandidateSet,
    ProjectionDiagnostic,
    EvidenceCatalog,
    Requirement,
    ReviewAttention,
    ReviewCiState,
    ReviewOverview,
    ReviewPullRequestState,
    ReviewSourcePacket,
    StructuralCoverage,
)
from prismcode.providers.structural import StructuralGraphResult

_SOURCE_COVERAGE_CODES = {
    "github_linked_issue_not_found",
    "github_linked_issues_unavailable",
    "github_patch_unavailable",
    "github_file_limit_reached",
}


def build_review_overview(
    packet: ReviewSourcePacket,
    requirements: tuple[Requirement, ...],
    candidates: ProjectionCandidateSet,
    evidence_catalog: EvidenceCatalog,
    structural_graph: StructuralGraphResult | None,
    *,
    structural_graph_disabled: bool,
) -> ReviewOverview:
    """Normalize review-wide status once for every presentation adapter."""

    attention = list(_projection_attention(candidates))
    source_messages = tuple(
        item
        for item in packet.diagnostics
        if item.code in _SOURCE_COVERAGE_CODES
    )
    if source_messages:
        attention.append(
            ReviewAttention(
                id=_attention_id(
                    "source_coverage",
                    tuple(item.message for item in source_messages),
                ),
                label="Source coverage",
                message=" ".join(item.message for item in source_messages),
                sources=tuple(
                    source
                    for item in source_messages
                    for source in item.sources
                ),
            )
        )
    source_message_text = {item.message for item in source_messages}
    change_messages = tuple(
        item
        for item in evidence_catalog.diagnostics
        if item.message not in source_message_text
    )
    if change_messages:
        attention.append(
            ReviewAttention(
                id=_attention_id(
                    "change_coverage",
                    tuple(item.message for item in change_messages),
                ),
                label="Change coverage",
                message=" ".join(item.message for item in change_messages),
                sources=tuple(
                    source
                    for item in change_messages
                    for source in item.sources
                ),
            )
        )
    guardrails = tuple(item for item in requirements if item.kind == "guardrail")
    if guardrails:
        attention.append(
            ReviewAttention(
                id=_attention_id(
                    "scope_guardrails",
                    tuple(f"{item.id}:{item.text}" for item in guardrails),
                ),
                label="Scope guardrails",
                message=" · ".join(
                    f"{item.id}: {item.text}" for item in guardrails
                ),
                focus_statement_ids=tuple(item.id for item in guardrails),
            )
        )
    return ReviewOverview(
        pull_request_state=_pull_request_state(packet),
        ci_state=_ci_state(packet),
        changed_file_count=len(packet.changed_files),
        structural_coverage=_structural_coverage(
            structural_graph,
            disabled=structural_graph_disabled,
        ),
        attention=tuple(attention),
        empty_review_message=(
            None
            if requirements
            else (
                "No explicit acceptance criteria found. Intent and PR claims "
                "remain context and were not promoted to requirements."
            )
        ),
    )


def _projection_attention(
    candidates: ProjectionCandidateSet,
) -> tuple[ReviewAttention, ...]:
    grouped: dict[tuple[str, str], list[ProjectionDiagnostic]] = {}
    for diagnostic in candidates.diagnostics:
        if diagnostic.state == "not_applicable":
            continue
        grouped.setdefault((diagnostic.slot, diagnostic.state), []).append(diagnostic)
    result = []
    for (slot, state), diagnostics in sorted(grouped.items()):
        focus_ids = tuple(
            dict.fromkeys(
                item.focus_statement_id for item in diagnostics
            )
        )
        messages = tuple(
            dict.fromkeys(
                item.message for item in diagnostics
            )
        )
        label = (
            "Acceptance basis"
            if focus_ids == ("I1",) and state == "source_absent"
            else f"{slot.replace('_', ' ')} · {state.replace('_', ' ')}"
        )
        result.append(
            ReviewAttention(
                id=_attention_id(label, (*focus_ids, *messages)),
                label=label,
                message=" ".join(messages),
                focus_statement_ids=focus_ids,
            )
        )
    return tuple(result)


def _ci_state(packet: ReviewSourcePacket) -> ReviewCiState:
    current = tuple(
        item
        for item in packet.verification_observations
        if packet.head_sha and item.head_sha == packet.head_sha
    )
    if not current:
        return "not_observed"
    conclusions = {item.conclusion.casefold() for item in current if item.conclusion}
    if conclusions & {"failure", "failed", "error", "cancelled", "timed_out"}:
        return "failure"
    if conclusions and conclusions <= {"success", "neutral", "skipped"}:
        return "passing"
    return "pending"


def _pull_request_state(packet: ReviewSourcePacket) -> ReviewPullRequestState:
    if packet.metadata.get("merged"):
        return "merged"
    if packet.metadata.get("draft"):
        return "draft"
    state = str(packet.metadata.get("state") or "").casefold()
    if state == "open":
        return "open"
    if state == "closed":
        return "closed"
    return "unknown"


def _attention_id(label: str, values: tuple[str, ...]) -> str:
    raw = "\0".join((label, *values))
    return "A:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _structural_coverage(
    result: StructuralGraphResult | None,
    *,
    disabled: bool,
) -> StructuralCoverage:
    if disabled:
        return StructuralCoverage(state="disabled")
    if result is None:
        return StructuralCoverage(state="unavailable")
    missing_reason: Literal["index_absent", "files_unindexed", ""] = ""
    if result.index.state == "missing":
        codes = {item.code for item in result.index.diagnostics}
        missing_reason = (
            "index_absent"
            if "codegraph_index_missing" in codes
            else "files_unindexed"
        )
    return StructuralCoverage(
        state=result.index.state,
        provider=result.index.provider,
        hunk_count=result.hunk_count,
        mapped_hunk_count=result.mapped_hunk_count,
        symbol_count=len(result.overlaps),
        path_count=len(result.paths),
        requested_files=result.index.requested_files,
        indexed_files=result.index.indexed_files,
        missing_reason=missing_reason,
    )
