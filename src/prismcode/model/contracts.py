from __future__ import annotations

import hashlib
import json
import unicodedata
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
TransformationClaimKind = Literal[
    "change",
    "before_state",
    "after_state",
    "selected_region",
    "input_boundary",
    "output_boundary",
    "boundary",
    "before_topology",
    "after_topology",
    "authority",
    "production_path",
    "migration",
    "producer_migration",
    "consumer_migration",
    "test_migration",
    "removal",
    "completion_condition",
    "uncertainty",
]
TransformationContractSourceState = Literal[
    "source_absent",
    "extraction_missing",
    "available",
]
TransformationPredicateSelectorKind = Literal[
    "symbol",
    "repository_path",
    "ordered_path",
]
TransformationPredicateRole = Literal["target", "path_scope"]
TransformationPredicateExpectation = Literal[
    "reference",
    "present_base",
    "present_head",
    "absent_head",
    "verified_head",
]
TransformationSubjectSelectionState = Literal[
    "no_structural_match",
]
TransformationStructuralClosureState = Literal["budget_truncated"]
StructuralTraversalCoverageState = Literal["complete", "truncated", "unknown"]
TransformationEvidenceRole = Literal[
    "change",
    "relation_change",
    "ownership_change",
    "structural_path",
    "verification",
    "closure",
]
TransformationAlignmentCoverageState = Literal[
    "no_eligible_fact",
    "no_association",
]
TransformationAssessmentStatus = Literal[
    "demonstrated",
    "partial",
    "contradicted",
    "unverified",
]
TransformationAssessmentReasonKind = Literal[
    "exact_fact_observed",
    "association_only",
    "closure_transition_observed",
    "closure_absence_observed",
    "closure_conflict_observed",
    "current_verification_success",
    "current_verification_failure",
    "verification_incomplete",
    "stale_verification",
    "coverage_incomplete",
    "no_binding",
    "generic_transition_context",
    "uncertainty_context",
    "authority_path_observed",
    "authority_bypass_observed",
    "migration_closure_observed",
    "migration_component_incomplete",
    "migration_component_conflict",
    "migration_scope_ambiguous",
]
VerificationSubjectKind = Literal[
    "requirement",
    "guardrail",
    "transformation_claim",
    "completion_condition",
]
VerificationProjectionStatus = Literal[
    "not_assessed",
    "demonstrated",
    "partial",
    "contradicted",
    "unverified",
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
    "closure_scan_provider",
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
    "closure_fact",
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
    "closure_fact",
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
ClosureScanSurface = Literal["paths", "file_content", "symbol_names"]
ClosureScanState = Literal["complete", "partial", "unavailable"]
ClosureSelectorKind = Literal["identifier", "path", "phrase"]
ClosureStatementKind = Literal[
    "guardrail",
    "removal",
    "completion_condition",
]
ClosureExpectation = Literal["absence", "transition"]
ClosureScanBoundaryKind = Literal["file_limit", "byte_limit", "match_limit"]
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

    def __post_init__(self) -> None:
        if self.name != canonical_verification_name(self.name):
            raise ValueError("verification identity name must be canonical")


def canonical_verification_name(value: str) -> str:
    """Preserve check-name punctuation while normalizing case and whitespace."""

    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split()).casefold()


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
class TransformationClaim:
    """One typed PR-authored transformation assertion, never an observation."""

    id: str
    kind: TransformationClaimKind
    text: str
    authority: Literal["pr_description"] = "pr_description"
    sources: tuple[SourceRef, ...] = ()

    def validate_consistency(self) -> None:
        expected_prefix = "CC" if self.kind == "completion_condition" else "T"
        numeric_id = self.id[len(expected_prefix) :]
        if (
            not self.id.startswith(expected_prefix)
            or not numeric_id.isdigit()
            or int(numeric_id) < 1
        ):
            raise ValueError(
                f"{self.id}: {self.kind} requires {expected_prefix} identity"
            )
        if self.authority != "pr_description":
            raise ValueError(
                f"{self.id}: transformation claim must remain PR-authored"
            )
        if not self.text.strip():
            raise ValueError(f"{self.id}: transformation claim requires text")
        if not self.sources:
            raise ValueError(
                f"{self.id}: transformation claim requires source provenance"
            )


@dataclass(frozen=True)
class TransformationPredicate:
    """One explicit PR-authored selector predicate, never an observation."""

    id: str
    claim_id: str
    selector_kind: TransformationPredicateSelectorKind
    values: tuple[str, ...]
    expectation: TransformationPredicateExpectation
    role: TransformationPredicateRole = "target"
    sources: tuple[SourceRef, ...] = ()

    def validate_consistency(self) -> None:
        if self.id != f"TP:{self.claim_id}:{self.id.rsplit(':', 1)[-1]}":
            raise ValueError(f"{self.id}: non-canonical predicate ID")
        ordinal = self.id.rsplit(":", 1)[-1]
        if not ordinal.isdigit() or int(ordinal) < 1:
            raise ValueError(f"{self.id}: predicate requires positive ordinal")
        if not self.values or any(not item.strip() for item in self.values):
            raise ValueError(f"{self.id}: predicate requires selector values")
        if (
            self.selector_kind != "ordered_path"
            and len(self.values) != len(set(self.values))
        ):
            raise ValueError(f"{self.id}: predicate values must be unique")
        if self.selector_kind == "ordered_path" and len(self.values) < 2:
            raise ValueError(f"{self.id}: ordered path requires two selectors")
        if self.role == "path_scope" and self.selector_kind != "repository_path":
            raise ValueError(f"{self.id}: path scope requires repository path")
        if self.selector_kind != "ordered_path" and len(self.values) != 1:
            raise ValueError(f"{self.id}: scalar predicate requires one selector")
        if not self.sources:
            raise ValueError(f"{self.id}: predicate requires source provenance")


@dataclass(frozen=True)
class TransformationPredicateDiagnostic:
    id: str
    claim_id: str
    state: Literal["no_explicit_selector"]
    message: str

    def validate_consistency(self) -> None:
        if self.id != f"TPD:{self.claim_id}:{self.state}":
            raise ValueError(f"{self.id}: non-canonical predicate diagnostic ID")
        if not self.message.strip():
            raise ValueError(f"{self.id}: predicate diagnostic requires a message")


@dataclass(frozen=True)
class TransformationPredicateSet:
    predicates: tuple[TransformationPredicate, ...] = ()
    diagnostics: tuple[TransformationPredicateDiagnostic, ...] = ()
    schema_version: str = "transformation_predicate_set.v2"

    def by_claim_id(self) -> dict[str, tuple[TransformationPredicate, ...]]:
        return {
            claim_id: tuple(
                item for item in self.predicates if item.claim_id == claim_id
            )
            for claim_id in dict.fromkeys(item.claim_id for item in self.predicates)
        }

    def validate_consistency(self, claim_ids: set[str]) -> None:
        if self.schema_version != "transformation_predicate_set.v2":
            raise ValueError("unsupported transformation predicate schema")
        ids = tuple(item.id for item in self.predicates)
        diagnostic_ids = tuple(item.id for item in self.diagnostics)
        if (
            len(ids) != len(set(ids))
            or len(diagnostic_ids) != len(set(diagnostic_ids))
        ):
            raise ValueError("transformation predicates contain duplicate IDs")
        for item in self.predicates:
            item.validate_consistency()
        for item in self.diagnostics:
            item.validate_consistency()
        referenced = {
            *(item.claim_id for item in self.predicates),
            *(item.claim_id for item in self.diagnostics),
        }
        if not referenced <= claim_ids:
            raise ValueError("transformation predicates reference unknown claims")
        predicate_claims = {item.claim_id for item in self.predicates}
        diagnostic_claims = {item.claim_id for item in self.diagnostics}
        if predicate_claims & diagnostic_claims:
            raise ValueError(
                "one claim cannot have predicates and missing-selector diagnostics"
            )


@dataclass(frozen=True)
class TransformationSubjectMatch:
    """One exact selector value to canonical changed-structure identity."""

    id: str
    claim_id: str
    predicate_id: str
    selector_index: int
    selector_value: str
    evidence_id: str


@dataclass(frozen=True)
class TransformationSubjectDiagnostic:
    id: str
    claim_id: str
    predicate_id: str
    selector_index: int
    state: TransformationSubjectSelectionState
    message: str


@dataclass(frozen=True)
class TransformationSubjectSelection:
    """Canonical explicit-selector matches, before structural closure."""

    matches: tuple[TransformationSubjectMatch, ...] = ()
    diagnostics: tuple[TransformationSubjectDiagnostic, ...] = ()
    schema_version: str = "transformation_subject_selection.v1"

    def by_claim_id(self) -> dict[str, tuple[TransformationSubjectMatch, ...]]:
        return {
            claim_id: tuple(item for item in self.matches if item.claim_id == claim_id)
            for claim_id in dict.fromkeys(item.claim_id for item in self.matches)
        }

    def validate_consistency(
        self,
        contract: TransformationContract,
        observed: ObservedTransformation,
        evidence_catalog: EvidenceCatalog,
    ) -> None:
        if self.schema_version != "transformation_subject_selection.v1":
            raise ValueError("unsupported transformation subject selection schema")
        predicates = {
            item.id: item
            for item in contract.predicates.predicates
            if item.role == "target"
        }
        evidence = evidence_catalog.by_id()
        observed_ids = set(observed.structural_change_evidence_ids)
        identities = tuple(
            (item.predicate_id, item.selector_index, item.evidence_id)
            for item in self.matches
        )
        if len(identities) != len(set(identities)):
            raise ValueError("transformation subject selection contains duplicates")
        diagnostic_keys = tuple(
            (item.predicate_id, item.selector_index) for item in self.diagnostics
        )
        if len(diagnostic_keys) != len(set(diagnostic_keys)):
            raise ValueError("transformation subject diagnostics contain duplicates")
        matched_keys = {
            (item.predicate_id, item.selector_index) for item in self.matches
        }
        if matched_keys & set(diagnostic_keys):
            raise ValueError("one selector cannot be both matched and diagnostic")
        expected_keys = {
            (predicate.id, index)
            for predicate in predicates.values()
            for index in range(1, len(predicate.values) + 1)
        }
        if matched_keys | set(diagnostic_keys) != expected_keys:
            raise ValueError(
                "subject selection must cover every predicate selector once"
            )
        for item in self.matches:
            predicate = predicates.get(item.predicate_id)
            fact = evidence.get(item.evidence_id)
            if (
                predicate is None
                or item.claim_id != predicate.claim_id
                or item.selector_index < 1
                or item.selector_index > len(predicate.values)
                or item.selector_value != predicate.values[item.selector_index - 1]
                or fact is None
                or fact.kind != "structural_change"
                or item.evidence_id not in observed_ids
            ):
                raise ValueError(f"{item.id}: invalid structural subject match")
            if item.id != (
                f"TSM:{item.predicate_id}:{item.selector_index}:{item.evidence_id}"
            ):
                raise ValueError(f"{item.id}: non-canonical subject match ID")
        for item in self.diagnostics:
            predicate = predicates.get(item.predicate_id)
            if (
                predicate is None
                or item.claim_id != predicate.claim_id
                or item.selector_index < 1
                or item.selector_index > len(predicate.values)
                or not item.message.strip()
                or item.state != "no_structural_match"
            ):
                raise ValueError(f"{item.id}: invalid subject diagnostic")
            if item.id != (
                f"TSD:{item.predicate_id}:{item.selector_index}:{item.state}"
            ):
                raise ValueError(f"{item.id}: non-canonical subject diagnostic ID")


