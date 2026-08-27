"""Evaluation-only R/G identifier specificity and policy shadowing.

R/G association intentionally remains a production-owned decision.  This
module does not re-run selection and does not change a report.  It records the
evidence available at the association boundary so that a future production
change can be chosen from a reproducible counterexample rather than from the
name ``exact_identifier`` alone.

The probe is deliberately conservative.  A term is called canonical only when
it is the complete shaped identifier of a qualified symbol name.  Path text,
diff text, suffix aliases, and signature vocabulary are retained as retrieval
evidence, but never acquire direct authority here.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Mapping

from repodelta.evaluation.association_attribution import (
    AssociationAttributionObservation,
    AssociationAttributionRow,
)
from repodelta.evaluation.structural_correctness import (
    StructuralCorrectnessLabels,
    StructuralCorrectnessObservation,
    StructuralCorrectnessPacket,
)
from repodelta.model.contracts import ReviewBrief
from repodelta.model.predicate_refs import identifier_keys


IDENTIFIER_SPECIFICITY_SCHEMA = "structural_identifier_specificity.v1"
IDENTIFIER_POLICY_SHADOW_SCHEMA = "structural_identifier_policy_shadow.v1"
IDENTIFIER_POLICY_SUMMARY_SCHEMA = "structural_identifier_policy_shadow_summary.v1"
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")
_SUBJECT_KINDS = frozenset({"requirement", "guardrail"})
_DIRECT_CLASSES = frozenset({"asserted", "matched"})
_CHANGED_OPERATIONS = frozenset(
    {"added", "modified", "removed", "renamed", "replaced"}
)

Origin = Literal[
    "qualified_name",
    "path",
    "diff_text",
    "signature_unattributed",
    "unobserved",
]
SourceForm = Literal[
    "full_identifier",
    "suffix_alias",
    "unknown",
]
Resolution = Literal["none", "unique", "multiple", "unobserved"]


@dataclass(frozen=True)
class IdentifierTermObservation:
    """One matched identifier term and the evidence that explains it."""

    term: str
    source_forms: tuple[SourceForm, ...]
    origins: tuple[Origin, ...]
    canonical_full_match_count: int | None
    canonical_resolution: Resolution
    fanout: int

    def __post_init__(self) -> None:
        if not self.term.strip() or not self.source_forms or not self.origins:
            raise ValueError("identifier term observation requires evidence")
        if any(item not in {"full_identifier", "suffix_alias", "unknown"} for item in self.source_forms):
            raise ValueError("identifier term observation has invalid source form")
        if any(item not in {"qualified_name", "path", "diff_text", "signature_unattributed", "unobserved"} for item in self.origins):
            raise ValueError("identifier term observation has invalid origin")
        if self.canonical_resolution not in {"none", "unique", "multiple", "unobserved"}:
            raise ValueError("identifier term observation has invalid resolution")
        if self.canonical_full_match_count is not None and self.canonical_full_match_count < 0:
            raise ValueError("identifier term observation has negative resolution count")
        if self.fanout < 0:
            raise ValueError("identifier term observation has negative fanout")


@dataclass(frozen=True)
class IdentifierSpecificityRow:
    """One R/G association row with typed identifier evidence."""

    subject_id: str
    subject_kind: str
    relation_id: str
    target_id: str
    candidate_node_id: str | None
    candidate_state: str
    association: str
    structural_member_id: str | None
    structural_membership_class: str | None
    terms: tuple[IdentifierTermObservation, ...]


@dataclass(frozen=True)
class IdentifierSpecificityObservation:
    """Immutable, serializable output of the evaluation-only probe."""

    packet_digest: str
    rows: tuple[IdentifierSpecificityRow, ...]
    subject_kinds: tuple[tuple[str, str], ...]
    origin_completeness: Literal["complete", "partial"]
    schema_version: str = IDENTIFIER_SPECIFICITY_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != IDENTIFIER_SPECIFICITY_SCHEMA:
            raise ValueError("unsupported identifier specificity schema")
        if not self.packet_digest:
            raise ValueError("identifier specificity requires packet identity")
        relation_ids = tuple(item.relation_id for item in self.rows)
        if len(relation_ids) != len(set(relation_ids)):
            raise ValueError("identifier specificity rows contain duplicate relations")
        if relation_ids != tuple(sorted(relation_ids)):
            raise ValueError("identifier specificity rows must be canonicalized")
        subject_ids = tuple(item[0] for item in self.subject_kinds)
        if subject_ids != tuple(sorted(subject_ids)):
            raise ValueError("identifier specificity subjects must be canonicalized")
        if len(subject_ids) != len(set(subject_ids)):
            raise ValueError("identifier specificity subjects contain duplicates")
        if any(item[1] not in _SUBJECT_KINDS for item in self.subject_kinds):
            raise ValueError("identifier specificity only accepts R/G subjects")
        if any(item.subject_id not in set(subject_ids) for item in self.rows):
            raise ValueError("identifier specificity row has unknown subject")


def observe_identifier_specificity(
    brief: ReviewBrief,
    packet: StructuralCorrectnessPacket,
    attribution: AssociationAttributionObservation,
) -> IdentifierSpecificityObservation:
    """Observe identifier origins from a live ``ReviewBrief``.

    The packet and attribution are checked against the brief before any data is
    copied.  The probe reads existing evidence signatures and previews but does
    not call the production association or projection code a second time.
    """

    from repodelta.evaluation.structural_correctness import (
        prepare_structural_correctness_packet,
    )

    if prepare_structural_correctness_packet(brief) != packet:
        raise ValueError("structural correctness packet does not match current review")
    if attribution.packet_digest != packet.digest:
        raise ValueError("association attribution does not match packet")
    evidence = brief.evidence_catalog.by_id()
    subjects = {
        item.subject_id: item.subject_kind
        for item in packet.subjects
        if item.subject_kind in _SUBJECT_KINDS
    }
    statements = {
        item.subject_id: item.authored_statement for item in packet.subjects
    }
    symbol_by_id = {item.node_id: item for item in packet.symbols}
    rows_by_focus: dict[str, list[AssociationAttributionRow]] = defaultdict(list)
    for row in attribution.rows:
        rows_by_focus[row.subject_id].append(row)
    changed_symbols = tuple(
        item for item in packet.symbols if item.operation in _CHANGED_OPERATIONS
    )
    source_forms_by_focus = {
        subject_id: _source_forms(statement)
        for subject_id, statement in statements.items()
    }
    result_rows: list[IdentifierSpecificityRow] = []
    complete = True
    for row in attribution.rows:
        if row.association != "exact_identifier" or not row.matched_terms:
            continue
        exact_terms = _primary_exact_terms(row)
        if not exact_terms:
            raise ValueError(
                f"exact identifier row {row.relation_id} has no primary terms"
            )
        target = evidence.get(row.target_id)
        candidate = symbol_by_id.get(row.candidate_node_id or "")
        if target is None:
            complete = False
        diff_evidence = _change_relation_evidence(target, evidence)
        term_rows = tuple(
            _term_observation(
                term,
                source_forms_by_focus.get(row.subject_id, {}),
                target,
                candidate,
                changed_symbols,
                rows_by_focus[row.subject_id],
                diff_evidence,
            )
            for term in exact_terms
        )
        if any(
            set(item.origins) & {"unobserved", "signature_unattributed"}
            for item in term_rows
        ):
            complete = False
        result_rows.append(
            IdentifierSpecificityRow(
                subject_id=row.subject_id,
                subject_kind=row.subject_kind,
                relation_id=row.relation_id,
                target_id=row.target_id,
                candidate_node_id=row.candidate_node_id,
                candidate_state=row.candidate_state,
                association=row.association,
                structural_member_id=row.structural_member_id,
                structural_membership_class=row.structural_membership_class,
                terms=term_rows,
            )
        )
    return IdentifierSpecificityObservation(
        packet_digest=packet.digest,
        rows=tuple(sorted(result_rows, key=lambda item: item.relation_id)),
        subject_kinds=tuple(sorted(subjects.items())),
        origin_completeness="complete" if complete else "partial",
    )


def observe_identifier_specificity_from_artifacts(
    packet: StructuralCorrectnessPacket,
    attribution: AssociationAttributionObservation,
) -> IdentifierSpecificityObservation:
    """Build a historical probe when only frozen packet/sidecar data exists.

    v1.1 packets intentionally contain no model answer or raw diff text.  This
    adapter therefore records canonical-name/path evidence and marks missing
    evidence as ``unobserved`` instead of pretending that an origin was known.
    It is useful for replaying frozen campaigns while preserving that limit.
    """

    if attribution.packet_digest != packet.digest:
        raise ValueError("association attribution does not match packet")
    symbols = {item.node_id: item for item in packet.symbols}
    subjects = {
        item.subject_id: item.subject_kind
        for item in packet.subjects
        if item.subject_kind in _SUBJECT_KINDS
    }
    statements = {item.subject_id: item.authored_statement for item in packet.subjects}
    changed_symbols = tuple(
        item for item in packet.symbols if item.operation in _CHANGED_OPERATIONS
    )
    forms_by_focus = {
        subject_id: _source_forms(statement)
        for subject_id, statement in statements.items()
    }
    rows_by_focus: dict[str, list[AssociationAttributionRow]] = defaultdict(list)
    for row in attribution.rows:
        rows_by_focus[row.subject_id].append(row)
    result_rows: list[IdentifierSpecificityRow] = []
    for row in attribution.rows:
        if row.association != "exact_identifier" or not row.matched_terms:
            continue
        exact_terms = _primary_exact_terms(row)
        if not exact_terms:
            raise ValueError(
                f"exact identifier row {row.relation_id} has no primary terms"
            )
        candidate = symbols.get(row.candidate_node_id or "")
        terms = tuple(
            _term_observation(
                term,
                forms_by_focus.get(row.subject_id, {}),
                None,
                candidate,
                changed_symbols,
                rows_by_focus[row.subject_id],
                (),
                artifact_only=True,
            )
            for term in exact_terms
        )
        result_rows.append(
            IdentifierSpecificityRow(
                subject_id=row.subject_id,
                subject_kind=row.subject_kind,
                relation_id=row.relation_id,
                target_id=row.target_id,
                candidate_node_id=row.candidate_node_id,
                candidate_state=row.candidate_state,
                association=row.association,
                structural_member_id=row.structural_member_id,
                structural_membership_class=row.structural_membership_class,
                terms=terms,
            )
        )
    return IdentifierSpecificityObservation(
        packet_digest=packet.digest,
        rows=tuple(sorted(result_rows, key=lambda item: item.relation_id)),
        subject_kinds=tuple(sorted(subjects.items())),
        origin_completeness="partial",
    )


def write_identifier_specificity(
    value: IdentifierSpecificityObservation,
    output: str | Path,
) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_identifier_specificity(path: str | Path) -> IdentifierSpecificityObservation:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping) or raw.get("schema_version") != IDENTIFIER_SPECIFICITY_SCHEMA:
        raise ValueError("unsupported identifier specificity artifact")
    raw_rows = raw.get("rows", [])
    if not isinstance(raw_rows, list) or not all(isinstance(item, Mapping) for item in raw_rows):
        raise ValueError("identifier specificity rows must be objects")
    rows = tuple(
        IdentifierSpecificityRow(
            subject_id=_string(item, "subject_id"),
            subject_kind=_string(item, "subject_kind"),
            relation_id=_string(item, "relation_id"),
            target_id=_string(item, "target_id"),
            candidate_node_id=_optional_string(item.get("candidate_node_id")),
            candidate_state=_string(item, "candidate_state"),
            association=_string(item, "association"),
            structural_member_id=_optional_string(item.get("structural_member_id")),
            structural_membership_class=_optional_string(item.get("structural_membership_class")),
            terms=tuple(_term_from_mapping(term) for term in _objects(item, "terms")),
        )
        for item in raw_rows
    )
    raw_subjects = raw.get("subject_kinds", [])
    if not isinstance(raw_subjects, list):
        raise ValueError("identifier specificity subject_kinds must be a list")
    if not all(isinstance(item, list) and len(item) == 2 for item in raw_subjects):
        raise ValueError("identifier specificity subject kinds must be pairs")
    subjects = tuple((str(item[0]), str(item[1])) for item in raw_subjects)
    completeness = raw.get("origin_completeness")
    if completeness not in {"complete", "partial"}:
        raise ValueError("identifier specificity has invalid completeness")
    return IdentifierSpecificityObservation(
        packet_digest=_string(raw, "packet_digest"),
        rows=tuple(sorted(rows, key=lambda item: item.relation_id)),
        subject_kinds=tuple(sorted(subjects)),
        origin_completeness=completeness,
        schema_version=str(raw["schema_version"]),
    )


def compare_identifier_policies(
    packet: StructuralCorrectnessPacket,
    observation: StructuralCorrectnessObservation,
    labels: StructuralCorrectnessLabels,
    attribution: AssociationAttributionObservation,
    specificity: IdentifierSpecificityObservation,
) -> dict[str, Any]:
    """Compare conservative direct-admission policies without replaying closure.

    ``current`` is a reproduction of observed direct membership.  The other
    policies are bounded projections over recorded exact-identifier rows; they
    intentionally do not claim to predict selected/context/relation changes.
    """

    for value, name in (
        (observation.packet_digest, "observation"),
        (labels.packet_digest, "labels"),
        (attribution.packet_digest, "attribution"),
        (specificity.packet_digest, "specificity"),
    ):
        if value != packet.digest:
            raise ValueError(f"{name} does not match packet")
    specificity_by_relation = {item.relation_id: item for item in specificity.rows}
    attribution_rows_by_focus: dict[str, list[AssociationAttributionRow]] = defaultdict(list)
    for row in attribution.rows:
        attribution_rows_by_focus[row.subject_id].append(row)
    observed_by_focus = {item.subject_id: item for item in observation.focuses}
    references_by_focus = {item.subject_id: item for item in labels.focuses}
    subject_kinds = dict(attribution.subject_kinds)
    policies = {
        "current": "reproduce observed direct membership; no policy change",
        "no_suffix": "accept exact identifiers only when the authored term is not suffix-only",
        "low_fanout": "accept only a full identifier with canonical origin and focus fanout one",
        "canonical_unique": "accept only a full qualified-name identifier resolving to one changed symbol",
    }
    policy_sets: dict[str, dict[str, set[str]]] = {
        name: {} for name in policies
    }
    completeness: dict[str, str] = {}
    for subject_id, subject_kind in sorted(subject_kinds.items()):
        current = observed_by_focus.get(subject_id)
        reference = references_by_focus.get(subject_id)
        if current is None or reference is None:
            raise ValueError(f"policy comparison focus {subject_id} is missing")
        observed_direct = set(current.direct_node_ids)
        rows = attribution_rows_by_focus[subject_id]
        rows_by_member: dict[str, list[AssociationAttributionRow]] = defaultdict(list)
        for row in rows:
            if row.structural_member_id is not None and row.structural_membership_class in _DIRECT_CLASSES:
                rows_by_member[row.structural_member_id].append(row)
        missing = observed_direct - set(rows_by_member)
        completeness[subject_id] = "complete" if not missing else "incomplete"
        if missing:
            raise ValueError(
                f"direct membership for {subject_id} has no observed admission row: "
                + ", ".join(sorted(missing))
            )
        for policy in policies:
            if policy == "current":
                policy_sets[policy][subject_id] = set(observed_direct)
                continue
            accepted: set[str] = set()
            for member_id, member_rows in rows_by_member.items():
                non_exact = [row for row in member_rows if row.association != "exact_identifier"]
                exact = [specificity_by_relation.get(row.relation_id) for row in member_rows if row.association == "exact_identifier"]
                if non_exact:
                    accepted.add(member_id)
                    continue
                if any(
                    term_ok(policy, term)
                    for item in exact
                    if item is not None
                    for term in item.terms
                ):
                    accepted.add(member_id)
            policy_sets[policy][subject_id] = accepted
    per_focus: list[dict[str, Any]] = []
    totals = {
        policy: {"false_inclusions": 0, "false_exclusions": 0}
        for policy in policies
    }
    for subject_id in sorted(subject_kinds):
        current = observed_by_focus[subject_id]
        reference = references_by_focus[subject_id]
        result: dict[str, Any] = {
            "subject_id": subject_id,
            "subject_kind": subject_kinds[subject_id],
            "reference_unresolved": reference.unresolved,
            "direct_membership_complete": completeness[subject_id],
            "policies": {},
        }
        for policy in policies:
            actual = policy_sets[policy][subject_id]
            if reference.unresolved:
                result["policies"][policy] = {
                    "observed_direct_nodes": sorted(actual),
                    "comparison": "reference_unresolved",
                }
                continue
            expected = set(reference.direct_node_ids)
            fi = actual - expected
            fe = expected - actual
            result["policies"][policy] = {
                "observed_direct_nodes": sorted(actual),
                "false_inclusions": len(fi),
                "false_exclusions": len(fe),
                "false_inclusion_nodes": sorted(fi),
                "false_exclusion_nodes": sorted(fe),
            }
            totals[policy]["false_inclusions"] += len(fi)
            totals[policy]["false_exclusions"] += len(fe)
        per_focus.append(result)
    by_subject_kind: dict[str, dict[str, dict[str, int]]] = {}
    for focus in per_focus:
        if focus["reference_unresolved"]:
            continue
        kind = focus["subject_kind"]
        entry = by_subject_kind.setdefault(kind, {})
        for policy in policies:
            policy_totals = entry.setdefault(
                policy, {"false_inclusions": 0, "false_exclusions": 0}
            )
            policy_totals["false_inclusions"] += focus["policies"][policy]["false_inclusions"]
            policy_totals["false_exclusions"] += focus["policies"][policy]["false_exclusions"]
    return {
        "schema_version": IDENTIFIER_POLICY_SHADOW_SCHEMA,
        "packet_digest": packet.digest,
        "specificity_origin_completeness": specificity.origin_completeness,
        "causal_replay": False,
        "downstream_replay": False,
        "policies": policies,
        "overall": totals,
        "by_subject_kind": by_subject_kind,
        "per_focus": per_focus,
        "limits": {
            "authority": "evaluation-only; no production association or projection is changed",
            "direct_dimension": "only observed direct member admission is projected",
            "downstream": "selected/context/relation effects are not replayed",
            "semantic_resolution": "no LLM or semantic model is used; grounded semantic policy remains unexplored",
            "historical_origin": "v1.1 artifacts without raw evidence are marked partial/unobserved",
        },
    }


def write_identifier_policy_shadow(value: Mapping[str, Any], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def aggregate_identifier_policy_shadows(
    shadows: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Aggregate independent policy shadows without changing their scope."""

    if not shadows:
        raise ValueError("identifier policy aggregate requires samples")
    for name, value in shadows.items():
        if value.get("schema_version") != IDENTIFIER_POLICY_SHADOW_SCHEMA:
            raise ValueError(f"unsupported identifier policy shadow in {name}")
    policy_names = tuple(next(iter(shadows.values()))["policies"])
    overall = {
        policy: {"false_inclusions": 0, "false_exclusions": 0}
        for policy in policy_names
    }
    by_subject_kind: dict[str, dict[str, dict[str, int]]] = {}
    completeness = {str(value.get("specificity_origin_completeness", "partial")) for value in shadows.values()}
    for value in shadows.values():
        if tuple(value.get("policies", {})) != policy_names:
            raise ValueError("identifier policy shadow policy sets differ")
        for policy in policy_names:
            for field in ("false_inclusions", "false_exclusions"):
                overall[policy][field] += int(value["overall"][policy][field])
        for subject_kind, policy_values in value.get("by_subject_kind", {}).items():
            destination = by_subject_kind.setdefault(subject_kind, {})
            for policy in policy_names:
                entry = destination.setdefault(
                    policy, {"false_inclusions": 0, "false_exclusions": 0}
                )
                entry["false_inclusions"] += int(
                    policy_values[policy]["false_inclusions"]
                )
                entry["false_exclusions"] += int(
                    policy_values[policy]["false_exclusions"]
                )
    return {
        "schema_version": IDENTIFIER_POLICY_SUMMARY_SCHEMA,
        "sample_count": len(shadows),
        "samples": sorted(shadows),
        "specificity_origin_completeness": (
            next(iter(completeness)) if len(completeness) == 1 else "mixed"
        ),
        "policies": {
            policy: next(iter(shadows.values()))["policies"][policy]
            for policy in policy_names
        },
        "overall": overall,
        "by_subject_kind": by_subject_kind,
        "limits": {
            "causal_replay": False,
            "downstream_replay": False,
            "authority": "evaluation-only; no production selection or assessment changes",
        },
    }


