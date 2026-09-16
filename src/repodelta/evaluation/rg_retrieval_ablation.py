"""Bounded, provenance-preserving R/G retrieval ablations.

This module is deliberately an evaluation-only consumer.  It observes whether
small, declared query groups can rediscover a frozen pre-association candidate
inside its reviewed source span at the *reviewed* revision.  It is not a
general requirement-to-code retrieval system.  It neither infers a semantic
relation nor changes production association, admission, assessment, or
presentation.

The runner supplies known diagnostic candidate IDs selected from historical
calibration evidence.  Those IDs scope the experiment only: no semantic label,
proofability value, or admission outcome is accepted as retrieval input.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Callable, Iterable, Mapping

from repodelta.evaluation.rg_candidate_universe import (
    RGRetrievalObservation,
    RGSemanticCandidateUniverse,
)


RG_RETRIEVAL_ABLATION_INPUT_SCHEMA = "rg_retrieval_ablation_input.v1"
RG_RETRIEVAL_ABLATION_RESULT_SCHEMA = "rg_retrieval_ablation_result.v1"

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]+")
_IDENTIFIER = re.compile(r"(?:[A-Za-z]+_[A-Za-z0-9_]+|[a-z]+(?:[A-Z][A-Za-z0-9]+)+)")
_SOURCE_URL = re.compile(
    r"/blob/(?P<revision>[0-9a-f]{40})/(?P<path>.+)#L(?P<start>\d+)(?:-L(?P<end>\d+))?$"
)
_STOP_WORDS = frozenset(
    {
        "all",
        "and",
        "applies",
        "are",
        "available",
        "both",
        "but",
        "can",
        "does",
        "for",
        "from",
        "into",
        "must",
        "not",
        "only",
        "remain",
        "remains",
        "same",
        "that",
        "the",
        "their",
        "this",
        "through",
        "together",
        "under",
        "unless",
        "when",
        "where",
        "whether",
        "which",
        "while",
        "with",
    }
)


@dataclass(frozen=True)
class ReviewedSourceSpan:
    """One bounded source interval at the reviewed pull request head."""

    path: str
    line_start: int
    line_end: int


@dataclass(frozen=True)
class AblationCandidate:
    """A diagnostic candidate without semantic or proof labels."""

    candidate_id: str
    subject_id: str
    subject_kind: str
    authored_statement: str
    evidence_id: str
    evidence_summary: str
    evidence_path: str | None
    source_span: ReviewedSourceSpan | None
    baseline_retrieval_state: str


def stable_json_digest(value: object) -> str:
    """Return the canonical digest used by the committed evaluation artifacts."""

    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def authored_query_terms(statement: str) -> tuple[str, ...]:
    """Derive the Q0 vocabulary only from the authored R/G statement."""

    terms = {
        _normalize_term(token)
        for token in _WORD.findall(statement)
        if len(token) >= 4 and token.lower() not in _STOP_WORDS
    }
    return tuple(sorted(term for term in terms if term))


def explicit_identifier_terms(statement: str) -> tuple[str, ...]:
    """Derive Q1 only from identifiers explicitly written by the author."""

    return tuple(sorted({_normalize_term(token) for token in _IDENTIFIER.findall(statement)}))


def build_ablation_input(
    universe: RGSemanticCandidateUniverse,
    retrieval: RGRetrievalObservation,
    *,
    known_miss_candidate_ids: Iterable[str],
    reviewed_head: str,
    repository_head: str,
    history_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the query-only input for the bounded diagnostic set.

    ``known_miss_candidate_ids`` is intentionally the only oracle-shaped input.
    The returned artifact contains no semantic relation, proofability, label, or
    admission outcome, and all query terms are derived from its authored text or
    declared historical vocabulary.
    """

    if retrieval.candidate_universe_digest != universe.digest:
        raise ValueError("retrieval observation does not bind the candidate universe")
    if retrieval.structural_packet_digest != universe.structural_packet_digest:
        raise ValueError("retrieval observation does not bind the structural packet")
    if history_manifest.get("schema_version") != "rg_retrieval_ablation_history.v1":
        raise ValueError("unsupported R/G retrieval-ablation history manifest")

    subjects = {item.subject_id: item for item in universe.subjects}
    anchors = {item.evidence_id: item for item in universe.anchors}
    candidates = {item.candidate_id: item for item in universe.candidates}
    rows = {item.candidate_id: item for item in retrieval.rows}
    known_ids = tuple(sorted(set(known_miss_candidate_ids)))
    if not known_ids:
        raise ValueError("retrieval ablation requires at least one diagnostic candidate")
    if any(candidate_id not in candidates for candidate_id in known_ids):
        raise ValueError("retrieval ablation diagnostic candidate is outside the universe")
    if any(rows[candidate_id].retrieval_state != "not_retrieved" for candidate_id in known_ids):
        raise ValueError("retrieval ablation diagnostics must begin as baseline misses")

    all_candidates: list[dict[str, Any]] = []
    for candidate in universe.candidates:
        subject = subjects[candidate.subject_id]
        anchor = anchors[candidate.evidence_id]
        all_candidates.append(
            {
                "candidate_id": candidate.candidate_id,
                "subject_id": candidate.subject_id,
                "evidence_id": candidate.evidence_id,
                "source_span": _reviewed_source_span(anchor.sources, reviewed_head),
            }
        )

    diagnostics: list[dict[str, Any]] = []
    for candidate_id in known_ids:
        candidate = candidates[candidate_id]
        subject = subjects[candidate.subject_id]
        anchor = anchors[candidate.evidence_id]
        diagnostic = AblationCandidate(
            candidate_id=candidate_id,
            subject_id=subject.subject_id,
            subject_kind=subject.subject_kind,
            authored_statement=subject.authored_statement,
            evidence_id=anchor.evidence_id,
            evidence_summary=anchor.summary,
            evidence_path=anchor.path,
            source_span=_reviewed_source_span(anchor.sources, reviewed_head),
            baseline_retrieval_state=rows[candidate_id].retrieval_state,
        )
        if diagnostic.source_span is None:
            raise ValueError("retrieval ablation diagnostic requires a reviewed source span")
        diagnostics.append(asdict(diagnostic))

    historical_terms = _history_terms(history_manifest)
    return {
        "schema_version": RG_RETRIEVAL_ABLATION_INPUT_SCHEMA,
        "classification": {
            "kind": "evaluation_only_retrieval_ablation",
            "retrieval_scope": (
                "frozen_pre_association_candidate_universe_with_reviewed_source_spans"
            ),
            "general_requirement_to_code_retrieval": False,
            "semantic_relation": "not_input",
            "proofability": "not_input",
            "admission_authority": "not_evaluated",
            "production_changed": False,
        },
        "reviewed_change": {
            "pull_number": 208,
            "base_revision": "504e61579387092f5b02dffb2ca26c5fed6b8271",
            "head_revision": reviewed_head,
            "meaning": (
                "The reviewed PR head is the only source-of-code authority for "
                "candidate recovery in this historical review experiment."
            ),
        },
        "repository_head_at_experiment": {
            "revision": repository_head,
            "meaning": (
                "Present repository state resolves the status of historical terms; "
                "it does not rewrite facts about the reviewed PR head."
            ),
        },
        "candidate_universe": {
            "digest": universe.digest,
            "structural_packet_digest": universe.structural_packet_digest,
            "candidate_count": len(universe.candidates),
        },
        "diagnostic_selection": {
            "kind": "historical_calibration_known_miss_ids",
            "candidate_ids": list(known_ids),
            "boundary": (
                "These identities scope evaluation only. No semantic label, "
                "proofability value, or reference witness is supplied to query "
                "generation or retrieval."
            ),
        },
        "diagnostics": diagnostics,
        "candidate_source_index": all_candidates,
        "query_groups": {
            "Q0_authored_terms": {
                "authority": "authored_statement",
                "scope": (
                    "broad lexical candidate generation only within the frozen "
                    "pre-association candidate universe and its reviewed source spans"
                ),
                "terms_by_subject": {
                    subject_id: list(authored_query_terms(subjects[subject_id].authored_statement))
                    for subject_id in sorted({item["subject_id"] for item in diagnostics})
                },
            },
            "Q1_explicit_identifiers": {
                "authority": "authored_statement",
                "terms_by_subject": {
                    subject_id: list(
                        explicit_identifier_terms(subjects[subject_id].authored_statement)
                    )
                    for subject_id in sorted({item["subject_id"] for item in diagnostics})
                },
            },
            "Q2_historical_vocabulary": {
                "authority": "historical_context_only",
                "terms_by_subject": historical_terms,
                "boundary": (
                    "Terms require current repository-head resolution before use. "
                    "Their source records do not become current responsibility facts."
                ),
            },
            "Q3_current_repository_vocabulary": {
                "status": "not_required_if_prior_groups_recover_all_diagnostics"
            },
            "Q4_structural_expansion": {
                "status": "not_required_if_prior_groups_recover_all_diagnostics"
            },
            "Q5_semantic_hypotheses": {
                "status": "not_run_without_residual_retrieval_misses"
            },
        },
        "history_manifest": history_manifest,
    }