@dataclass(frozen=True)
class TransformationStructuralClosureGroup:
    """Collected structural support reachable from one claim's selected seeds."""

    claim_id: str
    subject_match_ids: tuple[str, ...] = ()
    seed_evidence_ids: tuple[str, ...] = ()
    path_evidence_ids: tuple[str, ...] = ()
    deferred_path_evidence_ids: tuple[str, ...] = ()
    review_symbol_ids: tuple[str, ...] = ()
    relation_change_evidence_ids: tuple[str, ...] = ()
    ownership_change_evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TransformationStructuralClosureDiagnostic:
    id: str
    claim_id: str
    state: TransformationStructuralClosureState
    message: str
    affected_evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TransformationStructuralClosure:
    groups: tuple[TransformationStructuralClosureGroup, ...] = ()
    diagnostics: tuple[TransformationStructuralClosureDiagnostic, ...] = ()
    schema_version: str = "transformation_structural_closure.v1"

    def by_claim_id(self) -> dict[str, TransformationStructuralClosureGroup]:
        return {item.claim_id: item for item in self.groups}

    def validate_consistency(
        self,
        contract: TransformationContract,
        selection: TransformationSubjectSelection,
        evidence_catalog: EvidenceCatalog,
    ) -> None:
        if self.schema_version != "transformation_structural_closure.v1":
            raise ValueError("unsupported transformation structural closure schema")
        claim_ids = tuple(item.id for item in contract.claims)
        if tuple(item.claim_id for item in self.groups) != claim_ids:
            raise ValueError("transformation closure must preserve every claim once")
        evidence = evidence_catalog.by_id()
        matches = {item.id: item for item in selection.matches}
        diagnostics_by_claim = {item.claim_id: item for item in self.diagnostics}
        if len(diagnostics_by_claim) != len(self.diagnostics):
            raise ValueError("transformation closure contains duplicate diagnostics")
        for group in self.groups:
            expected_matches = tuple(
                item.id for item in selection.matches if item.claim_id == group.claim_id
            )
            if group.subject_match_ids != expected_matches:
                raise ValueError(f"{group.claim_id}: closure match identities conflict")
            expected_seeds = tuple(
                dict.fromkeys(matches[item].evidence_id for item in expected_matches)
            )
            if group.seed_evidence_ids != expected_seeds:
                raise ValueError(f"{group.claim_id}: closure seed identities conflict")
            selected_paths = set(group.path_evidence_ids)
            deferred_paths = set(group.deferred_path_evidence_ids)
            if (
                len(selected_paths) != len(group.path_evidence_ids)
                or len(deferred_paths) != len(group.deferred_path_evidence_ids)
                or selected_paths & deferred_paths
            ):
                raise ValueError(f"{group.claim_id}: invalid closure path partition")
            candidate_paths = {
                path_id
                for seed_id in group.seed_evidence_ids
                for path_id in evidence[seed_id].structural_path_ids
                if path_id in evidence and evidence[path_id].kind == "structural_path"
            }
            if selected_paths | deferred_paths != candidate_paths:
                raise ValueError(f"{group.claim_id}: closure paths are incomplete")
            review_ids = set(group.review_symbol_ids)
            if len(review_ids) != len(group.review_symbol_ids):
                raise ValueError(f"{group.claim_id}: duplicate closure symbol identity")
            expected_relation_ids = {
                item.id
                for item in evidence.values()
                if item.structural_relation_change is not None
                and selected_paths
                & {
                    *item.structural_path_ids,
                    *item.structural_relation_change.base_path_evidence_ids,
                    *item.structural_relation_change.head_path_evidence_ids,
                }
            }
            if set(group.relation_change_evidence_ids) != expected_relation_ids:
                raise ValueError(
                    f"{group.claim_id}: closure relation evidence is incomplete"
                )
            for field_name, ids, expected_kind in (
                (
                    "relation",
                    group.relation_change_evidence_ids,
                    "structural_relation_change",
                ),
                (
                    "ownership",
                    group.ownership_change_evidence_ids,
                    "structural_ownership_change",
                ),
            ):
                if len(ids) != len(set(ids)) or any(
                    item_id not in evidence or evidence[item_id].kind != expected_kind
                    for item_id in ids
                ):
                    raise ValueError(
                        f"{group.claim_id}: invalid closure {field_name} evidence"
                    )
            relation_endpoints = {
                endpoint
                for item_id in group.relation_change_evidence_ids
                for endpoint in (
                    evidence[
                        item_id
                    ].structural_relation_change.source_review_symbol_id,
                    evidence[
                        item_id
                    ].structural_relation_change.target_review_symbol_id,
                )
                if evidence[item_id].structural_relation_change is not None
            }
            ownership_endpoints = {
                endpoint
                for item_id in group.ownership_change_evidence_ids
                for endpoint in (
                    evidence[
                        item_id
                    ].structural_ownership_change.parent_review_symbol_id,
                    evidence[
                        item_id
                    ].structural_ownership_change.child_review_symbol_id,
                )
                if evidence[item_id].structural_ownership_change is not None
            }
            if not (relation_endpoints | ownership_endpoints) <= review_ids:
                raise ValueError(
                    f"{group.claim_id}: closure endpoints are missing symbols"
                )
            diagnostic = diagnostics_by_claim.get(group.claim_id)
            if bool(group.deferred_path_evidence_ids) != bool(diagnostic):
                raise ValueError(
                    f"{group.claim_id}: deferred closure paths require one diagnostic"
                )
        for item in self.diagnostics:
            if (
                item.id != f"TSCD:{item.claim_id}:{item.state}"
                or item.state != "budget_truncated"
                or not item.message.strip()
                or item.claim_id not in claim_ids
                or item.affected_evidence_ids
                != self.by_claim_id()[item.claim_id].deferred_path_evidence_ids
            ):
                raise ValueError(f"{item.id}: invalid transformation closure diagnostic")


@dataclass(frozen=True)
class TransformationRegion:
    selected_claim_ids: tuple[str, ...] = ()
    input_boundary_claim_ids: tuple[str, ...] = ()
    output_boundary_claim_ids: tuple[str, ...] = ()
    boundary_claim_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TransformationTopology:
    before_claim_ids: tuple[str, ...] = ()
    after_claim_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TransformationStateTransition:
    """Authored before/after state without an inferred semantic subtype."""

    before_claim_ids: tuple[str, ...] = ()
    after_claim_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TransformationMigration:
    general_claim_ids: tuple[str, ...] = ()
    producer_claim_ids: tuple[str, ...] = ()
    consumer_claim_ids: tuple[str, ...] = ()
    test_claim_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TransformationContract:
    """Canonical typed claims extracted from one PR description."""

    claims: tuple[TransformationClaim, ...] = ()
    predicates: TransformationPredicateSet = TransformationPredicateSet()
    change_claim_ids: tuple[str, ...] = ()
    state_transition: TransformationStateTransition = TransformationStateTransition()
    region: TransformationRegion = TransformationRegion()
    topology: TransformationTopology = TransformationTopology()
    authority_claim_ids: tuple[str, ...] = ()
    production_path_claim_ids: tuple[str, ...] = ()
    migration: TransformationMigration = TransformationMigration()
    removal_claim_ids: tuple[str, ...] = ()
    completion_condition_claim_ids: tuple[str, ...] = ()
    uncertainty_claim_ids: tuple[str, ...] = ()
    source_state: TransformationContractSourceState = "source_absent"
    schema_version: str = "transformation_contract.v4"

    def by_kind(
        self,
        kind: TransformationClaimKind,
    ) -> tuple[TransformationClaim, ...]:
        return tuple(item for item in self.claims if item.kind == kind)

    def validate_consistency(self) -> None:
        if self.schema_version != "transformation_contract.v4":
            raise ValueError(
                f"unsupported transformation contract schema: {self.schema_version}"
            )
        ids = tuple(item.id for item in self.claims)
        if len(ids) != len(set(ids)):
            raise ValueError("transformation contract contains duplicate claim IDs")
        for item in self.claims:
            item.validate_consistency()
        self.predicates.validate_consistency(set(ids))
        if (self.source_state == "available") != bool(self.claims):
            raise ValueError(
                "available transformation contract must contain typed claims"
            )
        references_by_kind = {
            "change": self.change_claim_ids,
            "before_state": self.state_transition.before_claim_ids,
            "after_state": self.state_transition.after_claim_ids,
            "selected_region": self.region.selected_claim_ids,
            "input_boundary": self.region.input_boundary_claim_ids,
            "output_boundary": self.region.output_boundary_claim_ids,
            "boundary": self.region.boundary_claim_ids,
            "before_topology": self.topology.before_claim_ids,
            "after_topology": self.topology.after_claim_ids,
            "authority": self.authority_claim_ids,
            "production_path": self.production_path_claim_ids,
            "migration": self.migration.general_claim_ids,
            "producer_migration": self.migration.producer_claim_ids,
            "consumer_migration": self.migration.consumer_claim_ids,
            "test_migration": self.migration.test_claim_ids,
            "removal": self.removal_claim_ids,
            "completion_condition": self.completion_condition_claim_ids,
            "uncertainty": self.uncertainty_claim_ids,
        }
        referenced_ids = tuple(
            claim_id
            for claim_ids in references_by_kind.values()
            for claim_id in claim_ids
        )
        if len(referenced_ids) != len(set(referenced_ids)):
            raise ValueError(
                "transformation contract groups contain duplicate claim references"
            )
        if set(referenced_ids) != set(ids):
            raise ValueError(
                "transformation contract groups must reference every claim once"
            )
        claims_by_id = {item.id: item for item in self.claims}
        for kind, claim_ids in references_by_kind.items():
            if any(claims_by_id[item].kind != kind for item in claim_ids):
                raise ValueError(
                    f"transformation contract group conflicts with {kind} claim kind"
                )