def _term_observation(
    term: str,
    source_forms: Mapping[str, tuple[SourceForm, ...]],
    target: Any,
    candidate: Any,
    changed_symbols: tuple[Any, ...],
    focus_rows: list[AssociationAttributionRow],
    diff_evidence: tuple[Any, ...],
    *,
    artifact_only: bool = False,
) -> IdentifierTermObservation:
    forms = source_forms.get(term, ("unknown",))
    origins: set[Origin] = set()
    if candidate is not None:
        if term in _full_identifier_keys(candidate.qualified_name):
            origins.add("qualified_name")
        if term in identifier_keys(candidate.path):
            origins.add("path")
    if target is not None:
        metadata = target.metadata
        path = str(metadata.get("path", ""))
        if term in identifier_keys(path):
            origins.add("path")
        previews = "\n".join(
            str(metadata.get(key, ""))
            for key in ("head_preview", "base_preview", "summary")
        )
        if term in identifier_keys(previews):
            origins.add("diff_text")
        signature_terms = {
            *target.head_signature.identifiers,
            *target.base_signature.identifiers,
        }
        for relation_evidence in diff_evidence:
            previews = "\n".join(
                str(relation_evidence.metadata.get(key, ""))
                for key in ("head_preview", "base_preview")
            )
            if term in identifier_keys(previews):
                origins.add("diff_text")
        if term in signature_terms and not (
            origins & {"qualified_name", "path", "diff_text"}
        ):
            origins.add("signature_unattributed")
    elif artifact_only:
        if not origins:
            origins.add("unobserved")
    else:
        origins.add("unobserved")
    if not origins:
        origins.add("unobserved")
    full_count: int | None
    if artifact_only or candidate is not None or changed_symbols:
        full_count = sum(
            term in _full_identifier_keys(symbol.qualified_name)
            for symbol in changed_symbols
        )
        resolution: Resolution = (
            "none" if full_count == 0 else "unique" if full_count == 1 else "multiple"
        )
    else:
        full_count = None
        resolution = "unobserved"
    fanout = len(
        {
            item.candidate_node_id or item.target_id
            for item in focus_rows
            if item.association == "exact_identifier"
            and term in _primary_exact_terms(item)
        }
    )
    return IdentifierTermObservation(
        term=term,
        source_forms=tuple(sorted(set(forms))),
        origins=tuple(sorted(origins)),
        canonical_full_match_count=full_count,
        canonical_resolution=resolution,
        fanout=fanout,
    )


