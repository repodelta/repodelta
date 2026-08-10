from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, get_args

from repodelta.evaluation.shadow import (
    ExpectedShadowOutcome,
    HumanShadowLabelSet,
    ShadowEvaluationMetrics,
    ShadowEvaluationThresholds,
    ShadowOutcomeEvaluation,
    evaluate_shadow_outcomes,
    load_human_shadow_labels,
    shadow_diagnostics,
    shadow_metrics,
    shadow_threshold_diagnostics,
)
from repodelta.llm.execution import load_shadow_execution
from repodelta.pipeline import DeterministicAnalyzer
from repodelta.model.contracts import (
    ClosureRevisionObservation,
    ClosureScanCoverage,
    ClosureScanMatch,
    ClosureScanPlanSet,
    ClosureScanResult,
    ClosureScanResultSet,
    ClosureScanTruncation,
    EvidenceClassification,
    FactProfile,
    ProjectionRelation,
    ProjectionSlot,
    ReviewBrief,
    StatementAuthority,
    StatementPurpose,
    StatementRole,
    StructuralFocusDispositionState,
    TransformationAssessmentReasonKind,
    TransformationAssessmentStatus,
    TransformationPredicateExpectation,
)
from repodelta.intake.fixture import load_fixture
from repodelta.providers.structural import (
    GraphPathStep,
    GraphSymbol,
    HunkSymbolOverlap,
    StructuralGraphCollection,
    StructuralGraphIndexStatus,
    StructuralGraphResult,
    StructuralPath,
    StructuralSeedCoverage,
)


@dataclass(frozen=True)
class ExpectedSelection:
    slot: ProjectionSlot
    focus_statement_id: str
    target_id: str


@dataclass(frozen=True)
class ExpectedEvidence:
    evidence_id: str
    classification: EvidenceClassification
    profile: FactProfile


@dataclass(frozen=True)
class ExpectedNoSelection:
    slot: ProjectionSlot
    focus_statement_id: str


@dataclass(frozen=True)
class ExpectedStatement:
    statement_id: str
    role: StatementRole
    purpose: StatementPurpose
    authority: StatementAuthority


@dataclass(frozen=True)
class ExpectedTransformationAssessment:
    claim_id: str
    status: TransformationAssessmentStatus
    reason_kinds: tuple[TransformationAssessmentReasonKind, ...]
    predicate_id: str | None = None
    expectation: TransformationPredicateExpectation | None = None
    supporting_evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExpectedFocusOutcome:
    subject_id: str
    disposition: StructuralFocusDispositionState
    graph_node_count: int = 0
    closure_fact_count: int = 0
    closure_revision_states: tuple[str, ...] = ()
    closure_match_count: int = 0


@dataclass(frozen=True)
class EvaluationCase:
    id: str
    fixture: str
    expected_selections: tuple[ExpectedSelection, ...]
    expected_no_selections: tuple[ExpectedNoSelection, ...] = ()
    expected_evidence: tuple[ExpectedEvidence, ...] = ()
    expected_statements: tuple[ExpectedStatement, ...] = ()
    expected_assessments: tuple[ExpectedTransformationAssessment, ...] = ()
    expected_focus_outcomes: tuple[ExpectedFocusOutcome, ...] = ()
    structural_graph: StructuralGraphCollection | None = None
    closure_scan_results: ClosureScanResultSet | None = None
    shadow_execution: str | None = None
    human_shadow_labels: str | None = None
    expected_shadow_outcomes: tuple[ExpectedShadowOutcome, ...] = ()


@dataclass(frozen=True)
class EvaluationThresholds:
    precision_at_k: float = 0.0
    recall_at_k: float = 0.0
    mean_reciprocal_rank: float = 0.0
    classification_accuracy: float = 0.0
    max_no_candidate_rate: float = 1.0
    no_match_accuracy: float = 0.0
    max_false_positive_rate: float = 1.0
    statement_accuracy: float = 0.0
    assessment_accuracy: float = 0.0
    focus_accuracy: float = 0.0


@dataclass(frozen=True)
class EvaluationSuite:
    cases: tuple[EvaluationCase, ...]
    thresholds: EvaluationThresholds = EvaluationThresholds()
    shadow_thresholds: ShadowEvaluationThresholds = ShadowEvaluationThresholds()
    k: int = 5
    schema_version: str = "evaluation_suite.v6"


@dataclass(frozen=True)
class QueryEvaluation:
    case_id: str
    slot: ProjectionSlot
    focus_statement_id: str
    expected_target_ids: tuple[str, ...]
    observed_target_ids: tuple[str, ...]
    missing_target_ids: tuple[str, ...]
    unexpected_target_ids: tuple[str, ...]
    precision_at_k: float
    recall_at_k: float
    reciprocal_rank: float


@dataclass(frozen=True)
class ClassificationEvaluation:
    case_id: str
    evidence_id: str
    expected: EvidenceClassification
    observed: str | None
    matched: bool


@dataclass(frozen=True)
class StatementEvaluation:
    case_id: str
    statement_id: str
    expected_role: StatementRole
    expected_purpose: StatementPurpose
    expected_authority: StatementAuthority
    observed_role: str | None
    observed_purpose: str | None
    observed_authority: str | None
    matched: bool