@dataclass(frozen=True)
class ObservedTopology:
    """Base/Head membership of canonical structural facts."""

    base_symbol_change_evidence_ids: tuple[str, ...] = ()
    head_symbol_change_evidence_ids: tuple[str, ...] = ()
    base_relation_change_evidence_ids: tuple[str, ...] = ()
    head_relation_change_evidence_ids: tuple[str, ...] = ()
    base_ownership_change_evidence_ids: tuple[str, ...] = ()
    head_ownership_change_evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ObservedTransformation:
    """Claim-independent reconstruction, never an assessment or conclusion."""

    structural_change_evidence_ids: tuple[str, ...] = ()
    fallback_change_evidence_ids: tuple[str, ...] = ()
    relation_change_evidence_ids: tuple[str, ...] = ()
    ownership_change_evidence_ids: tuple[str, ...] = ()
    replacement_candidate_ids: tuple[str, ...] = ()
    structural_path_evidence_ids: tuple[str, ...] = ()
    verification_evidence_ids: tuple[str, ...] = ()
    topology: ObservedTopology = ObservedTopology()
    schema_version: str = "observed_transformation.v1"

    def evidence_ids(self) -> tuple[str, ...]:
        """Canonical observed evidence identities, excluding non-fact candidates."""

        return tuple(
            dict.fromkeys(
                (
                    *self.structural_change_evidence_ids,
                    *self.fallback_change_evidence_ids,
                    *self.relation_change_evidence_ids,
                    *self.ownership_change_evidence_ids,
                    *self.structural_path_evidence_ids,
                    *self.verification_evidence_ids,
                )
            )
        )

    def validate_consistency(self, evidence_catalog: EvidenceCatalog) -> None:
        if self.schema_version != "observed_transformation.v1":
            raise ValueError(
                f"unsupported observed transformation schema: {self.schema_version}"
            )
        structural_changes = tuple(
            item
            for item in evidence_catalog.items
            if item.kind == "structural_change"
        )
        relation_changes = tuple(
            item
            for item in evidence_catalog.items
            if item.kind == "structural_relation_change"
        )
        ownership_changes = tuple(
            item
            for item in evidence_catalog.items
            if item.kind == "structural_ownership_change"
        )
        changed_anchors = tuple(
            item
            for item in evidence_catalog.items
            if item.changed and item.role == "changed_anchor"
        )
        expected = {
            "structural_change_evidence_ids": tuple(
                item.id for item in structural_changes
            ),
            "fallback_change_evidence_ids": tuple(
                item.id
                for item in changed_anchors
                if item.kind != "structural_change"
            ),
            "relation_change_evidence_ids": tuple(
                item.id for item in relation_changes
            ),
            "ownership_change_evidence_ids": tuple(
                item.id for item in ownership_changes
            ),
            "replacement_candidate_ids": tuple(
                item.id
                for item in evidence_catalog.structural_replacement_candidates
            ),
            "structural_path_evidence_ids": tuple(
                item.id
                for item in evidence_catalog.items
                if item.kind == "structural_path"
            ),
            "verification_evidence_ids": tuple(
                item.id
                for item in evidence_catalog.items
                if item.role == "verification"
            ),
            "base_symbol_change_evidence_ids": tuple(
                item.id
                for item in structural_changes
                if item.structural_change is not None
                and item.structural_change.base_symbol_evidence_id is not None
            ),
            "head_symbol_change_evidence_ids": tuple(
                item.id
                for item in structural_changes
                if item.structural_change is not None
                and item.structural_change.head_symbol_evidence_id is not None
            ),
            "base_relation_change_evidence_ids": tuple(
                item.id
                for item in relation_changes
                if item.structural_relation_change is not None
                and item.structural_relation_change.base_path_evidence_ids
            ),
            "head_relation_change_evidence_ids": tuple(
                item.id
                for item in relation_changes
                if item.structural_relation_change is not None
                and item.structural_relation_change.head_path_evidence_ids
            ),
            "base_ownership_change_evidence_ids": tuple(
                item.id
                for item in ownership_changes
                if item.structural_ownership_change is not None
                and (
                    item.structural_ownership_change.base_ownership_evidence_id
                    is not None
                )
            ),
            "head_ownership_change_evidence_ids": tuple(
                item.id
                for item in ownership_changes
                if item.structural_ownership_change is not None
                and (
                    item.structural_ownership_change.head_ownership_evidence_id
                    is not None
                )
            ),
        }
        actual = {
            "structural_change_evidence_ids": self.structural_change_evidence_ids,
            "fallback_change_evidence_ids": self.fallback_change_evidence_ids,
            "relation_change_evidence_ids": self.relation_change_evidence_ids,
            "ownership_change_evidence_ids": self.ownership_change_evidence_ids,
            "replacement_candidate_ids": self.replacement_candidate_ids,
            "structural_path_evidence_ids": self.structural_path_evidence_ids,
            "verification_evidence_ids": self.verification_evidence_ids,
            "base_symbol_change_evidence_ids": (
                self.topology.base_symbol_change_evidence_ids
            ),
            "head_symbol_change_evidence_ids": (
                self.topology.head_symbol_change_evidence_ids
            ),
            "base_relation_change_evidence_ids": (
                self.topology.base_relation_change_evidence_ids
            ),
            "head_relation_change_evidence_ids": (
                self.topology.head_relation_change_evidence_ids
            ),
            "base_ownership_change_evidence_ids": (
                self.topology.base_ownership_change_evidence_ids
            ),
            "head_ownership_change_evidence_ids": (
                self.topology.head_ownership_change_evidence_ids
            ),
        }
        for field_name, expected_ids in expected.items():
            if actual[field_name] != expected_ids:
                raise ValueError(
                    f"observed transformation {field_name} conflicts with "
                    "canonical evidence"
                )
            if len(actual[field_name]) != len(set(actual[field_name])):
                raise ValueError(
                    f"observed transformation {field_name} contains duplicates"
                )
        structural_ids = set(self.structural_change_evidence_ids)
        fallback_ids = set(self.fallback_change_evidence_ids)
        if structural_ids & fallback_ids:
            raise ValueError(
                "observed structural and fallback change lanes must be disjoint"
            )
        changed_anchor_ids = {
            item.id
            for item in evidence_catalog.items
            if item.changed and item.role == "changed_anchor"
        }
        if structural_ids | fallback_ids != changed_anchor_ids:
            raise ValueError(
                "observed change lanes must partition canonical changed anchors"
            )


@dataclass(frozen=True)
class TransformationEvidenceBinding:
    """One deterministic relevance edge, never an assessment."""

    id: str
    claim_id: str
    evidence_id: str
    evidence_role: TransformationEvidenceRole
    association: AssociationKind
    reasons: tuple[AssociationReason, ...]


@dataclass(frozen=True)
class TransformationAlignmentDiagnostic:
    id: str
    claim_id: str
    state: TransformationAlignmentCoverageState
    message: str


@dataclass(frozen=True)
class TransformationAlignment:
    """Typed PR-claim to observed-fact relevance without status or selection."""

    bindings: tuple[TransformationEvidenceBinding, ...] = ()
    diagnostics: tuple[TransformationAlignmentDiagnostic, ...] = ()
    schema_version: str = "transformation_alignment.v1"

    def by_claim_id(self) -> dict[str, tuple[TransformationEvidenceBinding, ...]]:
        return {
            claim_id: tuple(
                item for item in self.bindings if item.claim_id == claim_id
            )
            for claim_id in dict.fromkeys(item.claim_id for item in self.bindings)
        }

    def validate_consistency(
        self,
        contract: TransformationContract,
        observed: ObservedTransformation,
        evidence_catalog: EvidenceCatalog,
    ) -> None:
        if self.schema_version != "transformation_alignment.v1":
            raise ValueError(
                f"unsupported transformation alignment schema: {self.schema_version}"
            )
        claim_ids = {item.id for item in contract.claims}
        evidence = evidence_catalog.by_id()
        closure_ids = {
            item.id for item in evidence.values() if item.role == "closure_fact"
        }
        eligible_evidence_ids = set(observed.evidence_ids()) | closure_ids
        pairs = {(item.claim_id, item.evidence_id) for item in self.bindings}
        if len(pairs) != len(self.bindings):
            raise ValueError("transformation alignment contains duplicate bindings")
        for binding in self.bindings:
            if (
                binding.claim_id not in claim_ids
                or binding.evidence_id not in eligible_evidence_ids
                or binding.evidence_id not in evidence
            ):
                raise ValueError(
                    f"{binding.id}: transformation binding references unknown identity"
                )
            if binding.id != f"TAB:{binding.claim_id}:{binding.evidence_id}":
                raise ValueError(
                    f"{binding.id}: non-canonical transformation binding ID"
                )
            fact = evidence[binding.evidence_id]
            expected_role = fact.transformation_evidence_role()
            if binding.evidence_role != expected_role:
                raise ValueError(
                    f"{binding.id}: transformation evidence role conflicts"
                )
            if (
                not binding.reasons
                or binding.association != binding.reasons[0].kind
            ):
                raise ValueError(
                    f"{binding.id}: binding association requires canonical reasons"
                )
            if binding.evidence_role == "closure" and (
                fact.associated_statement_ids != (binding.claim_id,)
                or binding.association != "provided_association"
            ):
                raise ValueError(
                    f"{binding.id}: closure binding must preserve provider authority"
                )
        diagnostic_claim_ids = tuple(item.claim_id for item in self.diagnostics)
        if len(diagnostic_claim_ids) != len(set(diagnostic_claim_ids)):
            raise ValueError(
                "transformation alignment contains duplicate claim diagnostics"
            )
        bound_claim_ids = {item.claim_id for item in self.bindings}
        if set(diagnostic_claim_ids) & bound_claim_ids:
            raise ValueError(
                "bound transformation claims cannot carry coverage diagnostics"
            )
        if bound_claim_ids | set(diagnostic_claim_ids) != claim_ids:
            raise ValueError(
                "transformation alignment must cover every typed claim"
            )
        for diagnostic in self.diagnostics:
            if diagnostic.id != f"TAD:{diagnostic.claim_id}":
                raise ValueError(
                    f"{diagnostic.id}: non-canonical alignment diagnostic ID"
                )


