from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal

DiagnosticSeverity = Literal["info", "warning", "error"]
RequirementKind = Literal["deliverable", "guardrail", "manual_acceptance"]
ImplementationStatus = Literal["observed", "partial", "not_observed", "contradicted"]
VerificationStatus = Literal[
    "passed", "failed", "pending", "not_observed", "stale", "manual_required"
]


@dataclass(frozen=True)
class SourceRef:
    label: str
    url: str | None = None
    path: str | None = None
    line_start: int | None = None
    line_end: int | None = None


@dataclass(frozen=True)
class SourceRecord:
    id: str
    kind: str
    repository: str
    url: str | None = None
    title: str = ""
    body: str = ""
    revision: str = ""
    availability: Literal["available", "unavailable", "partial"] = "available"


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str = "modified"
    additions: int | None = None
    deletions: int | None = None
    changes: int | None = None
    source_url: str | None = None
    patch: str | None = None


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    severity: DiagnosticSeverity = "warning"
    sources: tuple[SourceRef, ...] = ()


@dataclass(frozen=True)
class ReviewSourcePacket:
    """Canonical, conclusion-free facts collected for one review."""

    repository: str
    pull_request: int | None
    title: str
    source_records: tuple[SourceRecord, ...]
    changed_files: tuple[ChangedFile, ...] = ()
    source_url: str | None = None
    head_sha: str | None = None
    base_sha: str | None = None
    diagnostics: tuple[Diagnostic, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "review_source_packet.v1"
    packet_revision: str = ""

    def semantic_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("packet_revision", None)
        return value

    def recompute_revision(self) -> str:
        encoded = json.dumps(
            self.semantic_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    def with_revision(self) -> ReviewSourcePacket:
        return replace(self, packet_revision=self.recompute_revision())

    def validate_consistency(self) -> None:
        if self.schema_version != "review_source_packet.v1":
            raise ValueError(f"unsupported source packet schema: {self.schema_version}")
        if not self.packet_revision or self.packet_revision != self.recompute_revision():
            raise ValueError("review source packet content does not match packet_revision")


@dataclass(frozen=True)
class Requirement:
    """A source assertion. Analysis conclusions never belong in this record."""

    id: str
    text: str
    kind: RequirementKind = "deliverable"
    sources: tuple[SourceRef, ...] = ()


@dataclass(frozen=True)
class Evidence:
    summary: str
    kind: str
    sources: tuple[SourceRef, ...] = ()


@dataclass(frozen=True)
class EvidenceHint:
    """Trusted fixture/provider input; it supplies facts, never final status."""

    requirement_id: str
    implementation: tuple[Evidence, ...] = ()
    verification: tuple[Evidence, ...] = ()
    verification_outcome: Literal[
        "success", "failure", "pending", "not_observed", "stale", "manual_required"
    ] = "not_observed"
    gaps: tuple[str, ...] = ()
    provenance: tuple[SourceRef, ...] = ()


@dataclass(frozen=True)
class AnalysisInput:
    packet: ReviewSourcePacket
    requirements: tuple[Requirement, ...] = ()
    evidence_hints: tuple[EvidenceHint, ...] = ()


@dataclass(frozen=True)
class ImplementationAssessment:
    status: ImplementationStatus
    evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True)
class VerificationAssessment:
    status: VerificationStatus
    evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True)
class RequirementAssessment:
    requirement: Requirement
    implementation: ImplementationAssessment
    verification: VerificationAssessment
    gaps: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewBrief:
    packet: ReviewSourcePacket
    intent: str
    assessments: tuple[RequirementAssessment, ...]
    generated_by: str = "prismcode-open-core"
    schema_version: str = "review_brief.v2"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
