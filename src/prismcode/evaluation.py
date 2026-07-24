from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from .analysis import DeterministicAnalyzer
from .contracts import CandidateBinding, EvidenceClassification
from .fixture import load_fixture
from .structural_graph import (
    GraphPathStep,
    GraphSymbol,
    HunkSymbolOverlap,
    StructuralGraphIndexStatus,
    StructuralGraphResult,
    StructuralPath,
)


@dataclass(frozen=True)
class ExpectedBinding:
    kind: str
    source_id: str
    target_id: str


@dataclass(frozen=True)
class ExpectedEvidence:
    evidence_id: str
    classification: EvidenceClassification


@dataclass(frozen=True)
class ExpectedNoBinding:
    kind: str
    source_id: str


@dataclass(frozen=True)
class EvaluationCase:
    id: str
    fixture: str
    expected_bindings: tuple[ExpectedBinding, ...]
    expected_no_bindings: tuple[ExpectedNoBinding, ...] = ()
    expected_evidence: tuple[ExpectedEvidence, ...] = ()
    structural_graph: StructuralGraphResult | None = None


@dataclass(frozen=True)
class EvaluationThresholds:
    precision_at_k: float = 0.0
    recall_at_k: float = 0.0
    mean_reciprocal_rank: float = 0.0
    classification_accuracy: float = 0.0
    max_no_candidate_rate: float = 1.0


@dataclass(frozen=True)
class EvaluationSuite:
    cases: tuple[EvaluationCase, ...]
    thresholds: EvaluationThresholds = EvaluationThresholds()
    k: int = 5
    schema_version: str = "evaluation_suite.v1"


@dataclass(frozen=True)
class QueryEvaluation:
    case_id: str
    kind: str
    source_id: str
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
class EvaluationMetrics:
    query_count: int
    precision_at_k: float
    recall_at_k: float
    mean_reciprocal_rank: float
    no_candidate_rate: float
    classification_accuracy: float


@dataclass(frozen=True)
class EvaluationResult:
    suite_path: str
    k: int
    passed: bool
    metrics: EvaluationMetrics
    queries: tuple[QueryEvaluation, ...]
    classifications: tuple[ClassificationEvaluation, ...]
    diagnostics: tuple[str, ...] = ()
    schema_version: str = "evaluation_result.v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_evaluation_suite(path: str | Path) -> EvaluationSuite:
    suite_path = Path(path)
    raw = json.loads(suite_path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != "evaluation_suite.v1":
        raise ValueError("evaluation suite must use schema_version evaluation_suite.v1")
    k = int(raw.get("k", 5))
    if k <= 0:
        raise ValueError("evaluation suite k must be positive")
    cases = tuple(
        EvaluationCase(
            id=str(case["id"]),
            fixture=str((suite_path.parent / case["fixture"]).resolve()),
            expected_bindings=tuple(
                ExpectedBinding(
                    kind=str(item["kind"]),
                    source_id=str(item["source_id"]),
                    target_id=str(item["target_id"]),
                )
                for item in case.get("expected_bindings", ())
            ),
            expected_no_bindings=tuple(
                ExpectedNoBinding(
                    kind=str(item["kind"]),
                    source_id=str(item["source_id"]),
                )
                for item in case.get("expected_no_bindings", ())
            ),
            expected_evidence=tuple(
                ExpectedEvidence(
                    evidence_id=str(item["evidence_id"]),
                    classification=item["classification"],
                )
                for item in case.get("expected_evidence", ())
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
            case.expected_bindings,
            case.expected_no_bindings,
        )
        observed_by_query = _observed_queries(brief.candidate_bindings.items)
        for (kind, source_id), expected_ids in grouped.items():
            observed_ids = observed_by_query.get((kind, source_id), ())
            query_results.append(
                _evaluate_query(
                    case.id,
                    kind,
                    source_id,
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
                    ),
                )
            )
        diagnostics.extend(
            f"{case.id}: {item.code}: {item.message}"
            for item in brief.candidate_bindings.diagnostics
        )

    metrics = _metrics(tuple(query_results), tuple(classification_results))
    threshold_diagnostics = _threshold_diagnostics(metrics, suite.thresholds)
    diagnostics.extend(threshold_diagnostics)
    passed = not threshold_diagnostics
    return EvaluationResult(
        suite_path=str(Path(suite_path)),
        k=suite.k,
        passed=passed,
        metrics=metrics,
        queries=tuple(query_results),
        classifications=tuple(classification_results),
        diagnostics=tuple(diagnostics),
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
        f"- no-candidate rate: {metrics.no_candidate_rate:.4f}",
        f"- classification accuracy: {metrics.classification_accuracy:.4f}",
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
            f"- `{query.case_id}` · `{query.kind}` · `{query.source_id}` · "
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
    if result.diagnostics:
        lines.extend(("", "## Diagnostics", ""))
        lines.extend(f"- {item}" for item in result.diagnostics)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _expected_queries(
    bindings: tuple[ExpectedBinding, ...],
    no_bindings: tuple[ExpectedNoBinding, ...],
) -> dict[tuple[str, str], tuple[str, ...]]:
    grouped: dict[tuple[str, str], list[str]] = {}
    for query in no_bindings:
        grouped.setdefault((query.kind, query.source_id), [])
    for binding in bindings:
        grouped.setdefault((binding.kind, binding.source_id), []).append(
            binding.target_id
        )
    return {
        key: tuple(sorted(set(target_ids)))
        for key, target_ids in sorted(grouped.items())
    }


def _observed_queries(
    bindings: tuple[CandidateBinding, ...],
) -> dict[tuple[str, str], tuple[str, ...]]:
    grouped: dict[tuple[str, str], list[str]] = {}
    for binding in bindings:
        grouped.setdefault((binding.kind, binding.source_id), []).append(
            binding.target_id
        )
    return {key: tuple(target_ids) for key, target_ids in grouped.items()}


def _evaluate_query(
    case_id: str,
    kind: str,
    source_id: str,
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
            kind=kind,
            source_id=source_id,
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
        kind=kind,
        source_id=source_id,
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
) -> EvaluationMetrics:
    query_count = len(queries)
    positive_queries = tuple(item for item in queries if item.expected_target_ids)
    classification_count = len(classifications)
    return EvaluationMetrics(
        query_count=query_count,
        precision_at_k=(
            sum(item.precision_at_k for item in queries) / query_count
            if query_count
            else 0.0
        ),
        recall_at_k=(
            sum(item.recall_at_k for item in queries) / query_count
            if query_count
            else 0.0
        ),
        mean_reciprocal_rank=(
            sum(item.reciprocal_rank for item in queries) / query_count
            if query_count
            else 0.0
        ),
        no_candidate_rate=(
            sum(not item.observed_target_ids for item in positive_queries)
            / len(positive_queries)
            if positive_queries
            else 0.0
        ),
        classification_accuracy=(
            sum(item.matched for item in classifications) / classification_count
            if classification_count
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
    return tuple(failures)


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


def _structural_graph(raw: dict[str, Any]) -> StructuralGraphResult:
    symbols = {
        symbol["id"]: _symbol(symbol)
        for symbol in raw.get("symbols", ())
    }
    return StructuralGraphResult(
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
    )