@dataclass(frozen=True)
class TransformationAssessmentReason:
    kind: TransformationAssessmentReasonKind
    detail: str
    binding_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TransformationClaimAssessment:
    id: str
    claim_id: str
    status: TransformationAssessmentStatus
    supporting_binding_ids: tuple[str, ...] = ()
    contradicting_binding_ids: tuple[str, ...] = ()
    component_claim_ids: tuple[str, ...] = ()
    reasons: tuple[TransformationAssessmentReason, ...] = ()
    predicate_assessments: tuple["TransformationPredicateAssessment", ...] = ()


@dataclass(frozen=True)
class TransformationPredicateAssessment:
    """Assessment of one authored predicate without claim-wide polarity."""

    id: str
    claim_id: str
    predicate_id: str
    expectation: TransformationPredicateExpectation
    status: TransformationAssessmentStatus
    supporting_binding_ids: tuple[str, ...] = ()
    contradicting_binding_ids: tuple[str, ...] = ()
    reasons: tuple[TransformationAssessmentReason, ...] = ()


@dataclass(frozen=True)
class TransformationAssessment:
    """One conservative deterministic status per authored transformation claim."""

    claims: tuple[TransformationClaimAssessment, ...] = ()
    schema_version: str = "transformation_assessment.v3"

    def by_claim_id(self) -> dict[str, TransformationClaimAssessment]:
        return {item.claim_id: item for item in self.claims}

    def validate_consistency(
        self,
        contract: TransformationContract,
        alignment: TransformationAlignment,
        evidence_catalog: EvidenceCatalog,
    ) -> None:
        if self.schema_version != "transformation_assessment.v3":
            raise ValueError(
                f"unsupported transformation assessment schema: {self.schema_version}"
            )
        claim_ids = tuple(item.id for item in contract.claims)
        if tuple(item.claim_id for item in self.claims) != claim_ids:
            raise ValueError(
                "transformation assessment must preserve every contract claim once"
            )
        binding_ids = {item.id for item in alignment.bindings}
        binding_claim_ids = {item.id: item.claim_id for item in alignment.bindings}
        evidence_ids = set(evidence_catalog.by_id())
        claims_by_id = {item.id: item for item in contract.claims}
        migration_component_ids = tuple(
            dict.fromkeys(
                (
                    *contract.authority_claim_ids,
                    *contract.migration.producer_claim_ids,
                    *contract.migration.consumer_claim_ids,
                    *contract.migration.test_claim_ids,
                    *contract.removal_claim_ids,
                    *contract.completion_condition_claim_ids,
                )
            )
        )
        for item in self.claims:
            if item.id != f"TAS:{item.claim_id}":
                raise ValueError(f"{item.id}: non-canonical assessment ID")
            claim_predicates = tuple(
                predicate
                for predicate in contract.predicates.predicates
                if predicate.claim_id == item.claim_id
                and predicate.role == "target"
            )
            predicate_ids = tuple(predicate.id for predicate in claim_predicates)
            if tuple(
                assessment.predicate_id
                for assessment in item.predicate_assessments
            ) != predicate_ids:
                raise ValueError(
                    f"{item.id}: predicate assessments must preserve each target predicate"
                )
            referenced = (
                *item.supporting_binding_ids,
                *item.contradicting_binding_ids,
                *(
                    binding_id
                    for reason in item.reasons
                    for binding_id in reason.binding_ids
                ),
            )
            if any(binding_id not in binding_ids for binding_id in referenced):
                raise ValueError(f"{item.id}: assessment references unknown binding")
            if any(
                binding_claim_ids[binding_id]
                not in {item.claim_id, *item.component_claim_ids}
                for binding_id in referenced
            ):
                raise ValueError(
                    f"{item.id}: assessment references an undeclared component binding"
                )
            claim = claims_by_id[item.claim_id]
            if item.component_claim_ids:
                if claim.kind != "migration":
                    raise ValueError(
                        f"{item.id}: only migration closure may reference components"
                    )
                if item.component_claim_ids != migration_component_ids:
                    raise ValueError(
                        f"{item.id}: migration closure components are not canonical"
                    )
            if set(item.supporting_binding_ids) & set(
                item.contradicting_binding_ids
            ):
                raise ValueError(
                    f"{item.id}: one binding cannot support and contradict a claim"
                )
            reason_evidence_ids = {
                evidence_id
                for reason in item.reasons
                for evidence_id in reason.evidence_ids
            }
            reason_evidence_ids.update(
                evidence_id
                for predicate_assessment in item.predicate_assessments
                for reason in predicate_assessment.reasons
                for evidence_id in reason.evidence_ids
            )
            if not reason_evidence_ids <= evidence_ids:
                raise ValueError(f"{item.id}: assessment references unknown evidence")
            if not item.reasons:
                raise ValueError(f"{item.id}: assessment requires typed reasons")
            if item.status == "demonstrated" and not item.supporting_binding_ids:
                raise ValueError(
                    f"{item.id}: demonstrated assessment requires support"
                )
            if item.status == "contradicted" and not item.contradicting_binding_ids:
                raise ValueError(
                    f"{item.id}: contradicted assessment requires conflict"
                )
            claim_binding_ids = {
                binding.id
                for binding in alignment.bindings
                if binding.claim_id == item.claim_id
            }
            for predicate_assessment in item.predicate_assessments:
                predicate = next(
                    (
                        candidate
                        for candidate in claim_predicates
                        if candidate.id == predicate_assessment.predicate_id
                    ),
                    None,
                )
                if predicate is None:
                    raise ValueError(
                        f"{item.id}: predicate assessment references unknown predicate"
                    )
                if predicate_assessment.id != (
                    f"TAP:{item.claim_id}:{predicate_assessment.predicate_id}"
                ):
                    raise ValueError(
                        f"{predicate_assessment.id}: non-canonical predicate assessment ID"
                    )
                if predicate_assessment.claim_id != item.claim_id:
                    raise ValueError(
                        f"{predicate_assessment.id}: predicate assessment claim mismatch"
                    )
                if predicate_assessment.expectation != predicate.expectation:
                    raise ValueError(
                        f"{predicate_assessment.id}: predicate expectation changed"
                    )
                predicate_referenced = (
                    *predicate_assessment.supporting_binding_ids,
                    *predicate_assessment.contradicting_binding_ids,
                    *(
                        binding_id
                        for reason in predicate_assessment.reasons
                        for binding_id in reason.binding_ids
                    ),
                )
                if any(
                    binding_id not in claim_binding_ids
                    for binding_id in predicate_referenced
                ):
                    raise ValueError(
                        f"{predicate_assessment.id}: assessment references another claim's binding"
                    )
                if set(predicate_assessment.supporting_binding_ids) & set(
                    predicate_assessment.contradicting_binding_ids
                ):
                    raise ValueError(
                        f"{predicate_assessment.id}: one binding cannot support and contradict a predicate"
                    )
                if not predicate_assessment.reasons:
                    raise ValueError(
                        f"{predicate_assessment.id}: predicate assessment requires typed reasons"
                    )
                if (
                    predicate_assessment.status == "demonstrated"
                    and not predicate_assessment.supporting_binding_ids
                ):
                    raise ValueError(
                        f"{predicate_assessment.id}: demonstrated predicate requires support"
                    )
                if (
                    predicate_assessment.status == "contradicted"
                    and not predicate_assessment.contradicting_binding_ids
                ):
                    raise ValueError(
                        f"{predicate_assessment.id}: contradicted predicate requires conflict"
                    )


@dataclass(frozen=True)
class ClosureScanSelector:
    id: str
    kind: ClosureSelectorKind
    value: str


@dataclass(frozen=True)
class ClosureScanPredicate:
    """One target constrained to its declared path-scope set."""

    id: str
    target: ClosureScanSelector
    path_scopes: tuple[ClosureScanSelector, ...] = ()
    source_predicate_id: str | None = None


@dataclass(frozen=True)
class ClosureScanPlan:
    """Source-backed scan intent. A plan is never evidence that a scan ran."""

    id: str
    statement_id: str
    statement_kind: ClosureStatementKind
    expectation: ClosureExpectation
    query_text: str
    revision_sides: tuple[Literal["base", "head"], ...] = ("head",)
    scope: Literal["repository"] = "repository"
    root_paths: tuple[str, ...] = (".",)
    surfaces: tuple[ClosureScanSurface, ...] = (
        "paths",
        "file_content",
    )
    predicates: tuple[ClosureScanPredicate, ...] = ()
    sources: tuple[SourceRef, ...] = ()