def term_ok(policy: str, term: IdentifierTermObservation) -> bool:
    """Return whether a term satisfies one named shadow policy."""

    if policy == "current":
        return True
    full = "full_identifier" in term.source_forms
    suffix_only = set(term.source_forms) == {"suffix_alias"}
    canonical = "qualified_name" in term.origins
    if policy == "no_suffix":
        return full and not suffix_only
    if policy == "low_fanout":
        return full and canonical and term.fanout == 1
    if policy == "canonical_unique":
        return (
            full
            and canonical
            and term.canonical_resolution == "unique"
        )
    raise ValueError(f"unknown identifier policy: {policy}")


def _primary_exact_terms(row: AssociationAttributionRow) -> tuple[str, ...]:
    """Return only the terms owned by the primary exact reason.

    Attribution rows flatten all reason terms for compatibility.  The probe's
    specificity contract must not treat bridge/support terms as identifier
    evidence, even when the row also has an exact primary reason.
    """

    return tuple(
        dict.fromkeys(
            term
            for reason in row.reasons
            if reason.kind == "exact_identifier"
            for term in reason.matched_terms
        )
    )


def _change_relation_evidence(
    target: Any,
    evidence: Mapping[str, Any],
) -> tuple[Any, ...]:
    """Resolve raw diff previews through structural change relation IDs only."""

    if target is None:
        return ()
    relation_ids = set(getattr(target, "change_relation_ids", ()))
    identity = getattr(target, "structural_change", None)
    if identity is not None:
        relation_ids.update(getattr(target, "change_relation_ids", ()))
    if target.kind == "change_relation":
        return (target,)
    if not relation_ids:
        return ()
    matches = tuple(
        item
        for item in evidence.values()
        if item.kind == "change_relation"
        and relation_ids.intersection(item.change_relation_ids)
    )
    return tuple(sorted(matches, key=lambda item: item.id))


