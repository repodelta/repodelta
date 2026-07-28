from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from prismcode.changes.hunks import DiffHunkCollection
    from prismcode.providers.structural import StructuralGraphCollection

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
    "guardrail_scan_provider",
    "supplied",
]
RevisionSide = Literal["head", "base", "review", "unchanged"]
ChangeOperation = Literal[
    "added",
    "modified",
    "replaced",
    "removed",
    "renamed",
    "retained",
    "unresolved",
    "observed",
    "unchanged",
]
FactRole = Literal[
    "changed_anchor",
    "revision_fact",
    "runtime_context",
    "test_context",
    "verification",
    "structural_path",
    "structural_relation",
    "structural_ownership",
    "boundary_fact",
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
FocusEvidenceRole = Literal[
    "primary",
    "test_support",
    "document_support",
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
GuardrailScanSurface = Literal["paths", "file_content", "symbol_names"]
GuardrailScanState = Literal["complete", "partial", "unavailable"]
GuardrailSelectorKind = Literal["identifier", "phrase"]
GuardrailScanBoundaryKind = Literal["file_limit", "byte_limit", "match_limit"]
ChangeRelationKind = Literal["added", "removed", "replaced"]


@dataclass(frozen=True)
class SourceRef:
    label: str
    url: str | None = None
    path: str | None = None
    line_start: int | None = None
    line_end: int | None = None


@dataclass(frozen=True)
class ChangedLine:
    number: int
    text: str


@dataclass(frozen=True)
class ChangeRelation:
    id: str
    hunk_id: str
    base_path: str | None
    head_path: str | None
    kind: ChangeRelationKind
    added: tuple[ChangedLine, ...] = ()
    removed: tuple[ChangedLine, ...] = ()

    def __post_init__(self) -> None:
        expected: ChangeRelationKind
        if self.added and self.removed:
            expected = "replaced"
        elif self.added:
            expected = "added"
        elif self.removed:
            expected = "removed"
        else:
            raise ValueError(
                f"{self.id}: change relation must own base or head lines"
            )
        if self.kind != expected:
            raise ValueError(
                f"{self.id}: {self.kind} conflicts with base/head relation shape"
            )
        if self.removed and not self.base_path:
            raise ValueError(f"{self.id}: removed lines require a base path")
        if self.added and not self.head_path:
            raise ValueError(f"{self.id}: added lines require a head path")

    def path_for_revision(self, revision_side: Literal["base", "head"]) -> str:
        path = self.base_path if revision_side == "base" else self.head_path
        if path is None:
            raise ValueError(
                f"{self.id}: no {revision_side} path exists for this change"
            )
        return path

    @property
    def added_lines(self) -> tuple[int, ...]:
        return tuple(item.number for item in self.added)

    @property
    def removed_lines(self) -> tuple[int, ...]:
        return tuple(item.number for item in self.removed)

    @property
    def new_snippet(self) -> str:
        return "\n".join(item.text for item in self.added)

    @property
    def old_snippet(self) -> str:
        return "\n".join(item.text for item in self.removed)


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
    base_path: str | None
    head_path: str | None
    status: str = "modified"
    additions: int | None = None
    deletions: int | None = None
    changes: int | None = None
    source_url: str | None = None
    patch: str | None = None

    def __post_init__(self) -> None:
        if not self.base_path and not self.head_path:
            raise ValueError("changed file requires a base or head path")
        expected = {
            "added": self.base_path is None and self.head_path is not None,
            "removed": self.base_path is not None and self.head_path is None,
            "renamed": (
                self.base_path is not None
                and self.head_path is not None
                and self.base_path != self.head_path
            ),
            "modified": (
                self.base_path is not None
                and self.head_path is not None
                and self.base_path == self.head_path
            ),
        }
        if self.status in expected and not expected[self.status]:
            raise ValueError(
                f"{self.status} changed file has inconsistent revision paths"
            )

    def path_for_revision(self, revision_side: Literal["base", "head"]) -> str:
        path = self.base_path if revision_side == "base" else self.head_path
        if path is None:
            raise ValueError(
                f"changed file has no {revision_side} revision path"
            )
        return path

    @property
    def display_path(self) -> str:
        return self.head_path or self.base_path or ""


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
    schema_version: str = "review_source_packet.v2"
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
        if self.schema_version != "review_source_packet.v2":
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
class GuardrailScanPlan:
    """Source-backed scan intent. A plan is never evidence that a scan ran."""

    id: str
    guardrail_id: str
    query_text: str
    revision_side: Literal["head"] = "head"
    scope: Literal["repository"] = "repository"
    root_paths: tuple[str, ...] = (".",)
    surfaces: tuple[GuardrailScanSurface, ...] = (
        "paths",
        "file_content",
    )
    selectors: tuple[GuardrailScanSelector, ...] = ()
    sources: tuple[SourceRef, ...] = ()


@dataclass(frozen=True)
class GuardrailScanSelector:
    id: str
    kind: GuardrailSelectorKind
    value: str


@dataclass(frozen=True)
class GuardrailScanPlanSet:
    plans: tuple[GuardrailScanPlan, ...] = ()
    schema_version: str = "guardrail_scan_plan_set.v2"

    def by_id(self) -> dict[str, GuardrailScanPlan]:
        return {item.id: item for item in self.plans}

    def by_guardrail_id(self) -> dict[str, GuardrailScanPlan]:
        return {item.guardrail_id: item for item in self.plans}

    def validate_consistency(
        self,
        guardrails: tuple[Requirement, ...],
    ) -> None:
        plan_ids = self.by_id()
        by_guardrail = self.by_guardrail_id()
        expected = {item.id for item in guardrails}
        if len(plan_ids) != len(self.plans):
            raise ValueError("guardrail scan plan set contains duplicate plan IDs")
        if len(by_guardrail) != len(self.plans):
            raise ValueError("guardrail scan plan set contains duplicate guardrail IDs")
        if set(by_guardrail) != expected:
            raise ValueError(
                "guardrail scan plans must map one-to-one to canonical guardrails"
            )
        for guardrail in guardrails:
            if (
                guardrail.kind != "guardrail"
                or guardrail.purpose != "guardrail"
                or not guardrail.id.startswith("G")
            ):
                raise ValueError(
                    "guardrail scan plans must map one-to-one to canonical guardrails"
                )
            plan = by_guardrail[guardrail.id]
            if plan.id != f"GSP:{guardrail.id}":
                raise ValueError(f"{plan.id}: non-canonical guardrail scan plan ID")
            if plan.query_text != guardrail.text or plan.sources != guardrail.sources:
                raise ValueError(
                    f"{plan.id}: scan intent must preserve guardrail text and sources"
                )
            if (
                plan.revision_side != "head"
                or plan.scope != "repository"
                or plan.root_paths != (".",)
                or plan.surfaces
                != ("paths", "file_content", "symbol_names")
            ):
                raise ValueError(f"{plan.id}: unsupported scan-plan boundary")
            if len({item.id for item in plan.selectors}) != len(plan.selectors):
                raise ValueError(f"{plan.id}: duplicate selector ID")
            for index, selector in enumerate(plan.selectors, start=1):
                if selector.id != f"{plan.id}:selector:{index}":
                    raise ValueError(f"{selector.id}: non-canonical selector ID")
                if not selector.value.strip():
                    raise ValueError(f"{selector.id}: empty selector")


@dataclass(frozen=True)
class GuardrailScanMatch:
    id: str
    plan_id: str
    guardrail_id: str
    selector_id: str
    surface: GuardrailScanSurface
    path: str
    line: int | None = None
    excerpt: str = ""


@dataclass(frozen=True)
class GuardrailScanCoverage:
    surface: GuardrailScanSurface
    state: GuardrailScanState
    inspected_count: int = 0
    inspected_bytes: int = 0
    message: str = ""


@dataclass(frozen=True)
class GuardrailScanTruncation:
    kind: GuardrailScanBoundaryKind
    surface: GuardrailScanSurface
    limit: int
    observed: int


@dataclass(frozen=True)
class GuardrailScanResult:
    id: str
    plan_id: str
    guardrail_id: str
    revision: str
    root_path: str
    state: GuardrailScanState
    coverages: tuple[GuardrailScanCoverage, ...] = ()
    truncations: tuple[GuardrailScanTruncation, ...] = ()
    matches: tuple[GuardrailScanMatch, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True)
class GuardrailScanResultSet:
    results: tuple[GuardrailScanResult, ...] = ()
    schema_version: str = "guardrail_scan_result_set.v1"

    def by_guardrail_id(self) -> dict[str, GuardrailScanResult]:
        return {item.guardrail_id: item for item in self.results}

    def validate_consistency(self, plans: GuardrailScanPlanSet) -> None:
        plan_by_id = plans.by_id()
        if len(self.by_guardrail_id()) != len(self.results):
            raise ValueError("guardrail scan results contain duplicate guardrail IDs")
        if {item.plan_id for item in self.results} != set(plan_by_id):
            raise ValueError("guardrail scan results must map one-to-one to plans")
        for result in self.results:
            plan = plan_by_id[result.plan_id]
            if result.id != f"GSR:{result.guardrail_id}":
                raise ValueError(f"{result.id}: non-canonical scan-result ID")
            if result.guardrail_id != plan.guardrail_id:
                raise ValueError(f"{result.id}: result guardrail conflicts with plan")
            selector_ids = {item.id for item in plan.selectors}
            if any(item.selector_id not in selector_ids for item in result.matches):
                raise ValueError(f"{result.id}: match references unknown selector")
            if any(item.surface not in plan.surfaces for item in result.matches):
                raise ValueError(f"{result.id}: match references unplanned surface")
            if tuple(item.surface for item in result.coverages) != plan.surfaces:
                raise ValueError(
                    f"{result.id}: result coverage must preserve plan surfaces"
                )
            if any(
                item.surface not in plan.surfaces
                or item.limit <= 0
                or item.observed < item.limit
                for item in result.truncations
            ):
                raise ValueError(f"{result.id}: invalid scan truncation")
            if result.state == "complete" and result.truncations:
                raise ValueError(
                    f"{result.id}: complete result cannot carry truncation"
                )
            if result.state == "complete" and any(
                item.state != "complete" for item in result.coverages
            ):
                raise ValueError(
                    f"{result.id}: complete result requires complete surfaces"
                )
            if result.state == "partial" and not result.truncations:
                raise ValueError(
                    f"{result.id}: partial result requires typed truncation"
                )
            if result.state == "partial" and all(
                item.state == "complete" for item in result.coverages
            ):
                raise ValueError(
                    f"{result.id}: partial result requires partial surface"
                )
            if result.state == "unavailable" and any(
                item.state != "unavailable" for item in result.coverages
            ):
                raise ValueError(
                    f"{result.id}: unavailable result requires unavailable surfaces"
                )
            if result.state != "unavailable" and not result.revision:
                raise ValueError(f"{result.id}: observed scan requires a revision")


@dataclass(frozen=True)
class GuardrailScanDiagnostic:
    code: str
    message: str
    plan_id: str
    guardrail_id: str


@dataclass(frozen=True)
class StructuralChangeIdentity:
    review_symbol_id: str
    base_symbol_evidence_id: str | None = None
    head_symbol_evidence_id: str | None = None
    schema_version: str = "structural_change_identity.v2"


@dataclass(frozen=True)
class StructuralReplacementCandidate:
    """Non-authoritative pairing of two canonical structural deltas."""

    id: str
    removed_change_evidence_id: str
    added_change_evidence_id: str
    change_relation_ids: tuple[str, ...]
    signals: tuple[
        Literal["shared_replacement_relation", "same_symbol_kind"], ...
    ] = ("shared_replacement_relation", "same_symbol_kind")
    schema_version: str = "structural_replacement_candidate.v1"

    def __post_init__(self) -> None:
        if (
            not self.id
            or not self.removed_change_evidence_id
            or not self.added_change_evidence_id
        ):
            raise ValueError("structural replacement candidate fields must be non-empty")
        if self.removed_change_evidence_id == self.added_change_evidence_id:
            raise ValueError("structural replacement candidate endpoints must differ")
        if not self.change_relation_ids:
            raise ValueError(
                "structural replacement candidate requires change relations"
            )
        if self.change_relation_ids != tuple(sorted(set(self.change_relation_ids))):
            raise ValueError(
                "structural replacement candidate relations must be sorted and unique"
            )
        if self.signals != (
            "shared_replacement_relation",
            "same_symbol_kind",
        ):
            raise ValueError("structural replacement candidate signals are canonical")


@dataclass(frozen=True)
class StructuralRelationChangeIdentity:
    """One revision-independent directed logical-symbol relation."""

    source_review_symbol_id: str
    target_review_symbol_id: str
    relation: str
    base_path_evidence_ids: tuple[str, ...] = ()
    head_path_evidence_ids: tuple[str, ...] = ()
    schema_version: str = "structural_relation_change_identity.v2"

    def __post_init__(self) -> None:
        if (
            not self.source_review_symbol_id
            or not self.target_review_symbol_id
            or not self.relation
        ):
            raise ValueError("structural relation identity fields must be non-empty")
        if not self.base_path_evidence_ids and not self.head_path_evidence_ids:
            raise ValueError("structural relation identity requires path provenance")


@dataclass(frozen=True)
class StructuralOwnershipIdentity:
    """One revision-local parent-to-child ownership observation."""

    parent_provider_symbol_id: str
    child_provider_symbol_id: str
    parent_symbol_evidence_id: str
    child_symbol_evidence_id: str
    schema_version: str = "structural_ownership_identity.v1"


@dataclass(frozen=True)
class StructuralOwnershipChangeIdentity:
    """One revision-independent logical parent-to-child ownership truth."""

    parent_review_symbol_id: str
    child_review_symbol_id: str
    base_ownership_evidence_id: str | None = None
    head_ownership_evidence_id: str | None = None
    schema_version: str = "structural_ownership_change_identity.v2"

    def __post_init__(self) -> None:
        if not self.parent_review_symbol_id or not self.child_review_symbol_id:
            raise ValueError("structural ownership identity fields must be non-empty")
        if (
            self.base_ownership_evidence_id is None
            and self.head_ownership_evidence_id is None
        ):
            raise ValueError("structural ownership change requires provenance")


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
    guardrail_scan_result: GuardrailScanResult | None = None
    sources: tuple[SourceRef, ...] = ()
    change_relation_ids: tuple[str, ...] = ()
    structural_path_ids: tuple[str, ...] = ()
    structural_change: StructuralChangeIdentity | None = None
    structural_relation_change: StructuralRelationChangeIdentity | None = None
    structural_ownership: StructuralOwnershipIdentity | None = None
    structural_ownership_change: StructuralOwnershipChangeIdentity | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate_consistency(self) -> None:
        if self.kind == "structural_relation_change":
            if (
                self.role != "structural_relation"
                or self.revision_side != "review"
                or self.profile != "structural_path"
                or self.structural_relation_change is None
                or self.operation not in {"added", "removed", "retained"}
                or self.changed != (self.operation != "retained")
            ):
                raise ValueError(
                    f"{self.id}: invalid structural relation change"
                )
        elif self.kind == "structural_ownership":
            if (
                self.role != "structural_ownership"
                or self.revision_side not in {"base", "head"}
                or self.operation != "observed"
                or self.changed
                or self.structural_ownership is None
            ):
                raise ValueError(f"{self.id}: invalid structural ownership provenance")
        elif self.kind == "structural_ownership_change":
            if (
                self.role != "structural_ownership"
                or self.revision_side != "review"
                or self.operation not in {"added", "removed", "retained"}
                or self.changed != (self.operation != "retained")
                or self.structural_ownership_change is None
            ):
                raise ValueError(f"{self.id}: invalid structural ownership change")
        elif self.changed:
            if self.kind == "structural_change":
                if self.role != "changed_anchor" or self.revision_side != "review":
                    raise ValueError(
                        f"{self.id}: structural change must be a review-level anchor"
                    )
                if self.structural_change is None:
                    raise ValueError(
                        f"{self.id}: structural change requires typed identity"
                    )
            elif self.kind == "symbol" and self.role != "revision_fact":
                raise ValueError(
                    f"{self.id}: changed symbol must be revision provenance"
                )
            elif self.kind != "symbol" and self.role != "changed_anchor":
                raise ValueError(f"{self.id}: changed fact must own changed_anchor role")
            if self.kind != "structural_change" and self.revision_side not in {
                "head",
                "base",
            }:
                raise ValueError(
                    f"{self.id}: changed revision fact must identify head or base"
                )
            changed_operations = {
                "added",
                "modified",
                "replaced",
                "removed",
                "renamed",
            }
            if self.kind == "structural_change":
                changed_operations.add("unresolved")
            if self.operation not in changed_operations:
                raise ValueError(f"{self.id}: changed fact has invalid operation")
        elif self.role == "changed_anchor":
            raise ValueError(f"{self.id}: changed_anchor role requires changed=True")
        if (
            self.operation == "removed"
            and self.revision_side != "base"
            and self.kind
            not in {
                "structural_change",
                "structural_relation_change",
                "structural_ownership_change",
            }
        ):
            raise ValueError(f"{self.id}: removed fact must belong to base revision")
        if self.kind != "structural_change" and self.structural_change is not None:
            raise ValueError(
                f"{self.id}: only structural changes may carry typed identity"
            )
        if (
            self.kind != "structural_relation_change"
            and self.structural_relation_change is not None
        ):
            raise ValueError(
                f"{self.id}: only structural relation changes may carry typed identity"
            )
        if self.kind != "structural_ownership" and self.structural_ownership is not None:
            raise ValueError(
                f"{self.id}: only structural ownership provenance may carry identity"
            )
        if (
            self.kind != "structural_ownership_change"
            and self.structural_ownership_change is not None
        ):
            raise ValueError(
                f"{self.id}: only structural ownership changes may carry identity"
            )
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
        if self.role == "boundary_fact":
            if self.authority != "guardrail_scan_provider":
                raise ValueError(
                    f"{self.id}: boundary fact requires guardrail scan authority"
                )
            if self.guardrail_scan_result is None:
                raise ValueError(f"{self.id}: boundary fact requires a scan result")
            if self.revision_side != "head" or self.operation != "observed":
                raise ValueError(
                    f"{self.id}: boundary fact must be an observed head fact"
                )
            if self.associated_statement_ids != (
                self.guardrail_scan_result.guardrail_id,
            ):
                raise ValueError(
                    f"{self.id}: boundary fact must own its G association"
                )
        elif self.guardrail_scan_result is not None:
            raise ValueError(
                f"{self.id}: only boundary facts may carry a scan result"
            )
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
    change_relations: tuple[ChangeRelation, ...] = ()
    structural_replacement_candidates: tuple[
        StructuralReplacementCandidate, ...
    ] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    guardrail_scan_diagnostics: tuple[GuardrailScanDiagnostic, ...] = ()
    schema_version: str = "evidence_catalog.v15"

    def by_id(self) -> dict[str, EvidenceItem]:
        return {item.id: item for item in self.items}

    def validate_consistency(self) -> None:
        items_by_id = self.by_id()
        if len({item.id for item in self.change_relations}) != len(
            self.change_relations
        ):
            raise ValueError("evidence catalog contains duplicate change relations")
        relation_ids = {item.id for item in self.change_relations}
        if len({item.id for item in self.structural_replacement_candidates}) != len(
            self.structural_replacement_candidates
        ):
            raise ValueError(
                "evidence catalog contains duplicate replacement candidates"
            )
        if self.structural_replacement_candidates != tuple(
            sorted(
                self.structural_replacement_candidates,
                key=lambda item: item.id,
            )
        ):
            raise ValueError("replacement candidates must use deterministic ordering")
        for candidate in self.structural_replacement_candidates:
            removed = items_by_id.get(candidate.removed_change_evidence_id)
            added = items_by_id.get(candidate.added_change_evidence_id)
            if (
                removed is None
                or removed.kind != "structural_change"
                or removed.operation != "removed"
            ):
                raise ValueError(
                    f"{candidate.id}: removed endpoint must be a removed "
                    "structural change"
                )
            if (
                added is None
                or added.kind != "structural_change"
                or added.operation != "added"
            ):
                raise ValueError(
                    f"{candidate.id}: added endpoint must be an added structural change"
                )
            if (
                removed.metadata.get("symbol_kind")
                != added.metadata.get("symbol_kind")
            ):
                raise ValueError(
                    f"{candidate.id}: replacement endpoints must share symbol kind"
                )
            unknown = set(candidate.change_relation_ids) - relation_ids
            if unknown:
                raise ValueError(
                    f"{candidate.id}: unknown replacement relation IDs: "
                    f"{sorted(unknown)}"
                )
            if any(
                relation.kind != "replaced"
                for relation in self.change_relations
                if relation.id in candidate.change_relation_ids
            ):
                raise ValueError(
                    f"{candidate.id}: replacement candidates require replaced relations"
                )
            shared = (
                set(removed.change_relation_ids)
                & set(added.change_relation_ids)
                & set(candidate.change_relation_ids)
            )
            if shared != set(candidate.change_relation_ids):
                raise ValueError(
                    f"{candidate.id}: replacement relations must be shared by endpoints"
                )
        for item in self.items:
            item.validate_consistency()
            unknown = set(item.change_relation_ids) - relation_ids
            if unknown:
                raise ValueError(
                    f"{item.id}: unknown change relation IDs: {sorted(unknown)}"
                )
            if (
                relation_ids
                and item.changed
                and item.kind in {"symbol", "change_relation", "structural_change"}
                and not item.change_relation_ids
            ):
                raise ValueError(
                    f"{item.id}: canonical changed evidence requires relation IDs"
                )
            if item.kind == "structural_path":
                for step in item.metadata.get("steps", ()):
                    for field in ("source_evidence_id", "target_evidence_id"):
                        symbol = items_by_id.get(step.get(field))
                        if symbol is None or symbol.kind != "symbol":
                            raise ValueError(
                                f"{item.id}: {field} must reference symbol evidence"
                            )
            if item.kind == "structural_change":
                identity = item.structural_change
                assert identity is not None
                symbol_ids = tuple(
                    value
                    for value in (
                        identity.base_symbol_evidence_id,
                        identity.head_symbol_evidence_id,
                    )
                    if value is not None
                )
                if not symbol_ids or any(
                    value not in items_by_id
                    or items_by_id[value].kind != "symbol"
                    for value in symbol_ids
                ):
                    raise ValueError(
                        f"{item.id}: structural change must reference symbol evidence"
                    )
                if any(
                    items_by_id[value].metadata.get("review_symbol_id")
                    != identity.review_symbol_id
                    for value in symbol_ids
                ):
                    raise ValueError(
                        f"{item.id}: structural change review identity mismatch"
                    )
                if any(
                    evidence_id is not None
                    and items_by_id[evidence_id].revision_side != revision
                    for revision, evidence_id in zip(
                        ("base", "head"),
                        (
                            identity.base_symbol_evidence_id,
                            identity.head_symbol_evidence_id,
                        ),
                        strict=True,
                    )
                ):
                    raise ValueError(
                        f"{item.id}: structural symbol revision mismatch"
                    )
            if item.kind == "structural_relation_change":
                identity = item.structural_relation_change
                assert identity is not None
                path_ids = (
                    *identity.base_path_evidence_ids,
                    *identity.head_path_evidence_ids,
                )
                if not path_ids or any(
                    value not in items_by_id
                    or items_by_id[value].kind != "structural_path"
                    for value in path_ids
                ):
                    raise ValueError(
                        f"{item.id}: structural relation change must reference "
                        "structural path evidence"
                    )
                if any(
                    items_by_id[value].revision_side != expected_revision
                    for expected_revision, values in (
                        ("base", identity.base_path_evidence_ids),
                        ("head", identity.head_path_evidence_ids),
                    )
                    for value in values
                ):
                    raise ValueError(
                        f"{item.id}: structural relation path revision mismatch"
                    )
                expected_shape = {
                    "retained": (
                        bool(identity.base_path_evidence_ids)
                        and bool(identity.head_path_evidence_ids)
                    ),
                    "added": (
                        not identity.base_path_evidence_ids
                        and bool(identity.head_path_evidence_ids)
                    ),
                    "removed": (
                        bool(identity.base_path_evidence_ids)
                        and not identity.head_path_evidence_ids
                    ),
                }
                if not expected_shape[item.operation]:
                    raise ValueError(
                        f"{item.id}: operation conflicts with revision provenance"
                    )
                if set(item.structural_path_ids) != set(path_ids):
                    raise ValueError(
                        f"{item.id}: structural path references conflict with identity"
                    )
            if item.kind == "structural_ownership":
                identity = item.structural_ownership
                assert identity is not None
                symbol_ids = (
                    identity.parent_symbol_evidence_id,
                    identity.child_symbol_evidence_id,
                )
                if any(
                    value not in items_by_id
                    or items_by_id[value].kind != "symbol"
                    or items_by_id[value].revision_side != item.revision_side
                    for value in symbol_ids
                ):
                    raise ValueError(
                        f"{item.id}: ownership must reference same-revision symbols"
                    )
                if (
                    items_by_id[identity.parent_symbol_evidence_id].metadata.get(
                        "symbol_id"
                    )
                    != identity.parent_provider_symbol_id
                    or items_by_id[identity.child_symbol_evidence_id].metadata.get(
                        "symbol_id"
                    )
                    != identity.child_provider_symbol_id
                ):
                    raise ValueError(
                        f"{item.id}: ownership endpoint identity mismatch"
                    )
            if item.kind == "structural_ownership_change":
                identity = item.structural_ownership_change
                assert identity is not None
                revision_ids = (
                    identity.base_ownership_evidence_id,
                    identity.head_ownership_evidence_id,
                )
                provenance = tuple(
                    value for value in revision_ids if value is not None
                )
                if any(
                    value not in items_by_id
                    or items_by_id[value].kind != "structural_ownership"
                    for value in provenance
                ):
                    raise ValueError(
                        f"{item.id}: ownership change must reference ownership provenance"
                    )
                if any(
                    items_by_id[value].structural_ownership is None
                    or (
                        items_by_id[
                            items_by_id[
                                value
                            ].structural_ownership.parent_symbol_evidence_id
                        ].metadata.get("review_symbol_id"),
                        items_by_id[
                            items_by_id[
                                value
                            ].structural_ownership.child_symbol_evidence_id
                        ].metadata.get("review_symbol_id"),
                    )
                    != (
                        identity.parent_review_symbol_id,
                        identity.child_review_symbol_id,
                    )
                    for value in provenance
                ):
                    raise ValueError(
                        f"{item.id}: ownership change endpoint identity mismatch"
                    )
                if any(
                    evidence_id is not None
                    and items_by_id[evidence_id].revision_side != revision
                    for revision, evidence_id in zip(
                        ("base", "head"),
                        revision_ids,
                        strict=True,
                    )
                ):
                    raise ValueError(
                        f"{item.id}: ownership provenance revision mismatch"
                    )
                expected_shape = {
                    "retained": all(revision_ids),
                    "added": (
                        identity.base_ownership_evidence_id is None
                        and identity.head_ownership_evidence_id is not None
                    ),
                    "removed": (
                        identity.base_ownership_evidence_id is not None
                        and identity.head_ownership_evidence_id is None
                    ),
                }
                if not expected_shape[item.operation]:
                    raise ValueError(
                        f"{item.id}: ownership operation conflicts with provenance"
                    )

        ownership_change_ids = tuple(
            (
                item.structural_ownership_change.parent_review_symbol_id,
                item.structural_ownership_change.child_review_symbol_id,
            )
            for item in self.items
            if item.kind == "structural_ownership_change"
            and item.structural_ownership_change is not None
        )
        if len(set(ownership_change_ids)) != len(ownership_change_ids):
            raise ValueError(
                "evidence catalog contains duplicate structural ownership identities"
            )


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
    evidence_role: FocusEvidenceRole = "primary"
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
    schema_version: str = "projection_candidate_set.v5"

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
                if (
                    relation.slot != "changed_anchor"
                    and relation.evidence_role != "primary"
                ):
                    raise ValueError(
                        f"{relation_id}: only changed anchors may carry a support role"
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
class ReviewRelevantStructuralClosure:
    """Canonical structural facts retained for one review focus."""

    path_relation_ids: tuple[str, ...] = ()
    relation_change_evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConvergenceGroup:
    focus_statement_id: str
    selected_relation_ids: tuple[str, ...] = ()
    deferred_relation_ids: tuple[str, ...] = ()
    structural_closure: ReviewRelevantStructuralClosure = (
        ReviewRelevantStructuralClosure()
    )
    diagnostic_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateConvergence:
    groups: tuple[ConvergenceGroup, ...] = ()
    diagnostics: tuple[ProjectionDiagnostic, ...] = ()
    schema_version: str = "candidate_convergence.v7"

    def diagnostics_by_id(self) -> dict[str, ProjectionDiagnostic]:
        return {item.id: item for item in self.diagnostics}

    def selected_relation_ids(self) -> tuple[str, ...]:
        return tuple(
            relation_id
            for group in self.groups
            for relation_id in group.selected_relation_ids
        )

    def validate_consistency(
        self,
        candidates: ProjectionCandidateSet,
        evidence_catalog: EvidenceCatalog,
    ) -> None:
        relations = candidates.by_id()
        evidence = evidence_catalog.by_id()
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
            closure = group.structural_closure
            support_ids = set(closure.path_relation_ids)
            if len(support_ids) != len(closure.path_relation_ids):
                raise ValueError(
                    f"{group.focus_statement_id}: duplicate structural closure path"
                )
            if support_ids != structural_selected:
                raise ValueError(
                    f"{group.focus_statement_id}: structural closure paths must equal "
                    "selected structural paths"
                )
            relation_change_ids = set(closure.relation_change_evidence_ids)
            if len(relation_change_ids) != len(
                closure.relation_change_evidence_ids
            ):
                raise ValueError(
                    f"{group.focus_statement_id}: duplicate structural closure edge"
                )
            if any(
                evidence.get(evidence_id) is None
                or evidence[evidence_id].kind != "structural_relation_change"
                for evidence_id in relation_change_ids
            ):
                raise ValueError(
                    f"{group.focus_statement_id}: structural closure references "
                    "invalid relation-change evidence"
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


StructuralFocusNodeRole = Literal[
    "changed_anchor",
    "runtime_context",
    "test_context",
    "intermediate",
]

StructuralFocusDispositionState = Literal[
    "projected",
    "non_structural_only",
    "deferred",
    "unassociated",
    "unavailable",
    "no_structural_evidence",
]


@dataclass(frozen=True)
class StructuralFocusDisposition:
    state: StructuralFocusDispositionState = "no_structural_evidence"
    non_structural_relation_ids: tuple[str, ...] = ()
    deferred_structural_relation_ids: tuple[str, ...] = ()
    diagnostic_ids: tuple[str, ...] = ()


StructuralGraphNodeDelta = Literal[
    "added",
    "modified",
    "renamed",
    "removed",
    "retained",
    "unresolved",
]


@dataclass(frozen=True)
class StructuralGraphNode:
    id: str
    review_symbol_id: str
    delta: StructuralGraphNodeDelta
    evidence_ids: tuple[str, ...]
    display_evidence_id: str
    path_relation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class StructuralGraphEdge:
    id: str
    source_node_id: str
    target_node_id: str
    relation: str
    operation: Literal["added", "removed", "retained"]
    relation_change_evidence_id: str
    path_relation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class StructuralGraphOwnershipEdge:
    id: str
    parent_node_id: str
    child_node_id: str
    operation: Literal["added", "removed", "retained"]
    ownership_change_evidence_id: str


@dataclass(frozen=True)
class StructuralGraphPlacement:
    """Observed revision-local containment for one logical parent/child pair."""

    id: str
    parent_node_id: str
    child_node_id: str
    base_ownership_evidence_ids: tuple[str, ...] = ()
    head_ownership_evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.base_ownership_evidence_ids
            and not self.head_ownership_evidence_ids
        ):
            raise ValueError(f"{self.id}: structural placement requires provenance")
        for evidence_ids in (
            self.base_ownership_evidence_ids,
            self.head_ownership_evidence_ids,
        ):
            if evidence_ids != tuple(sorted(set(evidence_ids))):
                raise ValueError(
                    f"{self.id}: structural placement provenance must be "
                    "sorted and unique"
                )
        if set(self.base_ownership_evidence_ids) & set(
            self.head_ownership_evidence_ids
        ):
            raise ValueError(
                f"{self.id}: structural placement provenance cannot cross revisions"
            )


@dataclass(frozen=True)
class ReviewStructuralGraph:
    nodes: tuple[StructuralGraphNode, ...] = ()
    edges: tuple[StructuralGraphEdge, ...] = ()
    ownership_edges: tuple[StructuralGraphOwnershipEdge, ...] = ()
    placements: tuple[StructuralGraphPlacement, ...] = ()
    backbone_node_ids: tuple[str, ...] = ()
    backbone_edge_ids: tuple[str, ...] = ()
    backbone_ownership_edge_ids: tuple[str, ...] = ()
    path_relation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class StructuralFocusNode:
    node_id: str
    role: StructuralFocusNodeRole
    relation_ids: tuple[str, ...] = ()
    path_relation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class StructuralFocusOverlay:
    nodes: tuple[StructuralFocusNode, ...] = ()
    edge_ids: tuple[str, ...] = ()
    ownership_edge_ids: tuple[str, ...] = ()
    placement_ids: tuple[str, ...] = ()
    path_relation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewSlice:
    focus_statement_id: str
    claim_relation_ids: tuple[str, ...] = ()
    standalone_changed_fact_relation_ids: tuple[str, ...] = ()
    standalone_test_support_relation_ids: tuple[str, ...] = ()
    standalone_document_support_relation_ids: tuple[str, ...] = ()
    standalone_runtime_relation_ids: tuple[str, ...] = ()
    standalone_test_relation_ids: tuple[str, ...] = ()
    verification_relation_ids: tuple[str, ...] = ()
    boundary_fact_relation_ids: tuple[str, ...] = ()
    guardrail_scan_plan_id: str | None = None
    structural_overlay: StructuralFocusOverlay = StructuralFocusOverlay()
    structural_disposition: StructuralFocusDisposition = (
        StructuralFocusDisposition()
    )
    diagnostic_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewProjection:
    slices: tuple[ReviewSlice, ...] = ()
    review_graph: ReviewStructuralGraph = ReviewStructuralGraph()
    schema_version: str = "review_projection.v18"

    def validate_consistency(
        self,
        evidence_catalog: EvidenceCatalog,
        candidates: ProjectionCandidateSet,
        convergence: CandidateConvergence,
    ) -> None:
        evidence = evidence_catalog.by_id()
        relations = candidates.by_id()
        convergence_by_focus = {
            item.focus_statement_id: item for item in convergence.groups
        }
        diagnostic_ids = {
            *(item.id for item in candidates.diagnostics),
            *(item.id for item in convergence.diagnostics),
        }
        nodes = {item.id: item for item in self.review_graph.nodes}
        edges = {item.id: item for item in self.review_graph.edges}
        ownership_edges = {
            item.id: item for item in self.review_graph.ownership_edges
        }
        placements = {
            item.id: item for item in self.review_graph.placements
        }
        if len(nodes) != len(self.review_graph.nodes):
            raise ValueError("review structural graph contains duplicate nodes")
        if len(edges) != len(self.review_graph.edges):
            raise ValueError("review structural graph contains duplicate edges")
        if len(ownership_edges) != len(self.review_graph.ownership_edges):
            raise ValueError(
                "review structural graph contains duplicate ownership edges"
            )
        if len(placements) != len(self.review_graph.placements):
            raise ValueError(
                "review structural graph contains duplicate placements"
            )
        for node in self.review_graph.nodes:
            if node.display_evidence_id not in node.evidence_ids:
                raise ValueError(
                    "review structural node display evidence is outside its "
                    "canonical evidence set"
                )
            display_fact = evidence.get(node.display_evidence_id)
            if display_fact is None:
                raise ValueError(
                    "review structural node references missing display evidence"
                )
            desired_revision = "base" if node.delta == "removed" else "head"
            revision_facts = tuple(
                evidence.get(evidence_id)
                for evidence_id in node.evidence_ids
                if evidence.get(evidence_id) is not None
                and evidence[evidence_id].revision_side == desired_revision
            )
            if (
                revision_facts
                and display_fact.revision_side != desired_revision
            ):
                raise ValueError(
                    "review structural node display evidence does not use its "
                    "canonical revision"
                )
        backbone_node_ids = set(self.review_graph.backbone_node_ids)
        backbone_edge_ids = set(self.review_graph.backbone_edge_ids)
        backbone_ownership_edge_ids = set(
            self.review_graph.backbone_ownership_edge_ids
        )
        if len(backbone_node_ids) != len(self.review_graph.backbone_node_ids):
            raise ValueError("review structural backbone contains duplicate nodes")
        if len(backbone_edge_ids) != len(self.review_graph.backbone_edge_ids):
            raise ValueError("review structural backbone contains duplicate edges")
        if len(backbone_ownership_edge_ids) != len(
            self.review_graph.backbone_ownership_edge_ids
        ):
            raise ValueError(
                "review structural backbone contains duplicate ownership edges"
            )
        if (
            not backbone_node_ids <= set(nodes)
            or not backbone_edge_ids <= set(edges)
            or not backbone_ownership_edge_ids <= set(ownership_edges)
        ):
            raise ValueError(
                "review structural backbone references members outside the graph"
            )
        if any(
            edges[edge_id].source_node_id not in backbone_node_ids
            or edges[edge_id].target_node_id not in backbone_node_ids
            for edge_id in backbone_edge_ids
        ):
            raise ValueError(
                "review structural backbone edge endpoints must be backbone nodes"
            )
        if any(
            ownership_edges[edge_id].parent_node_id not in backbone_node_ids
            or ownership_edges[edge_id].child_node_id not in backbone_node_ids
            for edge_id in backbone_ownership_edge_ids
        ):
            raise ValueError(
                "review structural backbone ownership endpoints must be "
                "backbone nodes"
            )
        for edge in self.review_graph.edges:
            if edge.source_node_id not in nodes or edge.target_node_id not in nodes:
                raise ValueError("review structural edge references a missing node")
            fact = evidence.get(edge.relation_change_evidence_id)
            if fact is None or fact.kind != "structural_relation_change":
                raise ValueError(
                    "review structural edge references invalid relation evidence"
                )
        ownership_pairs: set[tuple[str, str]] = set()
        ownership_children: dict[str, set[str]] = {}
        for edge in self.review_graph.ownership_edges:
            if edge.parent_node_id not in nodes or edge.child_node_id not in nodes:
                raise ValueError("review ownership edge references a missing node")
            fact = evidence.get(edge.ownership_change_evidence_id)
            identity = (
                fact.structural_ownership_change if fact is not None else None
            )
            if (
                fact is None
                or fact.kind != "structural_ownership_change"
                or identity is None
                or fact.operation != edge.operation
                or nodes[edge.parent_node_id].review_symbol_id
                != identity.parent_review_symbol_id
                or nodes[edge.child_node_id].review_symbol_id
                != identity.child_review_symbol_id
            ):
                raise ValueError(
                    "review ownership edge references invalid ownership evidence"
                )
            pair = (edge.parent_node_id, edge.child_node_id)
            if pair in ownership_pairs:
                raise ValueError(
                    "review structural graph contains duplicate ownership identity"
                )
            ownership_pairs.add(pair)
            ownership_children.setdefault(edge.parent_node_id, set()).add(
                edge.child_node_id
            )
        for start in ownership_children:
            frontier = list(ownership_children[start])
            visited: set[str] = set()
            while frontier:
                current = frontier.pop()
                if current == start:
                    raise ValueError("review structural ownership contains a cycle")
                if current in visited:
                    continue
                visited.add(current)
                frontier.extend(ownership_children.get(current, ()))
        placement_pairs: set[tuple[str, str]] = set()
        placement_children: dict[str, set[str]] = {}
        for placement in self.review_graph.placements:
            if (
                placement.parent_node_id not in nodes
                or placement.child_node_id not in nodes
            ):
                raise ValueError("review structural placement references a missing node")
            pair = (placement.parent_node_id, placement.child_node_id)
            if pair in placement_pairs:
                raise ValueError(
                    "review structural graph contains duplicate placement identity"
                )
            placement_pairs.add(pair)
            placement_children.setdefault(
                placement.parent_node_id, set()
            ).add(placement.child_node_id)
            for revision, evidence_ids in (
                ("base", placement.base_ownership_evidence_ids),
                ("head", placement.head_ownership_evidence_ids),
            ):
                for evidence_id in evidence_ids:
                    fact = evidence.get(evidence_id)
                    identity = (
                        fact.structural_ownership if fact is not None else None
                    )
                    if (
                        fact is None
                        or fact.kind != "structural_ownership"
                        or fact.revision_side != revision
                        or identity is None
                    ):
                        raise ValueError(
                            "review structural placement references invalid "
                            "ownership provenance"
                        )
                    parent = evidence.get(identity.parent_symbol_evidence_id)
                    child = evidence.get(identity.child_symbol_evidence_id)
                    if (
                        parent is None
                        or child is None
                        or nodes[placement.parent_node_id].review_symbol_id
                        != parent.metadata.get("review_symbol_id")
                        or nodes[placement.child_node_id].review_symbol_id
                        != child.metadata.get("review_symbol_id")
                    ):
                        raise ValueError(
                            "review structural placement provenance identity mismatch"
                        )
        for start in placement_children:
            frontier = list(placement_children[start])
            visited: set[str] = set()
            while frontier:
                current = frontier.pop()
                if current == start:
                    raise ValueError("review structural placement contains a cycle")
                if current in visited:
                    continue
                visited.add(current)
                frontier.extend(placement_children.get(current, ()))
        for review_slice in self.slices:
            overlay = review_slice.structural_overlay
            disposition = review_slice.structural_disposition
            converged = convergence_by_focus.get(review_slice.focus_statement_id)
            if converged is None:
                raise ValueError(
                    f"{review_slice.focus_statement_id}: structural disposition "
                    "has no convergence group"
                )
            selected_ids = set(converged.selected_relation_ids)
            deferred_ids = set(converged.deferred_relation_ids)
            if any(
                relation_id not in relations
                or relations[relation_id].focus_statement_id
                != review_slice.focus_statement_id
                for relation_id in (
                    *disposition.non_structural_relation_ids,
                    *disposition.deferred_structural_relation_ids,
                )
            ):
                raise ValueError(
                    f"{review_slice.focus_statement_id}: structural disposition "
                    "references an invalid relation"
                )
            if not set(disposition.non_structural_relation_ids) <= selected_ids:
                raise ValueError(
                    f"{review_slice.focus_statement_id}: non-structural disposition "
                    "must reference selected relations"
                )
            if not set(disposition.deferred_structural_relation_ids) <= deferred_ids:
                raise ValueError(
                    f"{review_slice.focus_statement_id}: deferred structural "
                    "disposition must reference deferred relations"
                )
            if any(
                item not in diagnostic_ids
                for item in disposition.diagnostic_ids
            ):
                raise ValueError(
                    f"{review_slice.focus_statement_id}: structural disposition "
                    "references an invalid diagnostic"
                )
            if any(
                placement_id not in placements
                for placement_id in overlay.placement_ids
            ):
                raise ValueError(
                    f"{review_slice.focus_statement_id}: structural overlay "
                    "references missing placement"
                )
            if (disposition.state == "projected") != bool(overlay.nodes):
                raise ValueError(
                    f"{review_slice.focus_statement_id}: projected disposition "
                    "must agree with the structural overlay"
                )
            overlay_node_ids = {item.node_id for item in overlay.nodes}
            if len(overlay_node_ids) != len(overlay.nodes):
                raise ValueError(
                    f"{review_slice.focus_statement_id}: overlay contains "
                    "duplicate structural nodes"
                )
            if any(node_id not in nodes for node_id in overlay_node_ids):
                raise ValueError(
                    f"{review_slice.focus_statement_id}: overlay references "
                    "a missing structural node"
                )
            if any(edge_id not in edges for edge_id in overlay.edge_ids):
                raise ValueError(
                    f"{review_slice.focus_statement_id}: overlay references "
                    "a missing structural edge"
                )
            if any(
                edge_id not in ownership_edges
                for edge_id in overlay.ownership_edge_ids
            ):
                raise ValueError(
                    f"{review_slice.focus_statement_id}: overlay references "
                    "a missing ownership edge"
                )
            if any(
                edges[edge_id].source_node_id not in overlay_node_ids
                or edges[edge_id].target_node_id not in overlay_node_ids
                for edge_id in overlay.edge_ids
            ):
                raise ValueError(
                    f"{review_slice.focus_statement_id}: structural edge "
                    "endpoints must belong to the overlay"
                )
            if any(
                ownership_edges[edge_id].parent_node_id not in overlay_node_ids
                or ownership_edges[edge_id].child_node_id not in overlay_node_ids
                for edge_id in overlay.ownership_edge_ids
            ):
                raise ValueError(
                    f"{review_slice.focus_statement_id}: ownership edge "
                    "endpoints must belong to the overlay"
                )


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
class FocusDiagnosticPresentation:
    focus_statement_id: str
    diagnostic_ids: tuple[str, ...]


@dataclass(frozen=True)
class DiagnosticPresentation:
    """Canonical display disposition for typed projection diagnostics."""

    focus: tuple[FocusDiagnosticPresentation, ...] = ()
    attention: tuple[ReviewAttention, ...] = ()
    suppressed_diagnostic_ids: tuple[str, ...] = ()

    def ids_by_focus(self) -> dict[str, tuple[str, ...]]:
        return {
            item.focus_statement_id: item.diagnostic_ids
            for item in self.focus
        }


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
    seed_count: int = 0
    complete_seed_count: int = 0
    truncated_seed_count: int = 0
    requested_files: int = 0
    indexed_files: int = 0
    missing_reason: Literal["index_absent", "files_unindexed", ""] = ""
    base_state: StructuralCoverageState = "unavailable"
    base_mapped_hunk_count: int = 0
    base_hunk_count: int = 0
    base_symbol_count: int = 0


@dataclass(frozen=True)
class AnalysisInput:
    packet: ReviewSourcePacket
    requirements: tuple[Requirement, ...] = ()
    changes: DiffHunkCollection | None = None
    structural_graph: StructuralGraphCollection | None = None
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
    verification_expectations: tuple[ReviewStatement, ...] = ()
    claims: tuple[ReviewStatement, ...] = ()
    guardrail_scan_plans: GuardrailScanPlanSet = GuardrailScanPlanSet()
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
    schema_version: str = "review_brief.v32"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