@dataclass(frozen=True)
class ClosureScanPlanSet:
    plans: tuple[ClosureScanPlan, ...] = ()
    schema_version: str = "closure_scan_plan_set.v3"

    def by_id(self) -> dict[str, ClosureScanPlan]:
        return {item.id: item for item in self.plans}

    def by_statement_id(self) -> dict[str, ClosureScanPlan]:
        return {item.statement_id: item for item in self.plans}

    def validate_consistency(
        self,
        statements: tuple[Requirement | TransformationClaim, ...],
    ) -> None:
        plan_ids = self.by_id()
        by_statement = self.by_statement_id()
        expected = {item.id for item in statements}
        if len(plan_ids) != len(self.plans):
            raise ValueError("closure scan plan set contains duplicate plan IDs")
        if len(by_statement) != len(self.plans):
            raise ValueError("closure scan plan set contains duplicate statement IDs")
        if set(by_statement) != expected:
            raise ValueError(
                "closure scan plans must map one-to-one to eligible statements"
            )
        for statement in statements:
            plan = by_statement[statement.id]
            expected_kind: ClosureStatementKind
            if isinstance(statement, Requirement):
                if (
                    statement.kind != "guardrail"
                    or statement.purpose != "guardrail"
                    or not statement.id.startswith("G")
                ):
                    raise ValueError(
                        "closure scan requirement must be a canonical guardrail"
                    )
                expected_kind = "guardrail"
            elif statement.kind in {"removal", "completion_condition"}:
                expected_kind = statement.kind
            else:
                raise ValueError(
                    "closure scan claim must be removal or completion condition"
                )
            if plan.id != f"CSP:{statement.id}":
                raise ValueError(f"{plan.id}: non-canonical closure scan plan ID")
            if (
                plan.statement_kind != expected_kind
                or plan.query_text != statement.text
                or plan.sources != statement.sources
            ):
                raise ValueError(
                    f"{plan.id}: scan intent must preserve typed source authority"
                )
            expected_shape = (
                ("transition", ("base", "head"))
                if expected_kind == "removal"
                else ("absence", ("head",))
            )
            if (plan.expectation, plan.revision_sides) != expected_shape:
                raise ValueError(f"{plan.id}: closure expectation shape conflicts")
            if (
                plan.scope != "repository"
                or plan.root_paths != (".",)
                or plan.surfaces
                != ("paths", "file_content", "symbol_names")
            ):
                raise ValueError(f"{plan.id}: unsupported scan-plan boundary")
            if len({item.id for item in plan.predicates}) != len(plan.predicates):
                raise ValueError(f"{plan.id}: duplicate predicate ID")
            selector_ids: list[str] = []
            predicate_keys: list[tuple[object, ...]] = []
            for index, predicate in enumerate(plan.predicates, start=1):
                expected_id = f"{plan.id}:predicate:{index}"
                if predicate.id != expected_id:
                    raise ValueError(f"{predicate.id}: non-canonical predicate ID")
                if (
                    predicate.target.id != f"{expected_id}:target"
                    or not predicate.target.value.strip()
                ):
                    raise ValueError(
                        f"{predicate.target.id}: invalid predicate target"
                    )
                if predicate.source_predicate_id is not None and (
                    not predicate.source_predicate_id.startswith("TP:")
                ):
                    raise ValueError(
                        f"{predicate.id}: invalid source transformation predicate"
                    )
                if predicate.target.kind == "phrase" and predicate.path_scopes:
                    raise ValueError(
                        f"{predicate.id}: scoped predicate target must be exact"
                    )
                for scope_index, selector in enumerate(
                    predicate.path_scopes,
                    start=1,
                ):
                    if (
                        selector.id
                        != f"{expected_id}:path_scope:{scope_index}"
                        or selector.kind != "path"
                        or not selector.value.strip()
                    ):
                        raise ValueError(
                            f"{selector.id}: invalid predicate path scope"
                        )
                scope_values = tuple(
                    item.value.casefold() for item in predicate.path_scopes
                )
                if len(scope_values) != len(set(scope_values)):
                    raise ValueError(f"{predicate.id}: duplicate path scope")
                predicate_keys.append(
                    (
                        predicate.target.kind,
                        predicate.target.value.casefold(),
                        scope_values,
                    )
                )
                selector_ids.extend(
                    (predicate.target.id, *(item.id for item in predicate.path_scopes))
                )
            if len(selector_ids) != len(set(selector_ids)):
                raise ValueError(f"{plan.id}: duplicate selector ID")
            if len(predicate_keys) != len(set(predicate_keys)):
                raise ValueError(f"{plan.id}: duplicate semantic predicate")


@dataclass(frozen=True)
class ClosureScanMatch:
    id: str
    plan_id: str
    statement_id: str
    predicate_id: str
    selector_id: str
    revision_side: Literal["base", "head"]
    surface: ClosureScanSurface
    profile: FactProfile
    path: str
    line: int | None = None
    excerpt: str = ""


@dataclass(frozen=True)
class ClosureScanCoverage:
    surface: ClosureScanSurface
    state: ClosureScanState
    inspected_count: int = 0
    inspected_bytes: int = 0
    message: str = ""


@dataclass(frozen=True)
class ClosureScanTruncation:
    kind: ClosureScanBoundaryKind
    surface: ClosureScanSurface
    limit: int
    observed: int


@dataclass(frozen=True)
class ClosureRevisionObservation:
    revision_side: Literal["base", "head"]
    revision: str
    root_path: str
    state: ClosureScanState
    coverages: tuple[ClosureScanCoverage, ...] = ()
    truncations: tuple[ClosureScanTruncation, ...] = ()
    matches: tuple[ClosureScanMatch, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True)
class ClosureScanResult:
    id: str
    plan_id: str
    statement_id: str
    statement_kind: ClosureStatementKind
    expectation: ClosureExpectation
    revisions: tuple[ClosureRevisionObservation, ...] = ()


@dataclass(frozen=True)
class ClosureScanResultSet:
    results: tuple[ClosureScanResult, ...] = ()
    schema_version: str = "closure_scan_result_set.v2"

    def by_statement_id(self) -> dict[str, ClosureScanResult]:
        return {item.statement_id: item for item in self.results}

    def validate_consistency(self, plans: ClosureScanPlanSet) -> None:
        plan_by_id = plans.by_id()
        if len(self.by_statement_id()) != len(self.results):
            raise ValueError("closure scan results contain duplicate statement IDs")
        if {item.plan_id for item in self.results} != set(plan_by_id):
            raise ValueError("closure scan results must map one-to-one to plans")
        for result in self.results:
            plan = plan_by_id[result.plan_id]
            if result.id != f"CSR:{result.statement_id}":
                raise ValueError(f"{result.id}: non-canonical scan-result ID")
            if (
                result.statement_id != plan.statement_id
                or result.statement_kind != plan.statement_kind
                or result.expectation != plan.expectation
            ):
                raise ValueError(f"{result.id}: result statement conflicts with plan")
            if tuple(item.revision_side for item in result.revisions) != (
                plan.revision_sides
            ):
                raise ValueError(
                    f"{result.id}: result revisions must preserve plan order"
                )
            predicates = {item.id: item for item in plan.predicates}
            for revision in result.revisions:
                if any(
                    item.predicate_id not in predicates
                    or item.selector_id
                    != predicates[item.predicate_id].target.id
                    or item.statement_id != result.statement_id
                    or item.revision_side != revision.revision_side
                    for item in revision.matches
                ):
                    raise ValueError(f"{result.id}: match identity conflicts")
                if any(item.surface not in plan.surfaces for item in revision.matches):
                    raise ValueError(f"{result.id}: match references unplanned surface")
                if tuple(item.surface for item in revision.coverages) != plan.surfaces:
                    raise ValueError(
                        f"{result.id}: result coverage must preserve plan surfaces"
                    )
                if any(
                    item.surface not in plan.surfaces
                    or item.limit <= 0
                    or item.observed < item.limit
                    for item in revision.truncations
                ):
                    raise ValueError(f"{result.id}: invalid scan truncation")
                if revision.state == "complete" and (
                    revision.truncations
                    or any(
                        item.state != "complete" for item in revision.coverages
                    )
                ):
                    raise ValueError(
                        f"{result.id}: complete revision requires complete surfaces"
                    )
                if revision.state == "partial" and (
                    not revision.truncations
                    or all(
                        item.state == "complete" for item in revision.coverages
                    )
                ):
                    raise ValueError(
                        f"{result.id}: partial revision requires typed truncation"
                    )
                if revision.state == "unavailable" and any(
                    item.state != "unavailable" for item in revision.coverages
                ):
                    raise ValueError(
                        f"{result.id}: unavailable revision requires unavailable surfaces"
                    )
                if revision.state != "unavailable" and not revision.revision:
                    raise ValueError(
                        f"{result.id}: observed scan requires a revision"
                    )


