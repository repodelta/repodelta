from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, get_args

from prismcode.pipeline import DeterministicAnalyzer
from prismcode.model.contracts import (
    EvidenceClassification,
    FactProfile,
    ProjectionRelation,
    ProjectionSlot,
    ReviewBrief,
    StatementAuthority,
    StatementPurpose,
    StatementRole,
    TransformationAssessmentReasonKind,
    TransformationAssessmentStatus,
    TransformationPredicateExpectation,
)
from prismcode.intake.fixture import load_fixture
from prismcode.providers.structural import (
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
class EvaluationCase:
    id: str
    fixture: str
    expected_selections: tuple[ExpectedSelection, ...]
    expected_no_selections: tuple[ExpectedNoSelection, ...] = ()
    expected_evidence: tuple[ExpectedEvidence, ...] = ()
    expected_statements: tuple[ExpectedStatement, ...] = ()
    expected_assessments: tuple[ExpectedTransformationAssessment, ...] = ()
    structural_graph: StructuralGraphCollection | None = None


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


@dataclass(frozen=True)
class EvaluationSuite:
    cases: tuple[EvaluationCase, ...]
    thresholds: EvaluationThresholds = EvaluationThresholds()
    k: int = 5
    schema_version: str = "evaluation_suite.v3"


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
    diagnostics: tuple[str, ...] = ()
    schema_version: str = "evaluation_result.v3"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_evaluation_suite(path: str | Path) -> EvaluationSuite:
    suite_path = Path(path)
    raw = json.loads(suite_path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != "evaluation_suite.v3":
        raise ValueError("evaluation suite must use schema_version evaluation_suite.v3")
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
            structural_graph=(
                _structural_graph(case["structural_graph"])
                if case.get("structural_graph") is not None
                else None
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
    thresholds = EvaluationThresholds(**raw.get("thresholds", {}))
    _validate_thresholds(thresholds)
    return EvaluationSuite(
        cases=cases,
        thresholds=thresholds,
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
    diagnostics: list[str] = []

    for case in suite.cases:
        analysis_input = load_fixture(case.fixture)
        if case.structural_graph is not None:
            analysis_input = replace(
                analysis_input,
                structural_graph=case.structural_graph,
            )
        brief = DeterministicAnalyzer().analyze(analysis_input)
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
    metrics = _metrics(
        tuple(query_results),
        tuple(classification_results),
        tuple(statement_results),
        tuple(assessment_results),
    )
    threshold_diagnostics = _threshold_diagnostics(metrics, suite.thresholds)
    if not query_results and not assessment_results:
        threshold_diagnostics = (
            *threshold_diagnostics,
            "threshold_failed: no projection or assessment assertions were declared",
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
        "# PrismCode evaluation",
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
) -> EvaluationMetrics:
    query_count = len(queries)
    positive_queries = tuple(item for item in queries if item.expected_target_ids)
    negative_queries = tuple(item for item in queries if not item.expected_target_ids)
    classification_count = len(classifications)
    statement_count = len(statements)
    assessment_count = len(assessments)
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