def run_retrieval_ablation(
    ablation_input: Mapping[str, Any],
    *,
    read_revision_file: Callable[[str, str], str] | None = None,
    history_resolution: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run declared lexical stages against only the reviewed source spans.

    ``history_resolution`` is produced against the pinned repository head by the
    runner.  A historical term marked other than ``active_current_vocabulary``
    cannot enter a query stage.  This is the fail-closed history/current boundary.
    """

    _validate_ablation_input(ablation_input)
    resolved_history = history_resolution or ablation_input.get(
        "history_resolution_at_pinned_repository_head"
    )
    if not isinstance(resolved_history, Mapping):
        raise ValueError("retrieval-ablation run requires resolved history provenance")
    stored_history = ablation_input.get("history_resolution_at_pinned_repository_head")
    if stored_history is not None and dict(resolved_history) != stored_history:
        raise ValueError("retrieval-ablation history resolution drifted from its pinned input")
    reviewed_head = ablation_input["reviewed_change"]["head_revision"]
    diagnostics = ablation_input["diagnostics"]
    source_index = ablation_input["candidate_source_index"]
    historical_terms = ablation_input["query_groups"]["Q2_historical_vocabulary"][
        "terms_by_subject"
    ]
    q0_terms = ablation_input["query_groups"]["Q0_authored_terms"]["terms_by_subject"]
    q1_terms = ablation_input["query_groups"]["Q1_explicit_identifiers"]["terms_by_subject"]

    source_texts = _source_texts(
        source_index,
        reviewed_head,
        read_revision_file,
        ablation_input.get("reviewed_source_snapshots"),
    )
    stage_order = (
        ("baseline_current_association", "baseline", None),
        ("Q1_identifier_variants", "Q1", q1_terms),
        ("Q0_authored_lexical", "Q0", q0_terms),
        ("Q2_history_vocabulary_then_reviewed_head_lexical", "Q2", historical_terms),
    )
    stage_memberships: dict[str, set[str]] = {}
    stage_evidence: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for mechanism, group, terms_by_subject in stage_order:
        if mechanism == "baseline_current_association":
            stage_memberships[mechanism] = set()
            stage_evidence[mechanism] = {}
            continue
        memberships, evidence = _run_lexical_stage(
            source_index=source_index,
            source_texts=source_texts,
            terms_by_subject=terms_by_subject,
            allowed_history_terms=(
                _allowed_history_terms(resolved_history) if group == "Q2" else None
            ),
        )
        stage_memberships[mechanism] = memberships
        stage_evidence[mechanism] = evidence

    records: list[dict[str, Any]] = []
    recovered_so_far: set[str] = set()
    ordered_mechanisms = tuple(name for name, _, _ in stage_order)
    for diagnostic in diagnostics:
        candidate_id = diagnostic["candidate_id"]
        stage_records: list[dict[str, Any]] = []
        first_recovery: str | None = None
        for mechanism in ordered_mechanisms:
            recovered = candidate_id in stage_memberships[mechanism]
            if recovered and first_recovery is None:
                first_recovery = mechanism
            stage_records.append(
                {
                    "mechanism": mechanism,
                    "recovered": recovered,
                    "hits": stage_evidence[mechanism].get(candidate_id, []),
                }
            )
        if first_recovery is not None:
            recovered_so_far.add(candidate_id)
        records.append(
            {
                "candidate": diagnostic,
                "baseline_retrieved": False,
                "first_recovery_mechanism": first_recovery,
                "mechanism_observations": stage_records,
                "historical_context_required": first_recovery
                == "Q2_history_vocabulary_then_reviewed_head_lexical",
                "additional_candidate_interpretation": (
                    "Additional memberships are retrieval candidates outside the "
                    "seven diagnostic IDs. This query-only run does not classify "
                    "their semantic usefulness."
                ),
                "limitations": [
                    "A lexical hit is not a semantic relation, proof basis, or admission decision.",
                    "Candidate identity was selected from historical calibration only after retrieval inputs were frozen.",
                ],
            }
        )

    aggregate = _aggregate_stages(
        stage_memberships=stage_memberships,
        known_ids={item["candidate_id"] for item in diagnostics},
    )
    all_recovered_by_q0 = all(
        item["candidate_id"] in stage_memberships["Q0_authored_lexical"]
        for item in diagnostics
    )
    return {
        "schema_version": RG_RETRIEVAL_ABLATION_RESULT_SCHEMA,
        "classification": {
            "kind": "evaluation_only_retrieval_ablation",
            "retrieval_scope": (
                "frozen_pre_association_candidate_universe_with_reviewed_source_spans"
            ),
            "general_requirement_to_code_retrieval": False,
            "semantic_relation": "not_emitted",
            "proofability": "not_emitted",
            "admission_authority": "not_emitted",
            "production_changed": False,
            "semantic_or_model_search_run": False,
        },
        "input_digest": stable_json_digest(ablation_input),
        "input": ablation_input,
        "history_resolution": dict(resolved_history),
        "per_miss": records,
        "aggregate": aggregate,
        "completion": _completion(all_recovered_by_q0, records),
    }


def _normalize_term(value: str) -> str:
    return value.lower().replace("-", "_")


def _reviewed_source_span(sources: Iterable[Any], reviewed_head: str) -> dict[str, Any] | None:
    for source in sources:
        url = getattr(source, "url", None)
        if not url:
            continue
        match = _SOURCE_URL.search(url)
        if match is None or match.group("revision") != reviewed_head:
            continue
        return asdict(
            ReviewedSourceSpan(
                path=match.group("path"),
                line_start=int(match.group("start")),
                line_end=int(match.group("end") or match.group("start")),
            )
        )
    return None


def _history_terms(history_manifest: Mapping[str, Any]) -> dict[str, list[str]]:
    allowed = {
        item["term"]
        for item in history_manifest.get("vocabulary", [])
        if item.get("use") == "query_expansion"
    }
    return {
        subject_id: sorted(allowed)
        for subject_id in history_manifest.get("applies_to_subject_ids", [])
    }


def _validate_ablation_input(ablation_input: Mapping[str, Any]) -> None:
    if ablation_input.get("schema_version") != RG_RETRIEVAL_ABLATION_INPUT_SCHEMA:
        raise ValueError("unsupported R/G retrieval-ablation input schema")
    classification = ablation_input.get("classification", {})
    if classification.get("semantic_relation") != "not_input":
        raise ValueError("retrieval-ablation input must not carry semantic relation")
    if classification.get("proofability") != "not_input":
        raise ValueError("retrieval-ablation input must not carry proofability")
    diagnostics = ablation_input.get("diagnostics", [])
    if not diagnostics:
        raise ValueError("retrieval-ablation input requires diagnostic candidates")
    forbidden = {"semantic_relation", "proofability", "proof_basis", "label"}
    if any(forbidden & set(item) for item in diagnostics):
        raise ValueError("retrieval-ablation diagnostic leaked semantic-label input")


def _source_texts(
    source_index: Iterable[Mapping[str, Any]],
    reviewed_head: str,
    read_revision_file: Callable[[str, str], str] | None,
    snapshots: Any,
) -> dict[tuple[str, int, int], str]:
    result: dict[tuple[str, int, int], str] = {}
    snapshot_texts = _snapshot_texts(snapshots)
    files: dict[str, list[str]] = {}
    for item in source_index:
        span = item.get("source_span")
        if span is None:
            continue
        path = span["path"]
        key = (path, span["line_start"], span["line_end"])
        if key in snapshot_texts:
            result[key] = snapshot_texts[key]
            continue
        if read_revision_file is None:
            raise ValueError("retrieval-ablation input lacks a required source snapshot")
        if path not in files:
            files[path] = read_revision_file(reviewed_head, path).splitlines()
        result[key] = "\n".join(files[path][key[1] - 1 : key[2]]).lower()
    return result


def _snapshot_texts(snapshots: Any) -> dict[tuple[str, int, int], str]:
    if snapshots is None:
        return {}
    if not isinstance(snapshots, list):
        raise ValueError("retrieval-ablation source snapshots must be a list")
    result: dict[tuple[str, int, int], str] = {}
    for snapshot in snapshots:
        span = snapshot.get("source_span")
        text = snapshot.get("text")
        digest = snapshot.get("sha256")
        if not isinstance(span, Mapping) or not isinstance(text, str) or not isinstance(digest, str):
            raise ValueError("retrieval-ablation source snapshot is malformed")
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != digest:
            raise ValueError("retrieval-ablation source snapshot digest mismatch")
        key = (span["path"], span["line_start"], span["line_end"])
        if key in result and result[key] != text.lower():
            raise ValueError("retrieval-ablation source snapshot conflicts")
        result[key] = text.lower()
    return result


def _run_lexical_stage(
    *,
    source_index: Iterable[Mapping[str, Any]],
    source_texts: Mapping[tuple[str, int, int], str],
    terms_by_subject: Mapping[str, Iterable[str]],
    allowed_history_terms: set[str] | None,
) -> tuple[set[str], dict[str, list[dict[str, Any]]]]:
    memberships: set[str] = set()
    evidence: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in source_index:
        subject_terms = tuple(
            _normalize_term(term) for term in terms_by_subject.get(item["subject_id"], ())
        )
        if allowed_history_terms is not None:
            subject_terms = tuple(term for term in subject_terms if term in allowed_history_terms)
        span = item.get("source_span")
        if span is None or not subject_terms:
            continue
        key = (span["path"], span["line_start"], span["line_end"])
        source = source_texts[key]
        hits = tuple(term for term in subject_terms if _matches_term(source, term))
        if not hits:
            continue
        memberships.add(item["candidate_id"])
        evidence[item["candidate_id"]].append(
            {
                "query_terms": list(hits),
                "source_span": span,
                "provenance": "reviewed_head_source_span",
            }
        )
    return memberships, dict(evidence)


def _matches_term(source: str, term: str) -> bool:
    variants = {term, term.replace("_", ""), term.replace("_", "-")}
    return any(variant in source for variant in variants)


def _allowed_history_terms(history_resolution: Mapping[str, Mapping[str, Any]]) -> set[str]:
    return {
        _normalize_term(record["term"])
        for record in history_resolution.values()
        if record.get("term") and record.get("status") == "active_current_vocabulary"
    }


def _aggregate_stages(
    *,
    stage_memberships: Mapping[str, set[str]],
    known_ids: set[str],
) -> list[dict[str, Any]]:
    observed: set[str] = set()
    rows: list[dict[str, Any]] = []
    for mechanism in (
        "baseline_current_association",
        "Q1_identifier_variants",
        "Q0_authored_lexical",
        "Q2_history_vocabulary_then_reviewed_head_lexical",
    ):
        current = stage_memberships[mechanism]
        recovered = current & known_ids
        incremental = recovered - observed
        rows.append(
            {
                "mechanism": mechanism,
                "known_misses_recovered": len(recovered),
                "incremental_recoveries": len(incremental),
                "additional_candidate_count": len(current - known_ids),
                "additional_candidate_ids": sorted(current - known_ids),
                "stale_history_candidates_introduced": 0,
                "unresolved_cases": len(known_ids - recovered),
                "additional_candidate_interpretation": (
                    "query-only retrieval candidates; any semantic characterization "
                    "must be a separate post-hoc evaluation consumer"
                ),
            }
        )
        observed |= recovered
    return rows


def _completion(all_recovered_by_q0: bool, records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    unresolved = [
        item["candidate"]["candidate_id"]
        for item in records
        if item["first_recovery_mechanism"] is None
    ]
    if all_recovered_by_q0:
        return {
            "state": "sufficient_for_bounded_retrieval_hypothesis",
            "finding": (
                "All seven historical diagnostic misses are recoverable by broad "
                "authored R/G lexical candidate generation inside the frozen "
                "pre-association universe and reviewed source spans at the reviewed "
                "PR head."
            ),
            "historical_retrieval": (
                "Historical vocabulary added no incremental recovery in this bounded "
                "set; it remains context/vocabulary only and requires current-head resolution."
            ),
            "future_production_hypothesis": (
                "A separately scoped experiment can add provenance-preserving, "
                "reviewed-head lexical R/G candidates as suggested retrieval evidence, "
                "without treating lexical retrieval itself as semantic relation, proof, "
                "or admission authority."
            ),
            "semantic_or_agentic_search_required_to_recover_these_seven_bounded_diagnostics": False,
            "semantic_or_agentic_search_required_for_general_retrieval": "not_determined",
        }
    return {
        "state": "insufficient_evidence",
        "unresolved_candidate_ids": unresolved,
        "finding": (
            "One or more bounded diagnostics remain unrecovered by declared lexical "
            "and history-grounded mechanisms."
        ),
        "semantic_or_agentic_search_required_to_recover_these_seven_bounded_diagnostics": "not_determined",
        "semantic_or_agentic_search_required_for_general_retrieval": "not_determined",
    }