@dataclass(frozen=True)
class TransformationAssessmentEvaluation:
    case_id: str
    claim_id: str
    predicate_id: str | None
    expected_status: TransformationAssessmentStatus
    observed_status: str | None
    expected_expectation: TransformationPredicateExpectation | None
    observed_expectation: str | None
    expected_reason_kinds: tuple[TransformationAssessmentReasonKind, ...]
    observed_reason_kinds: tuple[str, ...]
    expected_supporting_evidence_ids: tuple[str, ...]
    observed_supporting_evidence_ids: tuple[str, ...]
    expected_contradicting_evidence_ids: tuple[str, ...]
    observed_contradicting_evidence_ids: tuple[str, ...]
    matched: bool


@dataclass(frozen=True)
class FocusOutcomeEvaluation:
    case_id: str
    subject_id: str
    expected_disposition: StructuralFocusDispositionState
    observed_disposition: str | None
    expected_graph_node_count: int
    observed_graph_node_count: int | None
    expected_closure_fact_count: int
    observed_closure_fact_count: int | None
    expected_closure_revision_states: tuple[str, ...]
    observed_closure_revision_states: tuple[str, ...]
    expected_closure_match_count: int
    observed_closure_match_count: int | None
    matched: bool


@dataclass(frozen=True)
class EvaluationMetrics:
    query_count: int
    positive_query_count: int
    negative_query_count: int
    precision_at_k: float
    recall_at_k: float
    mean_reciprocal_rank: float
    no_candidate_rate: float
    no_match_accuracy: float
    false_positive_rate: float
    classification_accuracy: float
    statement_accuracy: float
    assessment_accuracy: float
    focus_accuracy: float


@dataclass(frozen=True)
class EvaluationResult:
    suite_path: str
    k: int
    passed: bool
    metrics: EvaluationMetrics
    queries: tuple[QueryEvaluation, ...]
    classifications: tuple[ClassificationEvaluation, ...]
    statements: tuple[StatementEvaluation, ...]
    assessments: tuple[TransformationAssessmentEvaluation, ...]
    focus_outcomes: tuple[FocusOutcomeEvaluation, ...]
    shadow_metrics: ShadowEvaluationMetrics
    shadow_outcomes: tuple[ShadowOutcomeEvaluation, ...]
    diagnostics: tuple[str, ...] = ()
    schema_version: str = "evaluation_result.v6"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _RecordedClosureScanner:
    """Replay typed provider observations through the production scanner port."""

    results: ClosureScanResultSet

    def scan(self, plans: ClosureScanPlanSet) -> ClosureScanResultSet:
        self.results.validate_consistency(plans)
        return self.results


