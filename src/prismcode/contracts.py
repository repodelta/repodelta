from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from .structural_graph import StructuralGraphResult

DiagnosticSeverity = Literal["info", "warning", "error"]
RequirementKind = Literal["deliverable", "guardrail", "manual_acceptance"]
StatementRole = Literal["obligation", "objective", "claim", "context", "intent"]
StatementPurpose = Literal[
    "unspecified",
    "acceptance",
    "guardrail",
    "goal",
    "scope",
    "implementation",
    "baseline",
    "verification",
    "boundary",
    "intent",
]
StatementAuthority = Literal[
    "issue",
    "pr_description",
    "pr_title",
    "provided",
]
EvidenceClassification = Literal[
    "code", "test", "document", "ci", "runtime", "mixed"
]
CandidateBindingKind = Literal["statement_evidence", "requirement_claim"]


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
class VerificationObservation:
    id: str
    name: str
    kind: Literal["check_run", "commit_status", "workflow_run", "manual"]
    status: str
    conclusion: str = ""
    head_sha: str | None = None
    details_url: str | None = None


@dataclass(frozen=True)
class ReviewSourcePacket:
    """Canonical, conclusion-free facts collected for one review."""

    repository: str
    pull_request: int | None
    title: str
    source_records: tuple[SourceRecord, ...]
    changed_files: tuple[ChangedFile, ...] = ()
    verification_observations: tuple[VerificationObservation, ...] = ()
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
class ReviewStatement:
    """A provenance-bearing source assertion, never an analysis conclusion."""

    id: str
    text: str
    role: StatementRole = "obligation"
    purpose: StatementPurpose = "unspecified"
    authority: StatementAuthority = "provided"
    sources: tuple[SourceRef, ...] = ()


@dataclass(frozen=True)
class Requirement(ReviewStatement):
    """An obligation statement used to retrieve review evidence candidates."""

    kind: RequirementKind = "deliverable"


@dataclass(frozen=True)
class EvidenceItem:
    """Canonical evidence fact. All downstream relationships reference its ID."""

    id: str
    summary: str
    kind: str
    classification: EvidenceClassification
    changed: bool = False
    sources: tuple[SourceRef, ...] = ()
    structural_path_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceCatalog:
    items: tuple[EvidenceItem, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    schema_version: str = "evidence_catalog.v1"

    def by_id(self) -> dict[str, EvidenceItem]:
        return {item.id: item for item in self.items}


@dataclass(frozen=True)
class BindingReason:
    feature: str
    detail: str
    weight: int
    matched_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateBinding:
    id: str
    kind: CandidateBindingKind
    source_id: str
    target_id: str
    score: int
    reasons: tuple[BindingReason, ...]
    structural_path_ids: tuple[str, ...] = ()
    relation: Literal["candidate_support"] = "candidate_support"


@dataclass(frozen=True)
class CandidateCoverage:
    requirement_ids_without_evidence_candidates: tuple[str, ...] = ()
    claim_ids_without_requirement_candidates: tuple[str, ...] = ()
    evidence_ids_without_statement_candidates: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateBindingSet:
    items: tuple[CandidateBinding, ...] = ()
    coverage: CandidateCoverage = CandidateCoverage()
    diagnostics: tuple[Diagnostic, ...] = ()
    schema_version: str = "candidate_binding_set.v1"


@dataclass(frozen=True)
class AnalysisInput:
    packet: ReviewSourcePacket
    requirements: tuple[Requirement, ...] = ()
    structural_graph: StructuralGraphResult | None = None
    supplied_evidence: tuple[EvidenceItem, ...] = ()


@dataclass(frozen=True)
class ReviewBrief:
    packet: ReviewSourcePacket
    intent: ReviewStatement
    requirements: tuple[Requirement, ...]
    guardrails: tuple[Requirement, ...] = ()
    objectives: tuple[ReviewStatement, ...] = ()
    scope: tuple[ReviewStatement, ...] = ()
    claims: tuple[ReviewStatement, ...] = ()
    structural_graph: StructuralGraphResult | None = None
    evidence_catalog: EvidenceCatalog = EvidenceCatalog()
    candidate_bindings: CandidateBindingSet = CandidateBindingSet()
    generated_by: str = "prismcode-open-core"
    schema_version: str = "review_brief.v8"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