@dataclass(frozen=True)
class ClosureScanDiagnostic:
    code: str
    message: str
    plan_id: str
    statement_id: str
    revision_side: Literal["base", "head"]


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
    closure_scan_result: ClosureScanResult | None = None
    sources: tuple[SourceRef, ...] = ()
    change_relation_ids: tuple[str, ...] = ()
    structural_path_ids: tuple[str, ...] = ()
    structural_traversal_coverage: StructuralTraversalCoverageState = "unknown"
    structural_change: StructuralChangeIdentity | None = None
    structural_relation_change: StructuralRelationChangeIdentity | None = None
    structural_ownership: StructuralOwnershipIdentity | None = None
    structural_ownership_change: StructuralOwnershipChangeIdentity | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def transformation_evidence_role(
        self,
    ) -> TransformationEvidenceRole | None:
        if self.role == "closure_fact":
            return "closure"
        if self.role == "verification":
            return "verification"
        if self.kind == "structural_path":
            return "structural_path"
        if self.kind == "structural_relation_change":
            return "relation_change"
        if self.kind == "structural_ownership_change":
            return "ownership_change"
        if self.changed and self.role == "changed_anchor":
            return "change"
        return None

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
            self.kind != "structural_path"
            and self.structural_traversal_coverage != "unknown"
        ):
            raise ValueError(
                f"{self.id}: only structural paths may carry traversal coverage"
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
        if self.role == "closure_fact":
            if self.authority != "closure_scan_provider":
                raise ValueError(
                    f"{self.id}: closure fact requires closure scan authority"
                )
            if self.closure_scan_result is None:
                raise ValueError(f"{self.id}: closure fact requires a scan result")
            if self.revision_side != "review" or self.operation != "observed":
                raise ValueError(
                    f"{self.id}: closure fact must aggregate observed revisions"
                )
            if self.associated_statement_ids != (
                self.closure_scan_result.statement_id,
            ):
                raise ValueError(
                    f"{self.id}: closure fact must own its statement association"
                )
        elif self.closure_scan_result is not None:
            raise ValueError(
                f"{self.id}: only closure facts may carry a scan result"
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
    closure_scan_diagnostics: tuple[ClosureScanDiagnostic, ...] = ()
    schema_version: str = "evidence_catalog.v18"

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
StructuralNavigationState = Literal["available", "unavailable"]
StructuralNavigationKind = Literal["revision_symbol", "pull_request_diff"]
StructuralNavigationPurpose = Literal["symbol", "change"]


@dataclass(frozen=True)
class StructuralNavigationTarget:
    """Projection-owned destination; renderers must not derive repository URLs."""

    id: str
    owner_node_id: str
    purpose: StructuralNavigationPurpose
    state: StructuralNavigationState
    kind: StructuralNavigationKind | None = None
    revision_side: Literal["base", "head"] | None = None
    url: str | None = None
    path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.state == "available":
            if (
                self.kind is None
                or self.revision_side is None
                or self.url is None
                or self.path is None
            ):
                raise ValueError(
                    f"{self.id}: available structural navigation is incomplete"
                )
            if self.reason is not None:
                raise ValueError(
                    f"{self.id}: available structural navigation has a reason"
                )
        elif (
            self.kind is not None
            or self.revision_side is not None
            or self.url is not None
            or self.path is not None
            or self.line_start is not None
            or self.line_end is not None
            or not self.reason
        ):
            raise ValueError(
                f"{self.id}: unavailable structural navigation carries a target"
            )


@dataclass(frozen=True)
class StructuralGraphNode:
    id: str
    review_symbol_id: str
    delta: StructuralGraphNodeDelta
    evidence_ids: tuple[str, ...]
    display_evidence_id: str
    path_relation_ids: tuple[str, ...] = ()
    symbol_navigation_target_id: str = ""
    change_navigation_target_id: str = ""


@dataclass(frozen=True)
class StructuralGraphEdge:
    id: str
    source_node_id: str
    target_node_id: str
    relation: str
    operation: Literal["added", "removed", "retained"]
    relation_change_evidence_id: str
    path_relation_ids: tuple[str, ...] = ()
    source_navigation_target_id: str = ""
    target_navigation_target_id: str = ""


@dataclass(frozen=True)
class StructuralRelationGroup:
    """Projection-owned display lane over canonical executable edges."""

    id: str
    source_node_id: str
    target_node_id: str
    relation: str
    operation: Literal["added", "removed", "retained"]
    member_edge_ids: tuple[str, ...]
    path_relation_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.member_edge_ids:
            raise ValueError(f"{self.id}: structural relation group requires members")
        if len(set(self.member_edge_ids)) != len(self.member_edge_ids):
            raise ValueError(
                f"{self.id}: structural relation group members must be unique"
            )
        if self.member_edge_ids != tuple(sorted(self.member_edge_ids)):
            raise ValueError(
                f"{self.id}: structural relation group members must be sorted"
            )
        if len(set(self.path_relation_ids)) != len(self.path_relation_ids):
            raise ValueError(
                f"{self.id}: structural relation group paths must be unique"
            )
        if self.source_node_id == self.target_node_id:
            raise ValueError(
                f"{self.id}: structural relation group requires distinct endpoints"
            )


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
    relation_groups: tuple[StructuralRelationGroup, ...] = ()
    ownership_edges: tuple[StructuralGraphOwnershipEdge, ...] = ()
    placements: tuple[StructuralGraphPlacement, ...] = ()
    primary_placement_ids: tuple[str, ...] = ()
    backbone_node_ids: tuple[str, ...] = ()
    backbone_edge_ids: tuple[str, ...] = ()
    backbone_relation_group_ids: tuple[str, ...] = ()
    backbone_ownership_edge_ids: tuple[str, ...] = ()
    path_relation_ids: tuple[str, ...] = ()
    navigation_targets: tuple[StructuralNavigationTarget, ...] = ()


ArchitecturalLayer = Literal[
    "entry",
    "presentation",
    "application",
    "domain",
    "infrastructure",
    "persistence",
    "verification",
    "documentation",
    "automation",
    "unclassified",
]
ArchitecturalFlowKind = Literal[
    "executable",
    "verification_support",
    "dependency",
    "structural_support",
]


def architectural_flow_kind(
    relation: str,
    source_layer: ArchitecturalLayer,
    target_layer: ArchitecturalLayer,
) -> ArchitecturalFlowKind:
    if "verification" in {source_layer, target_layer}:
        return "verification_support"
    if relation in {"calls", "instantiates"}:
        return "executable"
    if relation in {"imports", "references", "extends"}:
        return "dependency"
    return "structural_support"


@dataclass(frozen=True)
class ArchitecturalOperationCount:
    operation: StructuralGraphNodeDelta
    count: int

    def __post_init__(self) -> None:
        if self.count <= 0:
            raise ValueError("architectural operation count must be positive")


@dataclass(frozen=True)
class ArchitecturalComponent:
    """One path-bounded component over canonical structural node identities."""

    id: str
    domain: str
    layer: ArchitecturalLayer
    node_ids: tuple[str, ...]
    operation_counts: tuple[ArchitecturalOperationCount, ...]
    classification_authority: Literal["path_structure", "path_convention"]

    def __post_init__(self) -> None:
        if not self.domain or not self.node_ids:
            raise ValueError(f"{self.id}: architectural component requires members")
        if self.node_ids != tuple(sorted(set(self.node_ids))):
            raise ValueError(
                f"{self.id}: architectural component members must be sorted and unique"
            )
        expected_authority = (
            "path_structure"
            if self.layer == "unclassified"
            else "path_convention"
        )
        if self.classification_authority != expected_authority:
            raise ValueError(
                f"{self.id}: architectural classification authority mismatch"
            )


@dataclass(frozen=True)
class ArchitecturalFlow:
    """Cross-component flow backed only by canonical relation groups."""

    id: str
    source_component_id: str
    target_component_id: str
    kind: ArchitecturalFlowKind
    operation: Literal["added", "removed", "retained"]
    relations: tuple[str, ...]
    relation_group_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.source_component_id == self.target_component_id:
            raise ValueError(f"{self.id}: architectural flow must cross components")
        if not self.relation_group_ids:
            raise ValueError(f"{self.id}: architectural flow requires provenance")
        if self.relations != tuple(sorted(set(self.relations))) or not self.relations:
            raise ValueError(
                f"{self.id}: architectural flow relations must be sorted and unique"
            )
        if self.relation_group_ids != tuple(
            sorted(set(self.relation_group_ids))
        ):
            raise ValueError(
                f"{self.id}: architectural flow provenance must be sorted and unique"
            )


@dataclass(frozen=True)
class ArchitecturalChangeTopology:
    """Canonical component-level projection of the review structural backbone."""

    components: tuple[ArchitecturalComponent, ...] = ()
    flows: tuple[ArchitecturalFlow, ...] = ()
    display_component_ids: tuple[str, ...] = ()
    schema_version: str = "architectural_change_topology.v2"

    def validate_against(self, graph: ReviewStructuralGraph) -> None:
        component_ids = {item.id for item in self.components}
        if len(component_ids) != len(self.components):
            raise ValueError("architectural topology contains duplicate components")
        if set(self.display_component_ids) != component_ids or len(
            self.display_component_ids
        ) != len(component_ids):
            raise ValueError(
                "architectural topology display order must preserve every component"
            )
        flow_ids = {item.id for item in self.flows}
        if len(flow_ids) != len(self.flows):
            raise ValueError("architectural topology contains duplicate flows")
        projected_node_ids = tuple(
            node_id for item in self.components for node_id in item.node_ids
        )
        if len(projected_node_ids) != len(set(projected_node_ids)):
            raise ValueError("architectural topology classifies a node more than once")
        if set(projected_node_ids) != set(graph.backbone_node_ids):
            raise ValueError("architectural topology must classify the complete backbone")
        component_by_node = {
            node_id: component.id
            for component in self.components
            for node_id in component.node_ids
        }
        components_by_id = {item.id: item for item in self.components}
        graph_nodes = {item.id: item for item in graph.nodes}
        for component in self.components:
            expected_counts: dict[str, int] = {}
            for node_id in component.node_ids:
                operation = graph_nodes[node_id].delta
                expected_counts[operation] = expected_counts.get(operation, 0) + 1
            observed_counts = {
                item.operation: item.count for item in component.operation_counts
            }
            if observed_counts != expected_counts or len(observed_counts) != len(
                component.operation_counts
            ):
                raise ValueError(
                    "architectural component operation summary diverges from graph"
                )
        graph_groups = {
            item.id: item
            for item in graph.relation_groups
            if item.id in graph.backbone_relation_group_ids
        }
        projected_group_ids: list[str] = []
        for flow in self.flows:
            if (
                flow.source_component_id not in component_ids
                or flow.target_component_id not in component_ids
            ):
                raise ValueError("architectural flow references a missing component")
            if not set(flow.relation_group_ids) <= set(graph_groups):
                raise ValueError(
                    "architectural flow references a non-backbone relation"
                )
            for group_id in flow.relation_group_ids:
                group = graph_groups[group_id]
                if (
                    component_by_node[group.source_node_id]
                    != flow.source_component_id
                    or component_by_node[group.target_node_id]
                    != flow.target_component_id
                    or group.operation != flow.operation
                ):
                    raise ValueError(
                        "architectural flow diverges from canonical relation endpoints"
                    )
                projected_group_ids.append(group_id)
            expected_relations = tuple(
                sorted({graph_groups[item].relation for item in flow.relation_group_ids})
            )
            if flow.relations != expected_relations or any(
                architectural_flow_kind(
                    relation,
                    components_by_id[flow.source_component_id].layer,
                    components_by_id[flow.target_component_id].layer,
                )
                != flow.kind
                for relation in flow.relations
            ):
                raise ValueError(
                    "architectural flow kind diverges from canonical relations"
                )
        expected_group_ids = {
            group.id
            for group in graph_groups.values()
            if component_by_node[group.source_node_id]
            != component_by_node[group.target_node_id]
        }
        if len(projected_group_ids) != len(set(projected_group_ids)) or set(
            projected_group_ids
        ) != expected_group_ids:
            raise ValueError(
                "architectural topology must project each cross-component relation once"
            )


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
    relation_group_ids: tuple[str, ...] = ()
    ownership_edge_ids: tuple[str, ...] = ()
    placement_ids: tuple[str, ...] = ()
    path_relation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TransformationStructuralTopologyGroup:
    """One claim's identity join into the shared structural graph."""

    claim_id: str
    structural_overlay: StructuralFocusOverlay = StructuralFocusOverlay()
    diagnostic_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TransformationStructuralTopology:
    """Projection-owned mapping from closure claims to shared graph members."""

    groups: tuple[TransformationStructuralTopologyGroup, ...] = ()
    schema_version: str = "transformation_structural_topology.v1"

    def by_claim_id(self) -> dict[str, TransformationStructuralTopologyGroup]:
        return {item.claim_id: item for item in self.groups}


@dataclass(frozen=True)
class CanonicalChangeMapEntry:
    focus_statement_id: str
    claim_relation_ids: tuple[str, ...] = ()
    structural_overlay: StructuralFocusOverlay = StructuralFocusOverlay()
    structural_disposition: StructuralFocusDisposition = (
        StructuralFocusDisposition()
    )


@dataclass(frozen=True)
class ReviewSlice:
    change_map: CanonicalChangeMapEntry
    standalone_changed_fact_relation_ids: tuple[str, ...] = ()
    standalone_test_support_relation_ids: tuple[str, ...] = ()
    standalone_document_support_relation_ids: tuple[str, ...] = ()
    standalone_runtime_relation_ids: tuple[str, ...] = ()
    standalone_test_relation_ids: tuple[str, ...] = ()
    verification_relation_ids: tuple[str, ...] = ()
    closure_fact_relation_ids: tuple[str, ...] = ()
    closure_scan_plan_id: str | None = None
    diagnostic_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class VerificationMatrixEntry:
    id: str
    subject_id: str
    subject_kind: VerificationSubjectKind
    text: str
    authority: str
    status: VerificationProjectionStatus
    inspector_id: str
    sources: tuple[SourceRef, ...] = ()


@dataclass(frozen=True)
class ArchitecturalSubjectOverlay:
    component_ids: tuple[str, ...] = ()
    context_component_ids: tuple[str, ...] = ()
    flow_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name, identities in (
            ("component_ids", self.component_ids),
            ("context_component_ids", self.context_component_ids),
            ("flow_ids", self.flow_ids),
        ):
            if len(identities) != len(set(identities)):
                raise ValueError(f"architectural overlay {name} must be unique")
        if set(self.component_ids) & set(self.context_component_ids):
            raise ValueError(
                "architectural overlay direct and context components must be disjoint"
            )


@dataclass(frozen=True)
class VerificationEvidenceInspection:
    id: str
    subject_id: str
    observed_evidence_ids: tuple[str, ...] = ()
    supporting_evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()
    projection_relation_ids: tuple[str, ...] = ()
    transformation_binding_ids: tuple[str, ...] = ()
    diagnostic_ids: tuple[str, ...] = ()
    structural_overlay: StructuralFocusOverlay = StructuralFocusOverlay()
    architectural_overlay: ArchitecturalSubjectOverlay = ArchitecturalSubjectOverlay()
    assessment_reasons: tuple[TransformationAssessmentReason, ...] = ()


@dataclass(frozen=True)
class VerificationStatusCount:
    status: VerificationProjectionStatus
    count: int


@dataclass(frozen=True)
class TransformationSummaryProjection:
    source_state: TransformationContractSourceState = "source_absent"
    claim_ids: tuple[str, ...] = ()
    change_claim_ids: tuple[str, ...] = ()
    before_state_claim_ids: tuple[str, ...] = ()
    after_state_claim_ids: tuple[str, ...] = ()
    selected_region_claim_ids: tuple[str, ...] = ()
    boundary_claim_ids: tuple[str, ...] = ()
    before_topology_claim_ids: tuple[str, ...] = ()
    after_topology_claim_ids: tuple[str, ...] = ()
    authority_claim_ids: tuple[str, ...] = ()
    production_path_claim_ids: tuple[str, ...] = ()
    migration_claim_ids: tuple[str, ...] = ()
    migration_component_claim_ids: tuple[str, ...] = ()
    removal_claim_ids: tuple[str, ...] = ()
    completion_condition_claim_ids: tuple[str, ...] = ()
    uncertainty_claim_ids: tuple[str, ...] = ()
    observed_evidence_ids: tuple[str, ...] = ()
    base_topology_evidence_ids: tuple[str, ...] = ()
    head_topology_evidence_ids: tuple[str, ...] = ()
    aligned_claim_ids: tuple[str, ...] = ()
    unassociated_claim_ids: tuple[str, ...] = ()
    status_counts: tuple[VerificationStatusCount, ...] = ()


@dataclass(frozen=True)
class VerificationWorkspace:
    """Single presentation boundary for matrix and evidence-inspector views."""

    transformation_summary: TransformationSummaryProjection = (
        TransformationSummaryProjection()
    )
    transformation_structural_topology: TransformationStructuralTopology = (
        TransformationStructuralTopology()
    )
    matrix: tuple[VerificationMatrixEntry, ...] = ()
    inspections: tuple[VerificationEvidenceInspection, ...] = ()
    schema_version: str = "verification_workspace.v5"

    def by_subject_id(self) -> dict[str, VerificationMatrixEntry]:
        return {item.subject_id: item for item in self.matrix}

    def inspections_by_subject_id(
        self,
    ) -> dict[str, VerificationEvidenceInspection]:
        return {item.subject_id: item for item in self.inspections}


@dataclass(frozen=True)
class ReviewProjection:
    slices: tuple[ReviewSlice, ...] = ()
    review_graph: ReviewStructuralGraph = ReviewStructuralGraph()
    architectural_topology: ArchitecturalChangeTopology = (
        ArchitecturalChangeTopology()
    )
    verification_workspace: VerificationWorkspace = VerificationWorkspace()
    schema_version: str = "review_projection.v28"

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
        relation_groups = {
            item.id: item for item in self.review_graph.relation_groups
        }
        ownership_edges = {
            item.id: item for item in self.review_graph.ownership_edges
        }
        placements = {
            item.id: item for item in self.review_graph.placements
        }
        navigation_targets = {
            item.id: item for item in self.review_graph.navigation_targets
        }
        self.architectural_topology.validate_against(self.review_graph)
        if len(nodes) != len(self.review_graph.nodes):
            raise ValueError("review structural graph contains duplicate nodes")
        if len(edges) != len(self.review_graph.edges):
            raise ValueError("review structural graph contains duplicate edges")
        if len(relation_groups) != len(self.review_graph.relation_groups):
            raise ValueError(
                "review structural graph contains duplicate relation groups"
            )
        if len(ownership_edges) != len(self.review_graph.ownership_edges):
            raise ValueError(
                "review structural graph contains duplicate ownership edges"
            )
        if len(placements) != len(self.review_graph.placements):
            raise ValueError(
                "review structural graph contains duplicate placements"
            )
        if len(navigation_targets) != len(
            self.review_graph.navigation_targets
        ):
            raise ValueError(
                "review structural graph contains duplicate navigation targets"
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
            symbol_target = navigation_targets.get(
                node.symbol_navigation_target_id
            )
            change_target = navigation_targets.get(
                node.change_navigation_target_id
            )
            if (
                symbol_target is None
                or symbol_target.owner_node_id != node.id
                or symbol_target.purpose != "symbol"
                or change_target is None
                or change_target.owner_node_id != node.id
                or change_target.purpose != "change"
            ):
                raise ValueError(
                    "review structural node references invalid navigation targets"
                )
            desired_revision = (
                "base"
                if node.delta == "removed"
                else "head"
                if node.delta in {"added", "modified", "renamed"}
                else display_fact.revision_side
            )
            if (
                symbol_target.state == "available"
                and symbol_target.revision_side != desired_revision
            ):
                raise ValueError(
                    "review structural node symbol navigation revision mismatch"
                )
            if (
                change_target.state == "available"
                and change_target.revision_side != desired_revision
            ):
                raise ValueError(
                    "review structural node change navigation revision mismatch"
                )
        backbone_node_ids = set(self.review_graph.backbone_node_ids)
        backbone_edge_ids = set(self.review_graph.backbone_edge_ids)
        backbone_relation_group_ids = set(
            self.review_graph.backbone_relation_group_ids
        )
        backbone_ownership_edge_ids = set(
            self.review_graph.backbone_ownership_edge_ids
        )
        if len(backbone_node_ids) != len(self.review_graph.backbone_node_ids):
            raise ValueError("review structural backbone contains duplicate nodes")
        if len(backbone_edge_ids) != len(self.review_graph.backbone_edge_ids):
            raise ValueError("review structural backbone contains duplicate edges")
        if len(backbone_relation_group_ids) != len(
            self.review_graph.backbone_relation_group_ids
        ):
            raise ValueError(
                "review structural backbone contains duplicate relation groups"
            )
        if len(backbone_ownership_edge_ids) != len(
            self.review_graph.backbone_ownership_edge_ids
        ):
            raise ValueError(
                "review structural backbone contains duplicate ownership edges"
            )
        if (
            not backbone_node_ids <= set(nodes)
            or not backbone_edge_ids <= set(edges)
            or not backbone_relation_group_ids <= set(relation_groups)
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
            source_target = navigation_targets.get(
                edge.source_navigation_target_id
            )
            target_target = navigation_targets.get(
                edge.target_navigation_target_id
            )
            if (
                source_target is None
                or source_target.owner_node_id != edge.source_node_id
                or source_target.purpose != "symbol"
                or target_target is None
                or target_target.owner_node_id != edge.target_node_id
                or target_target.purpose != "symbol"
            ):
                raise ValueError(
                    "review structural edge references invalid endpoint navigation"
                )
        referenced_navigation_target_ids = {
            *(
                target_id
                for node in self.review_graph.nodes
                for target_id in (
                    node.symbol_navigation_target_id,
                    node.change_navigation_target_id,
                )
            ),
            *(
                target_id
                for edge in self.review_graph.edges
                for target_id in (
                    edge.source_navigation_target_id,
                    edge.target_navigation_target_id,
                )
            ),
        }
        if referenced_navigation_target_ids != set(navigation_targets):
            raise ValueError(
                "review structural graph contains dangling navigation targets"
            )
        primary_placement_ids = set(self.review_graph.primary_placement_ids)
        if len(primary_placement_ids) != len(
            self.review_graph.primary_placement_ids
        ) or not primary_placement_ids <= set(placements):
            raise ValueError(
                "review structural graph references invalid primary placements"
            )
        primary_children = [
            placements[placement_id].child_node_id
            for placement_id in self.review_graph.primary_placement_ids
        ]
        if len(primary_children) != len(set(primary_children)):
            raise ValueError(
                "review structural graph has multiple primary placements "
                "for one child"
            )
        if set(primary_children) != {
            placement.child_node_id
            for placement in self.review_graph.placements
        }:
            raise ValueError(
                "review structural graph must select one primary placement "
                "for every placed child"
            )
        primary_parent = {
            placements[placement_id].child_node_id: (
                placements[placement_id].parent_node_id
            )
            for placement_id in self.review_graph.primary_placement_ids
        }

        def belongs_to_display_endpoint(
            member_node_id: str,
            display_node_id: str,
        ) -> bool:
            current = member_node_id
            visited = {current}
            while True:
                if current == display_node_id:
                    return True
                if current not in primary_parent:
                    return False
                current = primary_parent[current]
                if current in visited:
                    raise ValueError(
                        "review structural primary placement contains a cycle"
                    )
                visited.add(current)

        grouped_edge_ids = []
        for group in self.review_graph.relation_groups:
            if (
                group.source_node_id not in nodes
                or group.target_node_id not in nodes
            ):
                raise ValueError(
                    "review structural relation group references a missing node"
                )
            members = tuple(edges.get(edge_id) for edge_id in group.member_edge_ids)
            if any(item is None for item in members):
                raise ValueError(
                    "review structural relation group references a missing edge"
                )
            if any(
                item.relation != group.relation
                or item.operation != group.operation
                for item in members
                if item is not None
            ):
                raise ValueError(
                    "review structural relation group member semantics mismatch"
                )
            if any(
                not belongs_to_display_endpoint(
                    item.source_node_id,
                    group.source_node_id,
                )
                or not belongs_to_display_endpoint(
                    item.target_node_id,
                    group.target_node_id,
                )
                for item in members
                if item is not None
            ):
                raise ValueError(
                    "review structural relation group display endpoint mismatch"
                )
            expected_paths = tuple(
                dict.fromkeys(
                    path_relation_id
                    for item in members
                    if item is not None
                    for path_relation_id in item.path_relation_ids
                )
            )
            if group.path_relation_ids != expected_paths:
                raise ValueError(
                    "review structural relation group path provenance mismatch"
                )
            grouped_edge_ids.extend(group.member_edge_ids)
        if (
            len(grouped_edge_ids) != len(set(grouped_edge_ids))
            or set(grouped_edge_ids) != set(edges)
        ):
            raise ValueError(
                "review structural relation groups must partition canonical edges"
            )
        if any(
            not set(relation_groups[group_id].member_edge_ids)
            & backbone_edge_ids
            for group_id in backbone_relation_group_ids
        ):
            raise ValueError(
                "review structural backbone group requires a backbone member edge"
            )
        expected_backbone_groups = {
            group.id
            for group in self.review_graph.relation_groups
            if set(group.member_edge_ids) & backbone_edge_ids
        }
        if backbone_relation_group_ids != expected_backbone_groups:
            raise ValueError(
                "review structural backbone groups must project every "
                "backbone executable edge"
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
        change_map_focus_ids = tuple(
            item.change_map.focus_statement_id for item in self.slices
        )
        if len(change_map_focus_ids) != len(set(change_map_focus_ids)):
            raise ValueError("canonical change map contains duplicate focus entries")
        for review_slice in self.slices:
            change_map = review_slice.change_map
            focus_id = change_map.focus_statement_id
            overlay = change_map.structural_overlay
            disposition = change_map.structural_disposition
            converged = convergence_by_focus.get(focus_id)
            if converged is None:
                raise ValueError(
                    f"{focus_id}: canonical change map "
                    "has no convergence group"
                )
            selected_ids = set(converged.selected_relation_ids)
            deferred_ids = set(converged.deferred_relation_ids)
            if len(change_map.claim_relation_ids) != len(
                set(change_map.claim_relation_ids)
            ):
                raise ValueError(
                    f"{focus_id}: canonical change map contains duplicate claim bindings"
                )
            if any(
                relation_id not in relations
                or relations[relation_id].focus_statement_id != focus_id
                or relations[relation_id].slot != "claim"
                or relation_id not in selected_ids
                for relation_id in change_map.claim_relation_ids
            ):
                raise ValueError(
                    f"{focus_id}: canonical change map references an invalid claim binding"
                )
            if any(
                relation_id not in relations
                or relations[relation_id].focus_statement_id
                != focus_id
                for relation_id in (
                    *disposition.non_structural_relation_ids,
                    *disposition.deferred_structural_relation_ids,
                )
            ):
                raise ValueError(
                    f"{focus_id}: structural disposition "
                    "references an invalid relation"
                )
            if not set(disposition.non_structural_relation_ids) <= selected_ids:
                raise ValueError(
                    f"{focus_id}: non-structural disposition "
                    "must reference selected relations"
                )
            if not set(disposition.deferred_structural_relation_ids) <= deferred_ids:
                raise ValueError(
                    f"{focus_id}: deferred structural "
                    "disposition must reference deferred relations"
                )
            if any(
                item not in diagnostic_ids
                for item in disposition.diagnostic_ids
            ):
                raise ValueError(
                    f"{focus_id}: structural disposition "
                    "references an invalid diagnostic"
                )
            if any(
                placement_id not in placements
                for placement_id in overlay.placement_ids
            ):
                raise ValueError(
                    f"{focus_id}: structural overlay "
                    "references missing placement"
                )
            if (disposition.state == "projected") != bool(overlay.nodes):
                raise ValueError(
                    f"{focus_id}: projected disposition "
                    "must agree with the structural overlay"
                )
            overlay_node_ids = {item.node_id for item in overlay.nodes}
            if len(overlay_node_ids) != len(overlay.nodes):
                raise ValueError(
                    f"{focus_id}: overlay contains "
                    "duplicate structural nodes"
                )
            if any(node_id not in nodes for node_id in overlay_node_ids):
                raise ValueError(
                    f"{focus_id}: overlay references "
                    "a missing structural node"
                )
            if any(edge_id not in edges for edge_id in overlay.edge_ids):
                raise ValueError(
                    f"{focus_id}: overlay references "
                    "a missing structural edge"
                )
            if any(
                group_id not in relation_groups
                for group_id in overlay.relation_group_ids
            ):
                raise ValueError(
                    f"{focus_id}: structural overlay "
                    "references a missing relation group"
                )
            if any(
                edge_id not in ownership_edges
                for edge_id in overlay.ownership_edge_ids
            ):
                raise ValueError(
                    f"{focus_id}: overlay references "
                    "a missing ownership edge"
                )
            if any(
                edges[edge_id].source_node_id not in overlay_node_ids
                or edges[edge_id].target_node_id not in overlay_node_ids
                for edge_id in overlay.edge_ids
            ):
                raise ValueError(
                    f"{focus_id}: structural edge "
                    "endpoints must belong to the overlay"
                )
            if any(
                relation_groups[group_id].source_node_id not in overlay_node_ids
                or relation_groups[group_id].target_node_id
                not in overlay_node_ids
                or not set(relation_groups[group_id].member_edge_ids)
                & set(overlay.edge_ids)
                for group_id in overlay.relation_group_ids
            ):
                raise ValueError(
                    f"{focus_id}: structural relation "
                    "group must represent overlay edges between overlay nodes"
                )
            expected_overlay_groups = {
                group.id
                for group in self.review_graph.relation_groups
                if set(group.member_edge_ids) & set(overlay.edge_ids)
            }
            if set(overlay.relation_group_ids) != expected_overlay_groups:
                raise ValueError(
                    f"{focus_id}: structural relation "
                    "groups must project every overlay edge"
                )
            if any(
                ownership_edges[edge_id].parent_node_id not in overlay_node_ids
                or ownership_edges[edge_id].child_node_id not in overlay_node_ids
                for edge_id in overlay.ownership_edge_ids
            ):
                raise ValueError(
                    f"{focus_id}: ownership edge "
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


LLMShadowExecutionState = Literal[
    "off", "unavailable", "completed", "partial", "failed"
]


@dataclass(frozen=True)
class LLMShadowExecutionSummary:
    """Review-level execution observation with no assessment authority."""

    state: LLMShadowExecutionState = "off"
    admitted_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    deferred_count: int = 0
    artifact_written: bool = False


@dataclass(frozen=True)
class ReviewOverview:
    pull_request_state: ReviewPullRequestState
    ci_state: ReviewCiState
    changed_file_count: int
    structural_coverage: StructuralCoverage
    attention: tuple[ReviewAttention, ...] = ()
    empty_review_message: str | None = None
    llm_shadow: LLMShadowExecutionSummary = field(
        default_factory=LLMShadowExecutionSummary
    )


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
    transformation_contract: TransformationContract = TransformationContract()
    observed_transformation: ObservedTransformation = ObservedTransformation()
    transformation_subject_selection: TransformationSubjectSelection = (
        TransformationSubjectSelection()
    )
    transformation_structural_closure: TransformationStructuralClosure = (
        TransformationStructuralClosure()
    )
    transformation_alignment: TransformationAlignment = TransformationAlignment()
    transformation_assessment: TransformationAssessment = TransformationAssessment()
    closure_scan_plans: ClosureScanPlanSet = ClosureScanPlanSet()
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
    schema_version: str = "review_brief.v52"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