def load_evaluation_suite(path: str | Path) -> EvaluationSuite:
    suite_path = Path(path)
    raw = json.loads(suite_path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != "evaluation_suite.v6":
        raise ValueError("evaluation suite must use schema_version evaluation_suite.v6")
    k = int(raw.get("k", 5))
    if k <= 0:
        raise ValueError("evaluation suite k must be positive")
    cases = tuple(
        EvaluationCase(
            id=str(case["id"]),
            fixture=str((suite_path.parent / case["fixture"]).resolve()),
            expected_selections=tuple(
                ExpectedSelection(
                    slot=item["slot"],
                    focus_statement_id=str(item["focus_statement_id"]),
                    target_id=str(item["target_id"]),
                )
                for item in case.get("expected_selections", ())
            ),
            expected_no_selections=tuple(
                ExpectedNoSelection(
                    slot=item["slot"],
                    focus_statement_id=str(item["focus_statement_id"]),
                )
                for item in case.get("expected_no_selections", ())
            ),
            expected_evidence=tuple(
                ExpectedEvidence(
                    evidence_id=str(item["evidence_id"]),
                    classification=item["classification"],
                    profile=item["profile"],
                )
                for item in case.get("expected_evidence", ())
            ),
            expected_statements=tuple(
                ExpectedStatement(
                    statement_id=str(item["statement_id"]),
                    role=item["role"],
                    purpose=item["purpose"],
                    authority=item["authority"],
                )
                for item in case.get("expected_statements", ())
            ),
            expected_assessments=tuple(
                _expected_assessment(item)
                for item in case.get("expected_assessments", ())
            ),
            expected_focus_outcomes=tuple(
                _expected_focus_outcome(item)
                for item in case.get("expected_focus_outcomes", ())
            ),
            structural_graph=(
                _structural_graph(case["structural_graph"])
                if case.get("structural_graph") is not None
                else None
            ),
            closure_scan_results=(
                _closure_scan_results(case["closure_scan_results"])
                if case.get("closure_scan_results") is not None
                else None
            ),
            shadow_execution=(
                str((suite_path.parent / case["shadow_execution"]).resolve())
                if case.get("shadow_execution") is not None
                else None
            ),
            human_shadow_labels=(
                str((suite_path.parent / case["human_shadow_labels"]).resolve())
                if case.get("human_shadow_labels") is not None
                else None
            ),
            expected_shadow_outcomes=tuple(
                _expected_shadow_outcome(item)
                for item in case.get("expected_shadow_outcomes", ())
            ),
        )
        for case in raw.get("cases", ())
    )
    if not cases:
        raise ValueError("evaluation suite must contain at least one case")
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("evaluation case IDs must be unique")
    for case in cases:
        identities = tuple(
            (item.claim_id, item.predicate_id)
            for item in case.expected_assessments
        )
        if len(identities) != len(set(identities)):
            raise ValueError(
                f"evaluation case {case.id} contains duplicate assessment identities"
            )
        focus_ids = tuple(item.subject_id for item in case.expected_focus_outcomes)
        if len(focus_ids) != len(set(focus_ids)):
            raise ValueError(
                f"evaluation case {case.id} contains duplicate focus identities"
            )
        shadow_ids = tuple(item.claim_id for item in case.expected_shadow_outcomes)
        if len(shadow_ids) != len(set(shadow_ids)):
            raise ValueError(
                f"evaluation case {case.id} contains duplicate shadow identities"
            )
        if bool(case.shadow_execution) != bool(case.expected_shadow_outcomes):
            raise ValueError(
                f"evaluation case {case.id} requires both shadow artifact and expectations"
            )
        if case.human_shadow_labels is not None and case.shadow_execution is None:
            raise ValueError(
                f"evaluation case {case.id} human labels require a shadow artifact"
            )
    thresholds = EvaluationThresholds(**raw.get("thresholds", {}))
    _validate_thresholds(thresholds)
    shadow_thresholds = ShadowEvaluationThresholds(
        **raw.get("shadow_thresholds", {})
    )
    _validate_thresholds(shadow_thresholds)
    return EvaluationSuite(
        cases=cases,
        thresholds=thresholds,
        shadow_thresholds=shadow_thresholds,
        k=k,
    )


def evaluate_suite(
    suite: EvaluationSuite,
    *,
    suite_path: str | Path,
) -> EvaluationResult:
    query_results: list[QueryEvaluation] = []
    classification_results: list[ClassificationEvaluation] = []
    statement_results: list[StatementEvaluation] = []
    assessment_results: list[TransformationAssessmentEvaluation] = []
    focus_results: list[FocusOutcomeEvaluation] = []
    shadow_results: list[ShadowOutcomeEvaluation] = []
    diagnostics: list[str] = []

    for case in suite.cases:
        analysis_input = load_fixture(case.fixture)
        if case.structural_graph is not None:
            analysis_input = replace(
                analysis_input,
                structural_graph=case.structural_graph,
            )
        analyzer = DeterministicAnalyzer(
            closure_scanner=(
                _RecordedClosureScanner(case.closure_scan_results)
                if case.closure_scan_results is not None
                else None
            )
        )
        brief = analyzer.analyze(analysis_input)
        grouped = _expected_queries(
            case.expected_selections,
            case.expected_no_selections,
        )
        observed_by_query = _observed_queries(
            brief.projection_candidates.relations,
            selected_relation_ids=set(
                brief.candidate_convergence.selected_relation_ids()
            ),
        )
        for (slot, focus_statement_id), expected_ids in grouped.items():
            observed_ids = observed_by_query.get((slot, focus_statement_id), ())
            query_results.append(
                _evaluate_query(
                    case.id,
                    slot,
                    focus_statement_id,
                    expected_ids,
                    observed_ids,
                    suite.k,
                )
            )
        catalog = brief.evidence_catalog.by_id()
        for expected in case.expected_evidence:
            observed = catalog.get(expected.evidence_id)
            classification_results.append(
                ClassificationEvaluation(
                    case_id=case.id,
                    evidence_id=expected.evidence_id,
                    expected=expected.classification,
                    observed=observed.classification if observed is not None else None,
                    matched=(
                        observed is not None
                        and observed.classification == expected.classification
                        and observed.profile == expected.profile
                    ),
                )
            )
        statements = {
            item.id: item
            for item in (
                *brief.requirements,
                *brief.guardrails,
                *brief.objectives,
                *brief.scope,
                *brief.verification_expectations,
                *brief.claims,
                brief.intent,
            )
        }
        for expected in case.expected_statements:
            observed = statements.get(expected.statement_id)
            statement_results.append(
                StatementEvaluation(
                    case_id=case.id,
                    statement_id=expected.statement_id,
                    expected_role=expected.role,
                    expected_purpose=expected.purpose,
                    expected_authority=expected.authority,
                    observed_role=observed.role if observed is not None else None,
                    observed_purpose=(
                        observed.purpose if observed is not None else None
                    ),
                    observed_authority=(
                        observed.authority if observed is not None else None
                    ),
                    matched=(
                        observed is not None
                        and observed.role == expected.role
                        and observed.purpose == expected.purpose
                        and observed.authority == expected.authority
                    ),
                )
            )
        assessment_results.extend(
            _evaluate_assessments(case.id, case.expected_assessments, brief)
        )
        focus_results.extend(
            _evaluate_focus_outcomes(
                case.id,
                case.expected_focus_outcomes,
                brief,
            )
        )
        if case.shadow_execution is not None:
            shadow_bundle = load_shadow_execution(case.shadow_execution)
            human_labels = (
                load_human_shadow_labels(
                    case.human_shadow_labels,
                    shadow_bundle,
                )
                if case.human_shadow_labels is not None
                else HumanShadowLabelSet(labels=())
            )
            shadow_results.extend(
                evaluate_shadow_outcomes(
                    case.id,
                    case.expected_shadow_outcomes,
                    human_labels,
                    shadow_bundle,
                )
            )
        diagnostics.extend(
            f"{case.id}: {item.slot}: {item.state}: {item.message}"
            for item in (
                *brief.projection_candidates.diagnostics,
                *brief.candidate_convergence.diagnostics,
            )
            if item.state in {"ambiguous", "budget_truncated"}
        )

    diagnostics.extend(_query_diagnostics(tuple(query_results)))
    diagnostics.extend(_classification_diagnostics(tuple(classification_results)))
    diagnostics.extend(_statement_diagnostics(tuple(statement_results)))
    diagnostics.extend(_assessment_diagnostics(tuple(assessment_results)))
    diagnostics.extend(_focus_diagnostics(tuple(focus_results)))
    diagnostics.extend(shadow_diagnostics(tuple(shadow_results)))
    measured_shadow = shadow_metrics(tuple(shadow_results))
    metrics = _metrics(
        tuple(query_results),
        tuple(classification_results),
        tuple(statement_results),
        tuple(assessment_results),
        tuple(focus_results),
    )
    threshold_diagnostics = _threshold_diagnostics(metrics, suite.thresholds)
    threshold_diagnostics = (
        *threshold_diagnostics,
        *shadow_threshold_diagnostics(
            measured_shadow,
            suite.shadow_thresholds,
        ),
    )
    if (
        not query_results
        and not assessment_results
        and not focus_results
        and not shadow_results
    ):
        threshold_diagnostics = (
            *threshold_diagnostics,
            "threshold_failed: no projection, assessment, focus, or shadow assertions were declared",
        )
    diagnostics.extend(threshold_diagnostics)
    passed = not threshold_diagnostics
    return EvaluationResult(
        suite_path=str(Path(suite_path)),
        k=suite.k,
        passed=passed,
        metrics=metrics,
        queries=tuple(query_results),
        classifications=tuple(classification_results),
        statements=tuple(statement_results),
        assessments=tuple(assessment_results),
        focus_outcomes=tuple(focus_results),
        shadow_metrics=measured_shadow,
        shadow_outcomes=tuple(shadow_results),
        diagnostics=tuple(diagnostics),
    )


def _expected_assessment(raw: dict[str, Any]) -> ExpectedTransformationAssessment:
    predicate_id = (
        str(raw["predicate_id"])
        if raw.get("predicate_id") is not None
        else None
    )
    expectation = raw.get("expectation")
    if (predicate_id is None) != (expectation is None):
        raise ValueError(
            "predicate assessment expectations require both predicate_id and expectation"
        )
    status = raw["status"]
    if status not in get_args(TransformationAssessmentStatus):
        raise ValueError(f"unsupported transformation assessment status: {status}")
    if (
        expectation is not None
        and expectation not in get_args(TransformationPredicateExpectation)
    ):
        raise ValueError(
            f"unsupported transformation predicate expectation: {expectation}"
        )
    reason_kinds = tuple(raw.get("reason_kinds", ()))
    unsupported_reasons = tuple(
        item
        for item in reason_kinds
        if item not in get_args(TransformationAssessmentReasonKind)
    )
    if unsupported_reasons:
        raise ValueError(
            "unsupported transformation assessment reasons: "
            + ", ".join(unsupported_reasons)
        )
    return ExpectedTransformationAssessment(
        claim_id=str(raw["claim_id"]),
        predicate_id=predicate_id,
        expectation=expectation,
        status=status,
        reason_kinds=reason_kinds,
        supporting_evidence_ids=tuple(raw.get("supporting_evidence_ids", ())),
        contradicting_evidence_ids=tuple(
            raw.get("contradicting_evidence_ids", ())
        ),
    )


def _expected_focus_outcome(raw: dict[str, Any]) -> ExpectedFocusOutcome:
    disposition = raw["disposition"]
    if disposition not in get_args(StructuralFocusDispositionState):
        raise ValueError(f"unsupported structural focus disposition: {disposition}")
    counts = {
        name: int(raw.get(name, 0))
        for name in (
            "graph_node_count",
            "closure_fact_count",
            "closure_match_count",
        )
    }
    if any(value < 0 for value in counts.values()):
        raise ValueError("focus outcome counts must be non-negative")
    return ExpectedFocusOutcome(
        subject_id=str(raw["subject_id"]),
        disposition=disposition,
        closure_revision_states=tuple(
            str(item) for item in raw.get("closure_revision_states", ())
        ),
        **counts,
    )


def _expected_shadow_outcome(raw: dict[str, Any]) -> ExpectedShadowOutcome:
    unexpected = set(raw) - {
        "claim_id",
        "execution_state",
        "diagnostic_codes",
    }
    if unexpected:
        raise ValueError(
            "shadow execution expectations contain unsupported fields: "
            + ", ".join(sorted(unexpected))
        )
    return ExpectedShadowOutcome(
        claim_id=str(raw["claim_id"]),
        execution_state=raw["execution_state"],
        diagnostic_codes=tuple(raw.get("diagnostic_codes", ())),
    )


def _closure_scan_results(raw: dict[str, Any]) -> ClosureScanResultSet:
    return ClosureScanResultSet(
        results=tuple(
            ClosureScanResult(
                id=str(result["id"]),
                plan_id=str(result["plan_id"]),
                statement_id=str(result["statement_id"]),
                statement_kind=result["statement_kind"],
                expectation=result["expectation"],
                revisions=tuple(
                    ClosureRevisionObservation(
                        revision_side=revision["revision_side"],
                        revision=str(revision.get("revision", "")),
                        root_path=str(revision.get("root_path", ".")),
                        state=revision["state"],
                        coverages=tuple(
                            ClosureScanCoverage(**item)
                            for item in revision.get("coverages", ())
                        ),
                        truncations=tuple(
                            ClosureScanTruncation(**item)
                            for item in revision.get("truncations", ())
                        ),
                        matches=tuple(
                            ClosureScanMatch(**item)
                            for item in revision.get("matches", ())
                        ),
                    )
                    for revision in result.get("revisions", ())
                ),
            )
            for result in raw.get("results", ())
        ),
        schema_version=str(
            raw.get("schema_version", "closure_scan_result_set.v2")
        ),
    )


def _evaluate_assessments(
    case_id: str,
    expected_items: tuple[ExpectedTransformationAssessment, ...],
    brief: ReviewBrief,
) -> tuple[TransformationAssessmentEvaluation, ...]:
    claims = brief.transformation_assessment.by_claim_id()
    bindings = {
        item.id: item for item in brief.transformation_alignment.bindings
    }
    results = []
    for expected in expected_items:
        claim = claims.get(expected.claim_id)
        observed = claim
        if claim is not None and expected.predicate_id is not None:
            observed = next(
                (
                    item
                    for item in claim.predicate_assessments
                    if item.predicate_id == expected.predicate_id
                ),
                None,
            )
        observed_status = observed.status if observed is not None else None
        observed_expectation = (
            observed.expectation
            if observed is not None and expected.predicate_id is not None
            else None
        )
        observed_reasons = (
            tuple(item.kind for item in observed.reasons)
            if observed is not None
            else ()
        )
        supporting = _binding_evidence_ids(
            observed.supporting_binding_ids if observed is not None else (),
            bindings,
        )
        contradicting = _binding_evidence_ids(
            observed.contradicting_binding_ids if observed is not None else (),
            bindings,
        )
        results.append(
            TransformationAssessmentEvaluation(
                case_id=case_id,
                claim_id=expected.claim_id,
                predicate_id=expected.predicate_id,
                expected_status=expected.status,
                observed_status=observed_status,
                expected_expectation=expected.expectation,
                observed_expectation=observed_expectation,
                expected_reason_kinds=expected.reason_kinds,
                observed_reason_kinds=observed_reasons,
                expected_supporting_evidence_ids=(
                    expected.supporting_evidence_ids
                ),
                observed_supporting_evidence_ids=supporting,
                expected_contradicting_evidence_ids=(
                    expected.contradicting_evidence_ids
                ),
                observed_contradicting_evidence_ids=contradicting,
                matched=(
                    observed_status == expected.status
                    and observed_expectation == expected.expectation
                    and observed_reasons == expected.reason_kinds
                    and supporting == expected.supporting_evidence_ids
                    and contradicting == expected.contradicting_evidence_ids
                ),
            )
        )
    return tuple(results)


def _evaluate_focus_outcomes(
    case_id: str,
    expected_items: tuple[ExpectedFocusOutcome, ...],
    brief: ReviewBrief,
) -> tuple[FocusOutcomeEvaluation, ...]:
    inspections = brief.projection.verification_workspace.inspections_by_subject_id()
    evidence = brief.evidence_catalog.by_id()
    results = []
    for expected in expected_items:
        inspection = inspections.get(expected.subject_id)
        closure_facts = tuple(
            evidence[evidence_id]
            for evidence_id in (
                inspection.observed_evidence_ids if inspection is not None else ()
            )
            if evidence_id in evidence
            and evidence[evidence_id].kind == "closure_fact"
            and evidence[evidence_id].closure_scan_result is not None
        )
        revision_states = tuple(
            revision.state
            for fact in closure_facts
            for revision in fact.closure_scan_result.revisions
        )
        match_count = sum(
            len(revision.matches)
            for fact in closure_facts
            for revision in fact.closure_scan_result.revisions
        )
        observed_disposition = (
            inspection.structural_disposition.state
            if inspection is not None
            else None
        )
        graph_node_count = (
            len(inspection.structural_overlay.nodes)
            if inspection is not None
            else None
        )
        closure_fact_count = len(closure_facts) if inspection is not None else None
        observed_match_count = match_count if inspection is not None else None
        results.append(
            FocusOutcomeEvaluation(
                case_id=case_id,
                subject_id=expected.subject_id,
                expected_disposition=expected.disposition,
                observed_disposition=observed_disposition,
                expected_graph_node_count=expected.graph_node_count,
                observed_graph_node_count=graph_node_count,
                expected_closure_fact_count=expected.closure_fact_count,
                observed_closure_fact_count=closure_fact_count,
                expected_closure_revision_states=(
                    expected.closure_revision_states
                ),
                observed_closure_revision_states=revision_states,
                expected_closure_match_count=expected.closure_match_count,
                observed_closure_match_count=observed_match_count,
                matched=(
                    observed_disposition == expected.disposition
                    and graph_node_count == expected.graph_node_count
                    and closure_fact_count == expected.closure_fact_count
                    and revision_states == expected.closure_revision_states
                    and observed_match_count == expected.closure_match_count
                ),
            )
        )
    return tuple(results)


def _binding_evidence_ids(binding_ids, bindings) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            bindings[binding_id].evidence_id
            for binding_id in binding_ids
            if binding_id in bindings
        )
    )


