from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from prismcode.changes.hunks import DiffHunkCollection
    from prismcode.providers.structural import StructuralGraphResult

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
FactProfile = Literal[
    "production",
    "test",
    "document",
    "workflow",
    "configuration",
    "dependency",
    "schema",
    "generated",
    "verification",
    "structural_path",
    "unknown",
]
FactAuthority = Literal[
    "github_diff",
    "structural_provider",
    "verification_provider",
    "supplied",
]
RevisionSide = Literal["head", "base", "review", "unchanged"]
ChangeOperation = Literal[
    "added",
    "modified",
    "removed",
    "renamed",
    "observed",
    "unchanged",
]
FactRole = Literal[
    "changed_anchor",
    "runtime_context",
    "test_context",
    "verification",
    "structural_path",
    "provided_context",
]
RequirementProfile = Literal[
    "behavior",
    "api_contract",
    "ui",
    "test_verification",
    "workflow_configuration",
    "documentation",
    "schema_migration",
    "guardrail",
    "generic",
]
ProjectionSlot = Literal[
    "claim",
    "changed_anchor",
    "runtime_context",
    "test_context",
    "verification",
    "structural_path",
    "boundary_fact",
]
AssociationKind = Literal[
    "provided_association",
    "explicit_reference",
    "exact_identifier",
    "distinctive_phrase",
    "claim_bridge",
    "structural_bridge",
    "current_head",
]
CoverageState = Literal[
    "source_absent",
    "not_applicable",
    "no_eligible_fact",
    "no_association",
    "ambiguous",
    "provider_unavailable",
    "partial_coverage",
    "stale_source",
    "budget_truncated",
    "upstream_deferred",
    "unsupported_change_type",
    "conflicting_facts",
]
ReviewCiState = Literal["not_observed", "failure", "passing", "pending"]
ReviewPullRequestState = Literal["merged", "draft", "open", "closed", "unknown"]
StructuralCoverageState = Literal[
    "disabled",
    "unavailable",
    "available",
    "partial",
    "missing",
    "stale",
    "invalid",
    "error",
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
class VerificationObservation:
    id: str
    name: str
    kind: Literal["check_run", "commit_status", "workflow_run", "manual"]
    status: str
    conclusion: str = ""
    head_sha: str | None = None
    details_url: str | None = None
    provider: str = "unknown"


@dataclass(frozen=True)
class VerificationIdentity:
    provider: str
    kind: Literal["check_run", "commit_status", "workflow_run", "manual"]
    name: str


@dataclass(frozen=True)
class AssociationSignature:
    """Complete normalized retrieval vocabulary for one revision side."""

    identifiers: tuple[str, ...] = ()
    tokens: tuple[str, ...] = ()


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
        pull_requests = tuple(
            item for item in self.source_records if item.kind == "pull_request"
        )
        if len(pull_requests) > 1:
            raise ValueError("review source packet contains multiple pull request records")
        if pull_requests:
            record = pull_requests[0]
            if record.title and record.title != self.title:
                raise ValueError("packet title conflicts with pull request source record")
            if record.url and self.source_url and record.url != self.source_url:
                raise ValueError("packet URL conflicts with pull request source record")


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

    def validate_consistency(self) -> None:
        if self.role != "obligation":
            raise ValueError(f"{self.id}: requirement must own obligation role")
        if self.kind == "guardrail":
            if not self.id.startswith("G") or self.purpose != "guardrail":
                raise ValueError(
                    f"{self.id}: guardrail kind requires G identity and guardrail purpose"
                )
        elif self.id.startswith("G") or self.purpose == "guardrail":
            raise ValueError(
                f"{self.id}: guardrail identity/purpose requires guardrail kind"
            )


@dataclass(frozen=True)
class EvidenceItem:
    """Canonical evidence fact. All downstream relationships reference its ID."""

    id: str
    summary: str
    kind: str
    classification: EvidenceClassification
    profile: FactProfile = "unknown"
    authority: FactAuthority = "supplied"
    revision_side: RevisionSide = "review"
    operation: ChangeOperation = "observed"
    role: FactRole = "changed_anchor"
    changed: bool = False
    associated_statement_ids: tuple[str, ...] = ()
    head_signature: AssociationSignature = AssociationSignature()
    base_signature: AssociationSignature = AssociationSignature()
    observed_head_sha: str | None = None
    verification_identity: VerificationIdentity | None = None
    verification_status: str = ""
    verification_conclusion: str = ""
    sources: tuple[SourceRef, ...] = ()
    structural_path_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate_consistency(self) -> None:
        if self.changed:
            if self.role != "changed_anchor":
                raise ValueError(f"{self.id}: changed fact must own changed_anchor role")
            if self.revision_side not in {"head", "base"}:
                raise ValueError(f"{self.id}: changed fact must identify head or base")
            if self.operation not in {"added", "modified", "removed", "renamed"}:
                raise ValueError(f"{self.id}: changed fact has invalid operation")
        elif self.role == "changed_anchor":
            raise ValueError(f"{self.id}: changed_anchor role requires changed=True")
        if self.operation == "removed" and self.revision_side != "base":
            raise ValueError(f"{self.id}: removed fact must belong to base revision")
        if self.role == "verification" and self.profile != "verification":
            raise ValueError(f"{self.id}: verification role requires verification profile")
        if self.role == "verification":
            if self.verification_identity is None:
                raise ValueError(f"{self.id}: verification fact requires an identity")
            if not self.observed_head_sha:
                raise ValueError(f"{self.id}: verification fact requires an observed head")
            if not self.verification_status:
                raise ValueError(f"{self.id}: verification fact requires a status")
        if self.role == "structural_path" and self.profile != "structural_path":
            raise ValueError(f"{self.id}: structural path role requires structural path profile")
        expected_classifications = {
            "test": {"test"},
            "document": {"document"},
            "verification": {"ci", "runtime"},
            "structural_path": {"runtime", "test", "mixed"},
        }
        expected = expected_classifications.get(self.profile)
        if expected is not None and self.classification not in expected:
            raise ValueError(
                f"{self.id}: {self.profile} profile conflicts with "
                f"{self.classification} classification"
            )


@dataclass(frozen=True)
class EvidenceCatalog:
    items: tuple[EvidenceItem, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    schema_version: str = "evidence_catalog.v5"

    def by_id(self) -> dict[str, EvidenceItem]:
        return {item.id: item for item in self.items}

    def validate_consistency(self) -> None:
        for item in self.items:
            item.validate_consistency()


@dataclass(frozen=True)
class SuppliedEvidence:
    summary: str
    kind: str
    classification: EvidenceClassification
    sources: tuple[SourceRef, ...] = ()
    statement_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class AssociationReason:
    kind: AssociationKind
    detail: str
    matched_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectionRelation:
    id: str
    focus_statement_id: str
    slot: ProjectionSlot
    target_type: Literal["statement", "evidence"]
    target_id: str
    association: AssociationKind
    reasons: tuple[AssociationReason, ...]
    bridge_ids: tuple[str, ...] = ()
    source_ordinal: int = 0


@dataclass(frozen=True)
class ProjectionDiagnostic:
    focus_statement_id: str
    slot: ProjectionSlot
    state: CoverageState
    message: str
    provider: str = ""
    affected_ids: tuple[str, ...] = ()
    sources: tuple[SourceRef, ...] = ()
    scope: Literal["review", "focus"] = "focus"

    @property
    def id(self) -> str:
        identity = "\0".join(
            (
                self.focus_statement_id,
                self.slot,
                self.state,
                self.provider,
                self.message,
                *self.affected_ids,
            )
        )
        return "D:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


@dataclass(frozen=True)
class ProjectionCandidateGroup:
    focus_statement_id: str
    profile: RequirementProfile
    relation_ids: tuple[str, ...] = ()
    diagnostic_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectionCandidateSet:
    relations: tuple[ProjectionRelation, ...] = ()
    groups: tuple[ProjectionCandidateGroup, ...] = ()
    diagnostics: tuple[ProjectionDiagnostic, ...] = ()
    schema_version: str = "projection_candidate_set.v4"

    def by_id(self) -> dict[str, ProjectionRelation]:
        return {item.id: item for item in self.relations}

    def diagnostics_by_id(self) -> dict[str, ProjectionDiagnostic]:
        return {item.id: item for item in self.diagnostics}

    def validate_consistency(self) -> None:
        relations = self.by_id()
        diagnostics = self.diagnostics_by_id()
        if len(relations) != len(self.relations):
            raise ValueError("projection candidate set contains duplicate relation IDs")
        if len(diagnostics) != len(self.diagnostics):
            raise ValueError("projection candidate set contains duplicate diagnostic IDs")
        if len({item.focus_statement_id for item in self.groups}) != len(self.groups):
            raise ValueError("projection candidate set contains duplicate focus groups")
        referenced_relations: set[str] = set()
        for group in self.groups:
            for relation_id in group.relation_ids:
                if relation_id in referenced_relations:
                    raise ValueError(
                        f"{relation_id}: candidate relation belongs to multiple groups"
                    )
                referenced_relations.add(relation_id)
                relation = relations.get(relation_id)
                if relation is None:
                    raise ValueError(
                        f"{group.focus_statement_id}: missing relation {relation_id}"
                    )
                if relation.focus_statement_id != group.focus_statement_id:
                    raise ValueError(
                        f"{relation_id}: relation belongs to a different focus statement"
                    )
            for diagnostic_id in group.diagnostic_ids:
                diagnostic = diagnostics.get(diagnostic_id)
                if diagnostic is None:
                    raise ValueError(
                        f"{group.focus_statement_id}: missing diagnostic {diagnostic_id}"
                    )
                if diagnostic.focus_statement_id != group.focus_statement_id:
                    raise ValueError(
                        f"{diagnostic_id}: diagnostic belongs to a different focus statement"
                    )
        if referenced_relations != set(relations):
            raise ValueError("projection candidate groups must reference every relation")


@dataclass(frozen=True)
class StructuralSupportSet:
    """Selected structural relations needed to support one review focus."""

    path_relation_ids: tuple[str, ...] = ()
    omitted_path_relation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConvergenceGroup:
    focus_statement_id: str
    selected_relation_ids: tuple[str, ...] = ()
    deferred_relation_ids: tuple[str, ...] = ()
    structural_support: StructuralSupportSet = StructuralSupportSet()
    diagnostic_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateConvergence:
    groups: tuple[ConvergenceGroup, ...] = ()
    diagnostics: tuple[ProjectionDiagnostic, ...] = ()
    schema_version: str = "candidate_convergence.v5"

    def diagnostics_by_id(self) -> dict[str, ProjectionDiagnostic]:
        return {item.id: item for item in self.diagnostics}

    def selected_relation_ids(self) -> tuple[str, ...]:
        return tuple(
            relation_id
            for group in self.groups
            for relation_id in group.selected_relation_ids
        )

    def validate_consistency(self, candidates: ProjectionCandidateSet) -> None:
        relations = candidates.by_id()
        candidate_groups = {
            item.focus_statement_id: item for item in candidates.groups
        }
        diagnostics = self.diagnostics_by_id()
        if len(diagnostics) != len(self.diagnostics):
            raise ValueError("candidate convergence contains duplicate diagnostic IDs")
        if len({item.focus_statement_id for item in self.groups}) != len(self.groups):
            raise ValueError("candidate convergence contains duplicate focus groups")
        if {item.focus_statement_id for item in self.groups} != set(candidate_groups):
            raise ValueError("candidate convergence must contain every candidate focus")
        for group in self.groups:
            candidate_group = candidate_groups.get(group.focus_statement_id)
            if candidate_group is None:
                raise ValueError(
                    f"{group.focus_statement_id}: convergence focus has no candidates"
                )
            selected = set(group.selected_relation_ids)
            deferred = set(group.deferred_relation_ids)
            if len(selected) != len(group.selected_relation_ids):
                raise ValueError(
                    f"{group.focus_statement_id}: duplicate selected relation"
                )
            if len(deferred) != len(group.deferred_relation_ids):
                raise ValueError(
                    f"{group.focus_statement_id}: duplicate deferred relation"
                )
            if selected & deferred:
                raise ValueError(
                    f"{group.focus_statement_id}: relation is both selected and deferred"
                )
            if selected | deferred != set(candidate_group.relation_ids):
                raise ValueError(
                    f"{group.focus_statement_id}: convergence must partition candidates"
                )
            structural_selected = {
                relation_id
                for relation_id in group.selected_relation_ids
                if relations[relation_id].slot == "structural_path"
            }
            support = group.structural_support
            support_ids = set(support.path_relation_ids)
            omitted_support_ids = set(support.omitted_path_relation_ids)
            if len(support_ids) != len(support.path_relation_ids):
                raise ValueError(
                    f"{group.focus_statement_id}: duplicate structural support relation"
                )
            if len(omitted_support_ids) != len(
                support.omitted_path_relation_ids
            ):
                raise ValueError(
                    f"{group.focus_statement_id}: duplicate omitted support relation"
                )
            if support_ids & omitted_support_ids:
                raise ValueError(
                    f"{group.focus_statement_id}: structural relation is both "
                    "displayed and omitted"
                )
            if support_ids | omitted_support_ids != structural_selected:
                raise ValueError(
                    f"{group.focus_statement_id}: structural support must partition "
                    "selected structural paths"
                )
            for relation_id in (*group.selected_relation_ids, *group.deferred_relation_ids):
                relation = relations.get(relation_id)
                if relation is None or relation.focus_statement_id != group.focus_statement_id:
                    raise ValueError(
                        f"{group.focus_statement_id}: invalid convergence relation {relation_id}"
                    )
            for diagnostic_id in group.diagnostic_ids:
                diagnostic = diagnostics.get(diagnostic_id)
                if (
                    diagnostic is None
                    or diagnostic.focus_statement_id != group.focus_statement_id
                ):
                    raise ValueError(
                        f"{group.focus_statement_id}: invalid convergence diagnostic "
                        f"{diagnostic_id}"
                    )


StructuralSubgraphNodeRole = Literal[
    "changed_anchor",
    "runtime_context",
    "test_context",
    "intermediate",
]


@dataclass(frozen=True)
class StructuralSubgraphNode:
    evidence_id: str
    role: StructuralSubgraphNodeRole
    relation_ids: tuple[str, ...] = ()
    path_relation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class StructuralSubgraphEdge:
    source_evidence_id: str
    target_evidence_id: str
    relation: str
    direction: Literal["outgoing", "incoming"]
    path_relation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class StructuralSubgraph:
    nodes: tuple[StructuralSubgraphNode, ...] = ()
    edges: tuple[StructuralSubgraphEdge, ...] = ()
    path_relation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewSlice:
    focus_statement_id: str
    claim_relation_ids: tuple[str, ...] = ()
    standalone_changed_anchor_relation_ids: tuple[str, ...] = ()
    standalone_runtime_relation_ids: tuple[str, ...] = ()
    standalone_test_relation_ids: tuple[str, ...] = ()
    verification_relation_ids: tuple[str, ...] = ()
    structural_subgraph: StructuralSubgraph = StructuralSubgraph()
    diagnostic_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewProjection:
    slices: tuple[ReviewSlice, ...] = ()
    schema_version: str = "review_projection.v5"


@dataclass(frozen=True)
class ReviewAttention:
    id: str
    label: str
    message: str
    focus_statement_ids: tuple[str, ...] = ()
    sources: tuple[SourceRef, ...] = ()
    scope: Literal["review", "focus"] = "focus"
    provider: str = ""


@dataclass(frozen=True)
class ReviewOverview:
    pull_request_state: ReviewPullRequestState
    ci_state: ReviewCiState
    changed_file_count: int
    structural_coverage: StructuralCoverage
    attention: tuple[ReviewAttention, ...] = ()
    empty_review_message: str | None = None


@dataclass(frozen=True)
class StructuralCoverage:
    state: StructuralCoverageState
    provider: str = ""
    hunk_count: int = 0
    mapped_hunk_count: int = 0
    symbol_count: int = 0
    path_count: int = 0
    requested_files: int = 0
    indexed_files: int = 0
    missing_reason: Literal["index_absent", "files_unindexed", ""] = ""


@dataclass(frozen=True)
class AnalysisInput:
    packet: ReviewSourcePacket
    requirements: tuple[Requirement, ...] = ()
    changes: DiffHunkCollection | None = None
    structural_graph: StructuralGraphResult | None = None
    structural_graph_disabled: bool = False
    supplied_evidence: tuple[SuppliedEvidence, ...] = ()


@dataclass(frozen=True)
class ReviewBrief:
    packet: ReviewSourcePacket
    intent: ReviewStatement
    requirements: tuple[Requirement, ...]
    guardrails: tuple[Requirement, ...] = ()
    objectives: tuple[ReviewStatement, ...] = ()
    scope: tuple[ReviewStatement, ...] = ()
    claims: tuple[ReviewStatement, ...] = ()
    evidence_catalog: EvidenceCatalog = EvidenceCatalog()
    projection_candidates: ProjectionCandidateSet = ProjectionCandidateSet()
    candidate_convergence: CandidateConvergence = CandidateConvergence()
    projection: ReviewProjection = ReviewProjection()
    overview: ReviewOverview = ReviewOverview(
        pull_request_state="unknown",
        ci_state="not_observed",
        changed_file_count=0,
        structural_coverage=StructuralCoverage(state="unavailable"),
    )
    generated_by: str = "prismcode-open-core"
    schema_version: str = "review_brief.v19"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