def _source_forms(statement: str) -> dict[str, tuple[SourceForm, ...]]:
    result: dict[str, set[SourceForm]] = defaultdict(set)
    for match in _WORD_RE.findall(statement):
        keys = tuple(identifier_keys(match))
        if not keys:
            continue
        parts = [part.casefold() for part in match.split("_") if part]
        shaped = "".join(part for part in parts if len(part) >= 3 or part.isdigit())
        full = shaped if len(shaped) >= 5 else ""
        for key in keys:
            result[key].add("full_identifier" if key == full else "suffix_alias")
    return {key: tuple(sorted(value)) for key, value in result.items()}


def _full_identifier_keys(value: str) -> frozenset[str]:
    result: set[str] = set()
    for token in _WORD_RE.findall(value):
        if "_" not in token and not any(char.isupper() for char in token[1:]):
            continue
        parts = [part.casefold() for part in token.split("_") if part]
        parts = [part for part in parts if len(part) >= 3 or part.isdigit()]
        collapsed = "".join(parts)
        if len(collapsed) >= 5:
            result.add(collapsed)
    return frozenset(result)


def _term_from_mapping(raw: Mapping[str, Any]) -> IdentifierTermObservation:
    forms = tuple(str(item) for item in raw.get("source_forms", []))
    origins = tuple(str(item) for item in raw.get("origins", []))
    return IdentifierTermObservation(
        term=_string(raw, "term"),
        source_forms=forms,  # type: ignore[arg-type]
        origins=origins,  # type: ignore[arg-type]
        canonical_full_match_count=(
            int(raw["canonical_full_match_count"])
            if raw.get("canonical_full_match_count") is not None
            else None
        ),
        canonical_resolution=str(raw.get("canonical_resolution", "unobserved")),  # type: ignore[arg-type]
        fanout=int(raw.get("fanout", 0)),
    )


def _string(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"identifier specificity requires {key}")
    return value


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("identifier specificity optional identity must be a string")
    return value


def _objects(raw: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = raw.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise ValueError(f"identifier specificity {key} must be objects")
    return list(value)