def write_evaluation_json(result: EvaluationResult, output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            result.to_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def write_evaluation_markdown(
    result: EvaluationResult, output: str | Path
) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    metrics = result.metrics
    lines = [
        "# RepoDelta evaluation",
        "",
        f"Status: **{'PASS' if result.passed else 'FAIL'}**",
        "",
        f"- precision@{result.k}: {metrics.precision_at_k:.4f}",
        f"- recall@{result.k}: {metrics.recall_at_k:.4f}",
        f"- mean reciprocal rank: {metrics.mean_reciprocal_rank:.4f}",
        f"- positive-query no-candidate rate: {metrics.no_candidate_rate:.4f}",
        f"- no-match accuracy: {metrics.no_match_accuracy:.4f}",
        f"- false-positive rate: {metrics.false_positive_rate:.4f}",
        f"- classification accuracy: {metrics.classification_accuracy:.4f}",
        f"- statement accuracy: {metrics.statement_accuracy:.4f}",
        f"- transformation assessment accuracy: {metrics.assessment_accuracy:.4f}",
        f"- structural focus accuracy: {metrics.focus_accuracy:.4f}",
        f"- shadow selection precision: {result.shadow_metrics.selection_precision:.4f}",
        f"- shadow selection recall: {result.shadow_metrics.selection_recall:.4f}",
        f"- shadow role accuracy: {result.shadow_metrics.role_accuracy:.4f}",
        f"- shadow human-labeled outcomes: "
        f"{result.shadow_metrics.human_labeled_outcome_count}",
        f"- shadow candidate labels: {result.shadow_metrics.candidate_label_count}",
        f"- shadow disposition accuracy: "
        f"{result.shadow_metrics.disposition_accuracy:.4f}",
        f"- shadow false-rejection rate: "
        f"{result.shadow_metrics.false_rejection_rate:.4f}",
        f"- shadow insufficient recall: "
        f"{result.shadow_metrics.insufficient_recall:.4f}",
        f"- shadow baseline retention: {result.shadow_metrics.baseline_retention:.4f}",
        f"- shadow unresolved precision: {result.shadow_metrics.unresolved_precision:.4f}",
        f"- shadow unresolved recall: {result.shadow_metrics.unresolved_recall:.4f}",
        f"- shadow state accuracy: {result.shadow_metrics.state_accuracy:.4f}",
        f"- shadow diagnostic accuracy: {result.shadow_metrics.diagnostic_accuracy:.4f}",
        f"- shadow usage: {result.shadow_metrics.total_input_tokens} input / "
        f"{result.shadow_metrics.total_output_tokens} output tokens",
        f"- shadow duration: {result.shadow_metrics.total_duration_ms:.2f} ms",
        f"- shadow execution policies: "
        f"{', '.join(result.shadow_metrics.execution_policy_ids) or 'none'}",
        "",
        "## Queries",
        "",
    ]
    for query in result.queries:
        state = (
            "PASS"
            if not query.missing_target_ids and not query.unexpected_target_ids
            else "MISS"
        )
        expected = ", ".join(query.expected_target_ids) or "none"
        lines.append(
            f"- `{query.case_id}` · `{query.slot}` · "
            f"`{query.focus_statement_id}` · "
            f"**{state}** · expected `{expected}` · "
            f"observed `{', '.join(query.observed_target_ids) or 'none'}`"
        )
    if result.classifications:
        lines.extend(("", "## Evidence classifications", ""))
        for item in result.classifications:
            lines.append(
                f"- `{item.case_id}` · `{item.evidence_id}` · "
                f"expected `{item.expected}` · observed `{item.observed or 'missing'}`"
            )
    if result.statements:
        lines.extend(("", "## Statement semantics", ""))
        for item in result.statements:
            lines.append(
                f"- `{item.case_id}` · `{item.statement_id}` · "
                f"expected `{item.expected_role}/{item.expected_purpose}/"
                f"{item.expected_authority}` · observed "
                f"`{item.observed_role or 'missing'}/"
                f"{item.observed_purpose or 'missing'}/"
                f"{item.observed_authority or 'missing'}`"
            )
    if result.assessments:
        lines.extend(("", "## Transformation assessments", ""))
        for item in result.assessments:
            identity = (
                f"{item.claim_id}/{item.predicate_id}"
                if item.predicate_id is not None
                else item.claim_id
            )
            state = "PASS" if item.matched else "MISS"
            lines.append(
                f"- `{item.case_id}` · `{identity}` · **{state}** · "
                f"expected `{item.expected_status}` · observed "
                f"`{item.observed_status or 'missing'}` · reasons "
                f"`{', '.join(item.observed_reason_kinds) or 'none'}`"
            )
    if result.focus_outcomes:
        lines.extend(("", "## Structural focus and closure", ""))
        for item in result.focus_outcomes:
            lines.append(
                f"- `{item.case_id}` · `{item.subject_id}` · "
                f"expected `{item.expected_disposition}`/"
                f"{item.expected_graph_node_count} nodes/"
                f"{item.expected_closure_fact_count} closure facts · observed "
                f"`{item.observed_disposition or 'missing'}`/"
                f"{item.observed_graph_node_count if item.observed_graph_node_count is not None else 'missing'} nodes/"
                f"{item.observed_closure_fact_count if item.observed_closure_fact_count is not None else 'missing'} closure facts"
            )
    if result.shadow_outcomes:
        lines.extend(("", "## LLM shadow observations", ""))
        for item in result.shadow_outcomes:
            lines.append(
                f"- `{item.case_id}` · `{item.claim_id}` · `{item.profile}` · "
                f"expected `{item.expected_execution_state}` · observed "
                f"`{item.observed_execution_state or 'missing'}` · selected "
                f"`{', '.join(item.observed_selection_ids) or 'none'}`"
            )
    if result.diagnostics:
        lines.extend(("", "## Diagnostics", ""))
        lines.extend(f"- {item}" for item in result.diagnostics)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _expected_queries(
    selections: tuple[ExpectedSelection, ...],
    no_selections: tuple[ExpectedNoSelection, ...],
) -> dict[tuple[str, str], tuple[str, ...]]:
    grouped: dict[tuple[str, str], list[str]] = {}
    for query in no_selections:
        grouped.setdefault((query.slot, query.focus_statement_id), [])
    for selection in selections:
        grouped.setdefault(
            (selection.slot, selection.focus_statement_id), []
        ).append(
            selection.target_id
        )
    return {
        key: tuple(sorted(set(target_ids)))
        for key, target_ids in sorted(grouped.items())
    }


def _observed_queries(
    relations: tuple[ProjectionRelation, ...],
    *,
    selected_relation_ids: set[str],
) -> dict[tuple[str, str], tuple[str, ...]]:
    grouped: dict[tuple[str, str], list[str]] = {}
    for relation in relations:
        if relation.id not in selected_relation_ids:
            continue
        grouped.setdefault(
            (relation.slot, relation.focus_statement_id), []
        ).append(
            relation.target_id
        )
    return {key: tuple(target_ids) for key, target_ids in grouped.items()}


def _evaluate_query(
    case_id: str,
    slot: ProjectionSlot,
    focus_statement_id: str,
    expected_ids: tuple[str, ...],
    observed_ids: tuple[str, ...],
    k: int,
) -> QueryEvaluation:
    expected = set(expected_ids)
    top = observed_ids[:k]
    relevant = [target_id for target_id in top if target_id in expected]
    first_rank = next(
        (
            index
            for index, target_id in enumerate(observed_ids, start=1)
            if target_id in expected
        ),
        None,
    )
    if not expected:
        return QueryEvaluation(
            case_id=case_id,
            slot=slot,
            focus_statement_id=focus_statement_id,
            expected_target_ids=(),
            observed_target_ids=top,
            missing_target_ids=(),
            unexpected_target_ids=top,
            precision_at_k=1.0 if not top else 0.0,
            recall_at_k=1.0 if not top else 0.0,
            reciprocal_rank=1.0 if not top else 0.0,
        )
    return QueryEvaluation(
        case_id=case_id,
        slot=slot,
        focus_statement_id=focus_statement_id,
        expected_target_ids=expected_ids,
        observed_target_ids=top,
        missing_target_ids=tuple(sorted(expected - set(observed_ids))),
        unexpected_target_ids=tuple(
            target_id for target_id in top if target_id not in expected
        ),
        precision_at_k=len(relevant) / len(top) if top else 0.0,
        recall_at_k=len(set(relevant)) / len(expected),
        reciprocal_rank=1 / first_rank if first_rank is not None else 0.0,
    )


def _metrics(
    queries: tuple[QueryEvaluation, ...],
    classifications: tuple[ClassificationEvaluation, ...],
    statements: tuple[StatementEvaluation, ...],
    assessments: tuple[TransformationAssessmentEvaluation, ...],
    focus_outcomes: tuple[FocusOutcomeEvaluation, ...],
) -> EvaluationMetrics:
    query_count = len(queries)
    positive_queries = tuple(item for item in queries if item.expected_target_ids)
    negative_queries = tuple(item for item in queries if not item.expected_target_ids)
    classification_count = len(classifications)
    statement_count = len(statements)
    assessment_count = len(assessments)
    focus_count = len(focus_outcomes)
    return EvaluationMetrics(
        query_count=query_count,
        positive_query_count=len(positive_queries),
        negative_query_count=len(negative_queries),
        precision_at_k=(
            sum(item.precision_at_k for item in positive_queries)
            / len(positive_queries)
            if positive_queries
            else 0.0
        ),
        recall_at_k=(
            sum(item.recall_at_k for item in positive_queries)
            / len(positive_queries)
            if positive_queries
            else 0.0
        ),
        mean_reciprocal_rank=(
            sum(item.reciprocal_rank for item in positive_queries)
            / len(positive_queries)
            if positive_queries
            else 0.0
        ),
        no_candidate_rate=(
            sum(not item.observed_target_ids for item in positive_queries)
            / len(positive_queries)
            if positive_queries
            else 0.0
        ),
        no_match_accuracy=(
            sum(not item.observed_target_ids for item in negative_queries)
            / len(negative_queries)
            if negative_queries
            else 1.0
        ),
        false_positive_rate=(
            sum(bool(item.observed_target_ids) for item in negative_queries)
            / len(negative_queries)
            if negative_queries
            else 0.0
        ),
        classification_accuracy=(
            sum(item.matched for item in classifications) / classification_count
            if classification_count
            else 1.0
        ),
        statement_accuracy=(
            sum(item.matched for item in statements) / statement_count
            if statement_count
            else 1.0
        ),
        assessment_accuracy=(
            sum(item.matched for item in assessments) / assessment_count
            if assessment_count
            else 1.0
        ),
        focus_accuracy=(
            sum(item.matched for item in focus_outcomes) / focus_count
            if focus_count
            else 1.0
        ),
    )


def _threshold_diagnostics(
    metrics: EvaluationMetrics, thresholds: EvaluationThresholds
) -> tuple[str, ...]:
    failures = []
    minimums = (
        ("precision_at_k", metrics.precision_at_k, thresholds.precision_at_k),
        ("recall_at_k", metrics.recall_at_k, thresholds.recall_at_k),
        (
            "mean_reciprocal_rank",
            metrics.mean_reciprocal_rank,
            thresholds.mean_reciprocal_rank,
        ),
        (
            "classification_accuracy",
            metrics.classification_accuracy,
            thresholds.classification_accuracy,
        ),
        (
            "no_match_accuracy",
            metrics.no_match_accuracy,
            thresholds.no_match_accuracy,
        ),
        (
            "statement_accuracy",
            metrics.statement_accuracy,
            thresholds.statement_accuracy,
        ),
        (
            "assessment_accuracy",
            metrics.assessment_accuracy,
            thresholds.assessment_accuracy,
        ),
        (
            "focus_accuracy",
            metrics.focus_accuracy,
            thresholds.focus_accuracy,
        ),
    )
    for name, observed, required in minimums:
        if observed < required:
            failures.append(
                f"threshold_failed: {name}={observed:.4f} is below {required:.4f}"
            )
    if metrics.no_candidate_rate > thresholds.max_no_candidate_rate:
        failures.append(
            "threshold_failed: "
            f"no_candidate_rate={metrics.no_candidate_rate:.4f} exceeds "
            f"{thresholds.max_no_candidate_rate:.4f}"
        )
    if metrics.false_positive_rate > thresholds.max_false_positive_rate:
        failures.append(
            "threshold_failed: "
            f"false_positive_rate={metrics.false_positive_rate:.4f} exceeds "
            f"{thresholds.max_false_positive_rate:.4f}"
        )
    return tuple(failures)


def _query_diagnostics(
    queries: tuple[QueryEvaluation, ...],
) -> tuple[str, ...]:
    return tuple(
        "query_mismatch: "
        f"case={item.case_id} slot={item.slot} "
        f"statement={item.focus_statement_id} "
        f"expected=[{', '.join(item.expected_target_ids) or 'none'}] "
        f"observed=[{', '.join(item.observed_target_ids) or 'none'}]"
        for item in queries
        if item.missing_target_ids or item.unexpected_target_ids
    )


def _classification_diagnostics(
    classifications: tuple[ClassificationEvaluation, ...],
) -> tuple[str, ...]:
    return tuple(
        "classification_mismatch: "
        f"case={item.case_id} evidence={item.evidence_id} "
        f"expected={item.expected} observed={item.observed or 'missing'}"
        for item in classifications
        if not item.matched
    )


def _statement_diagnostics(
    statements: tuple[StatementEvaluation, ...],
) -> tuple[str, ...]:
    return tuple(
        "statement_mismatch: "
        f"case={item.case_id} statement={item.statement_id} "
        f"expected={item.expected_role}/{item.expected_purpose}/"
        f"{item.expected_authority} observed={item.observed_role or 'missing'}/"
        f"{item.observed_purpose or 'missing'}/"
        f"{item.observed_authority or 'missing'}"
        for item in statements
        if not item.matched
    )


def _assessment_diagnostics(
    assessments: tuple[TransformationAssessmentEvaluation, ...],
) -> tuple[str, ...]:
    return tuple(
        "assessment_mismatch: "
        f"case={item.case_id} claim={item.claim_id} "
        f"predicate={item.predicate_id or 'aggregate'} "
        f"expected={item.expected_status}/"
        f"{','.join(item.expected_reason_kinds) or 'no_reason'} "
        f"observed={item.observed_status or 'missing'}/"
        f"{','.join(item.observed_reason_kinds) or 'no_reason'}"
        for item in assessments
        if not item.matched
    )


def _focus_diagnostics(
    outcomes: tuple[FocusOutcomeEvaluation, ...],
) -> tuple[str, ...]:
    return tuple(
        "focus_mismatch: "
        f"case={item.case_id} subject={item.subject_id} "
        f"expected={item.expected_disposition}/"
        f"{item.expected_graph_node_count}/"
        f"{item.expected_closure_fact_count}/"
        f"{','.join(item.expected_closure_revision_states) or 'none'}/"
        f"{item.expected_closure_match_count} "
        f"observed={item.observed_disposition or 'missing'}/"
        f"{item.observed_graph_node_count}/"
        f"{item.observed_closure_fact_count}/"
        f"{','.join(item.observed_closure_revision_states) or 'none'}/"
        f"{item.observed_closure_match_count}"
        for item in outcomes
        if not item.matched
    )


def _validate_thresholds(thresholds: EvaluationThresholds) -> None:
    for name, value in asdict(thresholds).items():
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"evaluation threshold {name} must be between 0 and 1")


def _symbol(raw: dict[str, Any]) -> GraphSymbol:
    return GraphSymbol(
        id=str(raw["id"]),
        kind=str(raw["kind"]),
        name=str(raw["name"]),
        qualified_name=str(raw["qualified_name"]),
        file_path=str(raw["file_path"]),
        language=str(raw["language"]),
        start_line=int(raw["start_line"]),
        end_line=int(raw["end_line"]),
    )


def _structural_graph(raw: dict[str, Any]) -> StructuralGraphCollection:
    results = tuple(
        _structural_revision(item) for item in raw.get("revisions", ())
    )
    graph = StructuralGraphCollection(revisions=results)
    graph.validate_consistency()
    return graph


def _structural_revision(raw: dict[str, Any]) -> StructuralGraphResult:
    symbols = {
        symbol["id"]: _symbol(symbol)
        for symbol in raw.get("symbols", ())
    }
    return StructuralGraphResult(
        revision_side=raw["revision_side"],
        index=StructuralGraphIndexStatus(**raw["index"]),
        hunk_count=int(raw.get("hunk_count", 0)),
        overlaps=tuple(
            HunkSymbolOverlap(
                hunk_id=str(item["hunk_id"]),
                symbol=symbols[item["symbol_id"]],
                changed_lines=tuple(int(line) for line in item["changed_lines"]),
            )
            for item in raw.get("overlaps", ())
        ),
        paths=tuple(
            StructuralPath(
                seed_symbol_id=str(item["seed_symbol_id"]),
                steps=tuple(
                    GraphPathStep(
                        source=symbols[step["source_id"]],
                        target=symbols[step["target_id"]],
                        relation=str(step["relation"]),
                        direction=step["direction"],
                    )
                    for step in item.get("steps", ())
                ),
                classification=item["classification"],
            )
            for item in raw.get("paths", ())
        ),
        traversal_coverage=tuple(
            StructuralSeedCoverage(
                seed_symbol_id=str(item["seed_symbol_id"]),
                state=item["state"],
                node_count=int(item["node_count"]),
                path_count=int(item["path_count"]),
                limiting_dimensions=tuple(item.get("limiting_dimensions", ())),
            )
            for item in raw.get("traversal_coverage", ())
        ),
    )
