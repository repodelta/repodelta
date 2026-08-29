"""Evaluation-only R/G candidate, reference, and retrieval artifacts.

The production R/G projection currently decides which profile-eligible changed
anchors have deterministic associations.  This module deliberately observes a
larger, earlier boundary: every profile-eligible changed-anchor fact.  It keeps
that bounded candidate universe, the current association observation, and an
independently reviewed semantic/proofability reference separate.

Nothing here changes production association, convergence, projection,
assessment, or report output.  In particular, lexical association, canonical
node resolution, and model confidence are recorded as evidence; none becomes
semantic-direct authority in this module.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Literal, Mapping

from repodelta.evaluation.structural_correctness import (
    StructuralCorrectnessPacket,
    prepare_structural_correctness_packet,
)
from repodelta.model.contracts import (
    AssociationKind,
    AssociationReason,
    EvidenceItem,
    Requirement,
    RequirementProfile,
    ReviewBrief,
    SourceRef,
)
from repodelta.model.structural_refs import review_symbol_id
from repodelta.routing.semantics import (
    anchor_key,
    eligible_changed_anchor,
    focus_evidence_role,
    requirement_profile,
)


RG_CANDIDATE_UNIVERSE_SCHEMA = "rg_semantic_candidate_universe.v1"
RG_RETRIEVAL_OBSERVATION_SCHEMA = "rg_semantic_candidate_retrieval.v1"
RG_SEMANTIC_REFERENCE_SCHEMA = "rg_semantic_candidate_reference.v2"
RG_SEMANTIC_COMPARISON_SCHEMA = "rg_semantic_candidate_comparison.v1"

_SUBJECT_KINDS = frozenset({"requirement", "guardrail"})
_ANCHOR_KINDS = frozenset(
    {"structural_change", "change_relation", "changed_file"}
)
_DIRECT_ASSOCIATIONS = frozenset({"provided_association", "exact_identifier"})
_DIRECT_RELATIONS = frozenset(
    {"implements", "constrains", "removes", "directly_verifies"}
)

CandidateNodeState = Literal[
    "node_resolved", "node_unresolved", "not_node_backed"
]
RetrievalState = Literal["not_retrieved", "selected", "deferred"]
SemanticRelation = Literal[
    "implements",
    "constrains",
    "removes",
    "directly_verifies",
    "contextual_support",
    "unrelated",
    "insufficient",
]
Proofability = Literal[
    "direct_capable", "suggested_only", "not_applicable", "insufficient"
]
ReferenceLabelStatus = Literal["pending", "reviewed"]
ProofBasis = Literal[
    "explicit_authoring",
    "typed_predicate",
    "bounded_evidence",
    "deterministic_mapping",
    "heuristic",
    "model_suggestion",
    "none",
]
ReferenceCoverageKind = Literal["out_of_universe"]


@dataclass(frozen=True)
class CandidateSourceRef:
    """Source identity carried into the bounded labeler packet."""

    label: str
    url: str | None = None
    path: str | None = None
    line_start: int | None = None
    line_end: int | None = None


@dataclass(frozen=True)
class RGSemanticSubject:
    subject_id: str
    subject_kind: Literal["requirement", "guardrail"]
    authored_statement: str
    profile: RequirementProfile


@dataclass(frozen=True)
class RGSemanticAnchorFact:
    """One changed-anchor fact, retained once for every candidate membership."""

    evidence_id: str
    evidence_kind: str
    classification: str
    profile: str
    revision_side: str
    operation: str
    summary: str
    path: str | None
    change_relation_ids: tuple[str, ...]
    sources: tuple[CandidateSourceRef, ...]
    canonical_review_symbol_id: str | None
    canonical_node_id: str | None
    node_state: CandidateNodeState

    def __post_init__(self) -> None:
        if not self.evidence_id:
            raise ValueError("R/G anchor fact requires a stable evidence identity")
        if self.evidence_kind not in _ANCHOR_KINDS:
            raise ValueError("R/G candidate requires a changed-anchor fact kind")
        if self.node_state not in {
            "node_resolved",
            "node_unresolved",
            "not_node_backed",
        }:
            raise ValueError("R/G candidate has invalid canonical-node state")
        if self.node_state == "node_resolved" and not self.canonical_node_id:
            raise ValueError("resolved R/G candidate requires a graph node")
        if self.node_state == "node_unresolved" and not self.canonical_review_symbol_id:
            raise ValueError("unresolved R/G candidate requires a review symbol")
        if self.node_state == "not_node_backed" and (
            self.canonical_review_symbol_id is not None
            or self.canonical_node_id is not None
        ):
            raise ValueError("non-node candidate cannot name a canonical node")
        if self.node_state != "node_resolved" and self.canonical_node_id is not None:
            raise ValueError("only resolved R/G candidates may name a graph node")
        if len(self.change_relation_ids) != len(set(self.change_relation_ids)):
            raise ValueError("R/G candidate repeats change relation identities")


@dataclass(frozen=True)
class RGSemanticCandidate:
    """One subject-to-anchor membership in the frozen candidate universe."""

    candidate_id: str
    subject_id: str
    evidence_id: str
    evidence_role: str

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.subject_id or not self.evidence_id:
            raise ValueError("R/G candidate requires stable identities")


@dataclass(frozen=True)
class RGSemanticCandidateUniverse:
    """Blind structural candidate surface, before association and selection."""

    structural_packet_digest: str
    subjects: tuple[RGSemanticSubject, ...]
    anchors: tuple[RGSemanticAnchorFact, ...]
    candidates: tuple[RGSemanticCandidate, ...]
    schema_version: str = RG_CANDIDATE_UNIVERSE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != RG_CANDIDATE_UNIVERSE_SCHEMA:
            raise ValueError("unsupported R/G candidate universe schema")
        if not self.structural_packet_digest:
            raise ValueError("R/G candidate universe requires structural packet identity")
        subject_ids = tuple(item.subject_id for item in self.subjects)
        if subject_ids != tuple(sorted(subject_ids)) or len(subject_ids) != len(
            set(subject_ids)
        ):
            raise ValueError("R/G candidate subjects must be unique and canonical")
        if any(item.subject_kind not in _SUBJECT_KINDS for item in self.subjects):
            raise ValueError("R/G candidate universe requires R/G subjects")
        anchor_ids = tuple(item.evidence_id for item in self.anchors)
        if anchor_ids != tuple(sorted(anchor_ids)) or len(anchor_ids) != len(
            set(anchor_ids)
        ):
            raise ValueError("R/G anchor facts must be unique and canonical")
        candidate_ids = tuple(item.candidate_id for item in self.candidates)
        if candidate_ids != tuple(sorted(candidate_ids)) or len(candidate_ids) != len(
            set(candidate_ids)
        ):
            raise ValueError("R/G candidates must be unique and canonical")
        if any(item.subject_id not in set(subject_ids) for item in self.candidates):
            raise ValueError("R/G candidate belongs to an unknown subject")
        if any(item.evidence_id not in set(anchor_ids) for item in self.candidates):
            raise ValueError("R/G candidate references an unknown anchor fact")

    @property
    def digest(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RGRetrievalObservationRow:
    """Current production association observed for one frozen candidate."""

    candidate_id: str
    retrieval_state: RetrievalState
    relation_id: str | None = None
    association: AssociationKind | None = None
    reasons: tuple[AssociationReason, ...] = ()

    def __post_init__(self) -> None:
        if not self.candidate_id:
            raise ValueError("R/G retrieval row requires candidate identity")
        if self.retrieval_state not in {
            "not_retrieved",
            "selected",
            "deferred",
        }:
            raise ValueError("R/G retrieval row has invalid state")
        observed = self.retrieval_state != "not_retrieved"
        if observed != (self.relation_id is not None):
            raise ValueError("R/G retrieval relation must match retrieval state")
        if observed != (self.association is not None):
            raise ValueError("R/G retrieval association must match retrieval state")
        if observed != bool(self.reasons):
            raise ValueError("R/G retrieval reasons must match retrieval state")
        if self.association is not None and self.reasons[0].kind != self.association:
            raise ValueError("R/G retrieval reasons must lead with association")


@dataclass(frozen=True)
class RGRetrievalObservation:
    """Observed current R/G retrieval; it does not label semantic relevance."""

    structural_packet_digest: str
    candidate_universe_digest: str
    rows: tuple[RGRetrievalObservationRow, ...]
    schema_version: str = RG_RETRIEVAL_OBSERVATION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != RG_RETRIEVAL_OBSERVATION_SCHEMA:
            raise ValueError("unsupported R/G retrieval observation schema")
        if not self.structural_packet_digest or not self.candidate_universe_digest:
            raise ValueError("R/G retrieval observation requires packet identities")
        candidate_ids = tuple(item.candidate_id for item in self.rows)
        if candidate_ids != tuple(sorted(candidate_ids)) or len(candidate_ids) != len(
            set(candidate_ids)
        ):
            raise ValueError("R/G retrieval rows must be unique and canonical")


@dataclass(frozen=True)
class RGSemanticReferenceAuthority:
    status: Literal["proposed", "verified"]
    proposed_by: str
    verified_by: str = ""
    verification_method: str = ""
    verification_evidence: tuple[str, ...] = ()
    system_under_test_isolated: bool = False
    proposal_digest: str = ""


@dataclass(frozen=True)
class RGSemanticReferenceLabel:
    candidate_id: str
    semantic_relation: SemanticRelation
    proofability: Proofability
    proof_basis: ProofBasis
    evidence_witnesses: tuple[str, ...] = ()
    note: str = ""
    review_status: ReferenceLabelStatus = "reviewed"

    def __post_init__(self) -> None:
        if not self.candidate_id:
            raise ValueError("R/G semantic label requires candidate identity")
        if self.semantic_relation not in {
            "implements",
            "constrains",
            "removes",
            "directly_verifies",
            "contextual_support",
            "unrelated",
            "insufficient",
        }:
            raise ValueError("R/G semantic label has invalid relation")
        if self.proofability not in {
            "direct_capable",
            "suggested_only",
            "not_applicable",
            "insufficient",
        }:
            raise ValueError("R/G semantic label has invalid proofability")
        if self.proof_basis not in {
            "explicit_authoring",
            "typed_predicate",
            "bounded_evidence",
            "deterministic_mapping",
            "heuristic",
            "model_suggestion",
            "none",
        }:
            raise ValueError("R/G semantic label has invalid proof basis")
        if self.review_status not in {"pending", "reviewed"}:
            raise ValueError("R/G semantic label has invalid review status")
        if self.review_status == "pending":
            if (
                self.semantic_relation != "insufficient"
                or self.proofability != "insufficient"
                or self.proof_basis != "none"
                or self.evidence_witnesses
                or self.note
            ):
                raise ValueError(
                    "pending R/G semantic label cannot make a semantic judgment"
                )
            return
        direct = self.semantic_relation in _DIRECT_RELATIONS
        if direct and self.proofability not in {
            "direct_capable",
            "suggested_only",
        }:
            raise ValueError("semantic-direct label requires a proofability state")
        if direct and not self.evidence_witnesses:
            raise ValueError("semantic-direct label requires evidence witnesses")
        if self.proofability == "direct_capable" and (
            not direct
            or self.proof_basis
            not in {
                "explicit_authoring",
                "typed_predicate",
                "bounded_evidence",
                "deterministic_mapping",
            }
        ):
            raise ValueError("direct-capable label requires grounded direct evidence")
        if self.proofability == "suggested_only" and (
            not direct or self.proof_basis not in {"heuristic", "model_suggestion"}
        ):
            raise ValueError("suggested-only label requires non-authoritative evidence")
        if self.semantic_relation == "insufficient" and (
            self.proofability != "insufficient" or self.proof_basis != "none"
        ):
            raise ValueError("insufficient semantic label cannot claim proof")
        if not direct and self.semantic_relation != "insufficient" and (
            self.proofability != "not_applicable" or self.proof_basis != "none"
        ):
            raise ValueError("non-direct semantic label cannot claim direct proof")


@dataclass(frozen=True)
class RGSemanticReferenceGap:
    """A reviewed semantic expectation the bounded candidate universe missed."""

    subject_id: str
    semantic_relation: Literal[
        "implements", "constrains", "removes", "directly_verifies"
    ]
    source_identity: str
    evidence_witnesses: tuple[str, ...]
    kind: ReferenceCoverageKind = "out_of_universe"

    def __post_init__(self) -> None:
        if (
            not self.subject_id
            or not self.source_identity
            or not self.evidence_witnesses
            or self.semantic_relation not in _DIRECT_RELATIONS
            or self.kind != "out_of_universe"
        ):
            raise ValueError("invalid out-of-universe R/G reference gap")


@dataclass(frozen=True)
class RGSemanticReference:
    """Independent semantic/proofability labels for one frozen universe."""

    candidate_universe_digest: str
    labels: tuple[RGSemanticReferenceLabel, ...]
    out_of_universe: tuple[RGSemanticReferenceGap, ...] = ()
    authority: RGSemanticReferenceAuthority = RGSemanticReferenceAuthority(
        "proposed", "unassigned"
    )
    schema_version: str = RG_SEMANTIC_REFERENCE_SCHEMA

    @property
    def proposal_digest(self) -> str:
        payload = json.dumps(
            {
                "candidate_universe_digest": self.candidate_universe_digest,
                "labels": [asdict(item) for item in self.labels],
                "out_of_universe": [asdict(item) for item in self.out_of_universe],
                "proposed_by": self.authority.proposed_by,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def __post_init__(self) -> None:
        if self.schema_version != RG_SEMANTIC_REFERENCE_SCHEMA:
            raise ValueError("unsupported R/G semantic reference schema")
        if not self.candidate_universe_digest:
            raise ValueError("R/G semantic reference requires candidate identity")
        candidate_ids = tuple(item.candidate_id for item in self.labels)
        if candidate_ids != tuple(sorted(candidate_ids)) or len(candidate_ids) != len(
            set(candidate_ids)
        ):
            raise ValueError("R/G semantic labels must be unique and canonical")
        authority = self.authority
        if not authority.proposed_by:
            raise ValueError("R/G semantic reference requires a proposer")
        if authority.status not in {"proposed", "verified"}:
            raise ValueError("R/G semantic reference has invalid authority status")
        if authority.status == "proposed" and (
            authority.verified_by
            or authority.verification_method
            or authority.verification_evidence
            or authority.system_under_test_isolated
            or authority.proposal_digest
        ):
            raise ValueError("proposed R/G semantic reference cannot claim verification")
        if authority.status == "verified" and (
            not authority.verified_by
            or not authority.verification_method
            or not authority.verification_evidence
            or not authority.system_under_test_isolated
            or authority.proposal_digest != self.proposal_digest
            or any(item.review_status != "reviewed" for item in self.labels)
        ):
            raise ValueError(
                "verified R/G reference must bind a fully reviewed exact proposal"
            )


def prepare_rg_candidate_universe(
    brief: ReviewBrief,
    structural_packet: StructuralCorrectnessPacket,
) -> RGSemanticCandidateUniverse:
    """Freeze all profile-eligible R/G changed-anchor facts before association."""

    _require_packet_matches_brief(brief, structural_packet)
    subjects = tuple(
        sorted(
            (
                RGSemanticSubject(
                    subject_id=focus.id,
                    subject_kind=(
                        "guardrail" if focus.kind == "guardrail" else "requirement"
                    ),
                    authored_statement=focus.text,
                    profile=requirement_profile(focus),
                )
                for focus in (*brief.requirements, *brief.guardrails)
            ),
            key=lambda item: item.subject_id,
        )
    )
    evidence = brief.evidence_catalog.by_id()
    changed_anchors = tuple(
        sorted(
            (
                item
                for item in evidence.values()
                if item.changed and item.kind in _ANCHOR_KINDS
            ),
            key=anchor_key,
        )
    )
    node_id_by_review_symbol_id = {
        item.review_symbol_id: item.id
        for item in brief.projection.review_graph.nodes
    }
    anchor_facts: dict[str, RGSemanticAnchorFact] = {}
    candidates: list[RGSemanticCandidate] = []
    focus_by_id = {
        item.id: item for item in (*brief.requirements, *brief.guardrails)
    }
    for subject in subjects:
        focus = focus_by_id[subject.subject_id]
        for anchor in changed_anchors:
            if not eligible_changed_anchor(anchor, subject.profile, focus):
                continue
            anchor_facts.setdefault(
                anchor.id,
                _anchor_fact_from_evidence(anchor, node_id_by_review_symbol_id),
            )
            candidates.append(
                RGSemanticCandidate(
                    candidate_id=f"C:{subject.subject_id}:{anchor.id}",
                    subject_id=subject.subject_id,
                    evidence_id=anchor.id,
                    evidence_role=focus_evidence_role(subject.profile, anchor.profile),
                )
            )
    return RGSemanticCandidateUniverse(
        structural_packet_digest=structural_packet.digest,
        subjects=subjects,
        anchors=tuple(sorted(anchor_facts.values(), key=lambda item: item.evidence_id)),
        candidates=tuple(sorted(candidates, key=lambda item: item.candidate_id)),
    )


def observe_rg_retrieval(
    brief: ReviewBrief,
    structural_packet: StructuralCorrectnessPacket,
    universe: RGSemanticCandidateUniverse,
) -> RGRetrievalObservation:
    """Copy the current R/G association observation onto a frozen universe."""

    _require_packet_matches_brief(brief, structural_packet)
    _require_universe_matches_brief(brief, structural_packet, universe)
    convergence_by_focus = {
        item.focus_statement_id: item for item in brief.candidate_convergence.groups
    }
    relations_by_candidate: dict[tuple[str, str], Any] = {}
    candidate_keys = {
        (item.subject_id, item.evidence_id) for item in universe.candidates
    }
    universe_subject_ids = {item.subject_id for item in universe.subjects}
    for relation in brief.projection_candidates.relations:
        if relation.slot != "changed_anchor" or relation.target_type != "evidence":
            continue
        key = (relation.focus_statement_id, relation.target_id)
        if relation.focus_statement_id in universe_subject_ids and key not in candidate_keys:
            raise ValueError(
                "current R/G association escaped the frozen profile-eligible "
                "candidate universe"
            )
        if key in relations_by_candidate:
            raise ValueError("current R/G association emitted duplicate candidate rows")
        relations_by_candidate[key] = relation
    rows: list[RGRetrievalObservationRow] = []
    for candidate in universe.candidates:
        relation = relations_by_candidate.get(
            (candidate.subject_id, candidate.evidence_id)
        )
        if relation is None:
            rows.append(
                RGRetrievalObservationRow(candidate.candidate_id, "not_retrieved")
            )
            continue
        convergence = convergence_by_focus.get(candidate.subject_id)
        if convergence is None:
            raise ValueError(
                f"R/G retrieval has no convergence group for {candidate.subject_id}"
            )
        if relation.id in convergence.selected_relation_ids:
            state: RetrievalState = "selected"
        elif relation.id in convergence.deferred_relation_ids:
            state = "deferred"
        else:
            raise ValueError("current R/G association is outside convergence")
        rows.append(
            RGRetrievalObservationRow(
                candidate_id=candidate.candidate_id,
                retrieval_state=state,
                relation_id=relation.id,
                association=relation.association,
                reasons=tuple(relation.reasons),
            )
        )
    return RGRetrievalObservation(
        structural_packet_digest=structural_packet.digest,
        candidate_universe_digest=universe.digest,
        rows=tuple(sorted(rows, key=lambda item: item.candidate_id)),
    )


def prepare_rg_semantic_reference_template(
    universe: RGSemanticCandidateUniverse,
    *,
    proposed_by: str = "unassigned",
) -> RGSemanticReference:
    """Create a complete but unreviewed semantic label template."""

    return RGSemanticReference(
        candidate_universe_digest=universe.digest,
        labels=tuple(
            RGSemanticReferenceLabel(
                candidate_id=item.candidate_id,
                semantic_relation="insufficient",
                proofability="insufficient",
                proof_basis="none",
                review_status="pending",
            )
            for item in universe.candidates
        ),
        authority=RGSemanticReferenceAuthority("proposed", proposed_by),
    )


def verify_rg_semantic_reference(
    reference: RGSemanticReference,
    universe: RGSemanticCandidateUniverse,
    *,
    verified_by: str,
    verification_method: str,
    verification_evidence: tuple[str, ...],
    system_under_test_isolated: bool,
) -> RGSemanticReference:
    """Bind an independently reviewed reference to its exact proposal digest."""

    _validate_reference(reference, universe)
    if reference.authority.status != "proposed":
        raise ValueError("only a proposed R/G semantic reference can be verified")
    if any(label.review_status != "reviewed" for label in reference.labels):
        raise ValueError(
            "cannot verify R/G semantic reference with pending candidate labels"
        )
    verified = replace(
        reference,
        authority=RGSemanticReferenceAuthority(
            status="verified",
            proposed_by=reference.authority.proposed_by,
            verified_by=verified_by.strip(),
            verification_method=verification_method.strip(),
            verification_evidence=tuple(
                item.strip() for item in verification_evidence if item.strip()
            ),
            system_under_test_isolated=system_under_test_isolated,
            proposal_digest=reference.proposal_digest,
        ),
    )
    _validate_reference(verified, universe)
    return verified


def compare_rg_retrieval(
    universe: RGSemanticCandidateUniverse,
    retrieval: RGRetrievalObservation,
    reference: RGSemanticReference,
) -> dict[str, Any]:
    """Compare observed R/G retrieval with a frozen semantic/proof reference.

    The comparison intentionally has two dimensions.  ``retrieval`` measures
    whether the current association surfaced a semantic-direct candidate at
    all.  ``direct_attempt`` measures only current provided/exact associations
    against the smaller direct-capable target.  Neither dimension predicts a
    redesigned selector or changes production membership.
    """

    _validate_retrieval(retrieval, universe)
    _validate_reference(reference, universe)
    if reference.authority.status != "verified":
        raise ValueError(
            "only a verified R/G semantic reference can produce semantic metrics"
        )
    subjects = {item.subject_id: item for item in universe.subjects}
    anchors_by_id = {item.evidence_id: item for item in universe.anchors}
    candidates_by_subject: dict[str, list[RGSemanticCandidate]] = defaultdict(list)
    for candidate in universe.candidates:
        candidates_by_subject[candidate.subject_id].append(candidate)
    labels = {item.candidate_id: item for item in reference.labels}
    retrieval_by_candidate = {item.candidate_id: item for item in retrieval.rows}
    gaps_by_subject: dict[str, list[RGSemanticReferenceGap]] = defaultdict(list)
    for gap in reference.out_of_universe:
        gaps_by_subject[gap.subject_id].append(gap)

    overall = {
        "retrieval_against_semantic_direct": _empty_delta(),
        "direct_attempt_against_direct_capable": _empty_delta(),
    }
    coverage = Counter(
        {
            "candidate_count": 0,
            "node_resolved_candidates": 0,
            "node_unresolved_candidates": 0,
            "not_node_backed_candidates": 0,
            "semantic_direct_node_unresolved": 0,
            "out_of_universe_references": len(reference.out_of_universe),
            "reference_insufficient_candidates": 0,
        }
    )
    by_subject_kind: dict[str, dict[str, dict[str, int]]] = {}
    per_focus: list[dict[str, Any]] = []
    for subject_id in sorted(subjects):
        subject = subjects[subject_id]
        candidates = candidates_by_subject[subject_id]
        resolved = {
            candidate.candidate_id
            for candidate in candidates
            if labels[candidate.candidate_id].semantic_relation != "insufficient"
        }
        expected_semantic_direct = {
            candidate.candidate_id
            for candidate in candidates
            if labels[candidate.candidate_id].semantic_relation in _DIRECT_RELATIONS
        }
        expected_direct_capable = {
            candidate.candidate_id
            for candidate in candidates
            if labels[candidate.candidate_id].semantic_relation in _DIRECT_RELATIONS
            and labels[candidate.candidate_id].proofability == "direct_capable"
        }
        retrieved = {
            candidate.candidate_id
            for candidate in candidates
            if retrieval_by_candidate[candidate.candidate_id].retrieval_state
            != "not_retrieved"
        }
        direct_attempt = {
            candidate.candidate_id
            for candidate in candidates
            if retrieval_by_candidate[candidate.candidate_id].association
            in _DIRECT_ASSOCIATIONS
        }
        focus_deltas = {
            "retrieval_against_semantic_direct": _delta(
                retrieved & resolved, expected_semantic_direct
            ),
            "direct_attempt_against_direct_capable": _delta(
                direct_attempt & resolved, expected_direct_capable
            ),
        }
        for name, delta in focus_deltas.items():
            for field in ("false_inclusions", "false_exclusions"):
                overall[name][field] += delta[field]
        bucket = by_subject_kind.setdefault(
            subject.subject_kind,
            {
                "retrieval_against_semantic_direct": _empty_delta(),
                "direct_attempt_against_direct_capable": _empty_delta(),
            },
        )
        for name, delta in focus_deltas.items():
            for field in ("false_inclusions", "false_exclusions"):
                bucket[name][field] += delta[field]
        distribution: Counter[str] = Counter()
        for candidate in candidates:
            anchor = anchors_by_id[candidate.evidence_id]
            label = labels[candidate.candidate_id]
            row = retrieval_by_candidate[candidate.candidate_id]
            association = row.association or "not_retrieved"
            distribution[f"{label.semantic_relation}:{association}"] += 1
            coverage["candidate_count"] += 1
            coverage[f"{anchor.node_state}_candidates"] += 1
            if label.semantic_relation in _DIRECT_RELATIONS and anchor.node_state != "node_resolved":
                coverage["semantic_direct_node_unresolved"] += 1
            if label.semantic_relation == "insufficient":
                coverage["reference_insufficient_candidates"] += 1
        per_focus.append(
            {
                "subject_id": subject_id,
                "subject_kind": subject.subject_kind,
                "candidate_count": len(candidates),
                "reference_resolved_candidate_count": len(resolved),
                "reference_insufficient_candidate_count": len(candidates) - len(resolved),
                "semantic_direct_candidate_ids": sorted(expected_semantic_direct),
                "direct_capable_candidate_ids": sorted(expected_direct_capable),
                "retrieved_candidate_ids": sorted(retrieved),
                "direct_attempt_candidate_ids": sorted(direct_attempt),
                "dimensions": focus_deltas,
                "semantic_relation_by_association": dict(sorted(distribution.items())),
                "out_of_universe_references": [
                    asdict(item) for item in gaps_by_subject[subject_id]
                ],
            }
        )
    return {
        "schema_version": RG_SEMANTIC_COMPARISON_SCHEMA,
        "structural_packet_digest": universe.structural_packet_digest,
        "candidate_universe_digest": universe.digest,
        "reference_authority": asdict(reference.authority),
        "causal_replay": False,
        "production_changed": False,
        "overall": overall,
        "by_subject_kind": by_subject_kind,
        "coverage": dict(sorted(coverage.items())),
        "per_focus": per_focus,
        "limits": {
            "candidate_universe": (
                "profile-eligible changed-anchor facts only; it is not a "
                "repository-wide semantic universe"
            ),
            "context": (
                "structural paths, ownership, relation endpoints, and retained "
                "topology are not direct semantic candidates"
            ),
            "guardrail_closure": (
                "closure/current-head verification remains a separate proof "
                "surface and is not part of this candidate universe"
            ),
            "authority": (
                "lexical retrieval, canonical resolution, and model suggestions "
                "do not alter formal direct admission; reference proofability is "
                "evaluation evidence only and does not create a production direct "
                "mapping"
            ),
            "unresolved_reference": (
                "reviewed insufficient reference labels are excluded from FI/FE "
                "rather than treated as semantic negatives"
            ),
        },
    }


def write_rg_candidate_artifact(
    value: RGSemanticCandidateUniverse
    | RGRetrievalObservation
    | RGSemanticReference
    | Mapping[str, Any],
    output: str | Path,
) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(value) if not isinstance(value, Mapping) else value
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_rg_candidate_universe(path: str | Path) -> RGSemanticCandidateUniverse:
    raw = _load_mapping(path, RG_CANDIDATE_UNIVERSE_SCHEMA)
    subjects = tuple(
        RGSemanticSubject(
            subject_id=_string(item, "subject_id"),
            subject_kind=_string(item, "subject_kind"),  # type: ignore[arg-type]
            authored_statement=_string(item, "authored_statement"),
            profile=_string(item, "profile"),  # type: ignore[arg-type]
        )
        for item in _objects(raw, "subjects")
    )
    anchors = tuple(
        _anchor_fact_from_mapping(item) for item in _objects(raw, "anchors")
    )
    candidates = tuple(
        _candidate_from_mapping(item) for item in _objects(raw, "candidates")
    )
    return RGSemanticCandidateUniverse(
        structural_packet_digest=_string(raw, "structural_packet_digest"),
        subjects=tuple(sorted(subjects, key=lambda item: item.subject_id)),
        anchors=tuple(sorted(anchors, key=lambda item: item.evidence_id)),
        candidates=tuple(sorted(candidates, key=lambda item: item.candidate_id)),
        schema_version=_string(raw, "schema_version"),
    )


def load_rg_retrieval_observation(path: str | Path) -> RGRetrievalObservation:
    raw = _load_mapping(path, RG_RETRIEVAL_OBSERVATION_SCHEMA)
    rows = tuple(
        RGRetrievalObservationRow(
            candidate_id=_string(item, "candidate_id"),
            retrieval_state=_string(item, "retrieval_state"),  # type: ignore[arg-type]
            relation_id=_optional_string(item.get("relation_id")),
            association=_optional_string(item.get("association")),  # type: ignore[arg-type]
            reasons=tuple(_reason_from_mapping(reason) for reason in _objects(item, "reasons")),
        )
        for item in _objects(raw, "rows")
    )
    return RGRetrievalObservation(
        structural_packet_digest=_string(raw, "structural_packet_digest"),
        candidate_universe_digest=_string(raw, "candidate_universe_digest"),
        rows=tuple(sorted(rows, key=lambda item: item.candidate_id)),
        schema_version=_string(raw, "schema_version"),
    )


def load_rg_semantic_reference(path: str | Path) -> RGSemanticReference:
    raw = _load_mapping(path, RG_SEMANTIC_REFERENCE_SCHEMA)
    authority_raw = _mapping(raw.get("authority"), "authority")
    authority = RGSemanticReferenceAuthority(
        status=_string(authority_raw, "status"),  # type: ignore[arg-type]
        proposed_by=_string(authority_raw, "proposed_by"),
        verified_by=_optional_string(authority_raw.get("verified_by")) or "",
        verification_method=_optional_string(authority_raw.get("verification_method")) or "",
        verification_evidence=_strings(authority_raw.get("verification_evidence", [])),
        system_under_test_isolated=_boolean(
            authority_raw.get("system_under_test_isolated", False),
            "system_under_test_isolated",
        ),
        proposal_digest=_optional_string(authority_raw.get("proposal_digest")) or "",
    )
    labels = tuple(
        RGSemanticReferenceLabel(
            candidate_id=_string(item, "candidate_id"),
            semantic_relation=_string(item, "semantic_relation"),  # type: ignore[arg-type]
            proofability=_string(item, "proofability"),  # type: ignore[arg-type]
            proof_basis=_string(item, "proof_basis"),  # type: ignore[arg-type]
            evidence_witnesses=_strings(item.get("evidence_witnesses", [])),
            note=_optional_string(item.get("note")) or "",
            review_status=_string(item, "review_status"),  # type: ignore[arg-type]
        )
        for item in _objects(raw, "labels")
    )
    gaps = tuple(
        RGSemanticReferenceGap(
            subject_id=_string(item, "subject_id"),
            semantic_relation=_string(item, "semantic_relation"),  # type: ignore[arg-type]
            source_identity=_string(item, "source_identity"),
            evidence_witnesses=_strings(item.get("evidence_witnesses", [])),
            kind=_optional_string(item.get("kind")) or "out_of_universe",  # type: ignore[arg-type]
        )
        for item in _objects(raw, "out_of_universe")
    )
    return RGSemanticReference(
        candidate_universe_digest=_string(raw, "candidate_universe_digest"),
        labels=tuple(sorted(labels, key=lambda item: item.candidate_id)),
        out_of_universe=gaps,
        authority=authority,
        schema_version=_string(raw, "schema_version"),
    )


def _anchor_fact_from_evidence(
    item: EvidenceItem,
    node_id_by_review_symbol_id: Mapping[str, str],
) -> RGSemanticAnchorFact:
    review_id = review_symbol_id(item)
    node_id = node_id_by_review_symbol_id.get(review_id or "")
    node_state: CandidateNodeState = (
        "node_resolved"
        if node_id is not None
        else "node_unresolved"
        if review_id is not None
        else "not_node_backed"
    )
    source = item.sources[0] if item.sources else None
    path = str(item.metadata.get("path") or (source.path if source else "") or "")
    return RGSemanticAnchorFact(
        evidence_id=item.id,
        evidence_kind=item.kind,
        classification=item.classification,
        profile=item.profile,
        revision_side=item.revision_side,
        operation=item.operation,
        summary=item.summary,
        path=path or None,
        change_relation_ids=tuple(item.change_relation_ids),
        sources=tuple(_source_ref(item) for item in item.sources),
        canonical_review_symbol_id=review_id,
        canonical_node_id=node_id,
        node_state=node_state,
    )


def _source_ref(source: SourceRef) -> CandidateSourceRef:
    return CandidateSourceRef(
        label=source.label,
        url=source.url,
        path=source.path,
        line_start=source.line_start,
        line_end=source.line_end,
    )


def _require_packet_matches_brief(
    brief: ReviewBrief, structural_packet: StructuralCorrectnessPacket
) -> None:
    if prepare_structural_correctness_packet(brief) != structural_packet:
        raise ValueError("structural correctness packet does not match current review")


def _require_universe_matches_brief(
    brief: ReviewBrief,
    structural_packet: StructuralCorrectnessPacket,
    universe: RGSemanticCandidateUniverse,
) -> None:
    if universe.structural_packet_digest != structural_packet.digest:
        raise ValueError("R/G candidate universe does not match structural packet")
    current = prepare_rg_candidate_universe(brief, structural_packet)
    if current != universe:
        raise ValueError("R/G candidate universe does not match current review")


def _validate_retrieval(
    retrieval: RGRetrievalObservation,
    universe: RGSemanticCandidateUniverse,
) -> None:
    if retrieval.structural_packet_digest != universe.structural_packet_digest:
        raise ValueError("R/G retrieval does not match structural packet")
    if retrieval.candidate_universe_digest != universe.digest:
        raise ValueError("R/G retrieval does not match candidate universe")
    if {item.candidate_id for item in retrieval.rows} != {
        item.candidate_id for item in universe.candidates
    }:
        raise ValueError("R/G retrieval must dispose every candidate exactly once")


def _validate_reference(
    reference: RGSemanticReference,
    universe: RGSemanticCandidateUniverse,
) -> None:
    if reference.candidate_universe_digest != universe.digest:
        raise ValueError("R/G semantic reference does not match candidate universe")
    candidate_ids = {item.candidate_id for item in universe.candidates}
    if {item.candidate_id for item in reference.labels} != candidate_ids:
        raise ValueError("R/G semantic reference must dispose every candidate")
    subject_ids = {item.subject_id for item in universe.subjects}
    if any(item.subject_id not in subject_ids for item in reference.out_of_universe):
        raise ValueError("R/G reference gap names an unknown subject")


def _empty_delta() -> dict[str, int]:
    return {"false_inclusions": 0, "false_exclusions": 0}


def _delta(actual: set[str], expected: set[str]) -> dict[str, Any]:
    false_inclusions = sorted(actual - expected)
    false_exclusions = sorted(expected - actual)
    return {
        "false_inclusions": len(false_inclusions),
        "false_exclusions": len(false_exclusions),
        "false_inclusion_candidate_ids": false_inclusions,
        "false_exclusion_candidate_ids": false_exclusions,
    }


def _load_mapping(path: str | Path, schema: str) -> Mapping[str, Any]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping) or raw.get("schema_version") != schema:
        raise ValueError(f"unsupported {schema} artifact")
    return raw


def _candidate_from_mapping(raw: Mapping[str, Any]) -> RGSemanticCandidate:
    return RGSemanticCandidate(
        candidate_id=_string(raw, "candidate_id"),
        subject_id=_string(raw, "subject_id"),
        evidence_id=_string(raw, "evidence_id"),
        evidence_role=_string(raw, "evidence_role"),
    )


def _anchor_fact_from_mapping(raw: Mapping[str, Any]) -> RGSemanticAnchorFact:
    return RGSemanticAnchorFact(
        evidence_id=_string(raw, "evidence_id"),
        evidence_kind=_string(raw, "evidence_kind"),
        classification=_string(raw, "classification"),
        profile=_string(raw, "profile"),
        revision_side=_string(raw, "revision_side"),
        operation=_string(raw, "operation"),
        summary=_string(raw, "summary"),
        path=_optional_string(raw.get("path")),
        change_relation_ids=_strings(raw.get("change_relation_ids", [])),
        sources=tuple(
            CandidateSourceRef(
                label=_string(source, "label"),
                url=_optional_string(source.get("url")),
                path=_optional_string(source.get("path")),
                line_start=_optional_int(source.get("line_start")),
                line_end=_optional_int(source.get("line_end")),
            )
            for source in _objects(raw, "sources")
        ),
        canonical_review_symbol_id=_optional_string(raw.get("canonical_review_symbol_id")),
        canonical_node_id=_optional_string(raw.get("canonical_node_id")),
        node_state=_string(raw, "node_state"),  # type: ignore[arg-type]
    )


def _reason_from_mapping(raw: Mapping[str, Any]) -> AssociationReason:
    return AssociationReason(
        kind=_string(raw, "kind"),  # type: ignore[arg-type]
        detail=_string(raw, "detail"),
        matched_terms=_strings(raw.get("matched_terms", [])),
    )


def _objects(raw: Mapping[str, Any], key: str) -> tuple[Mapping[str, Any], ...]:
    value = raw.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise ValueError(f"{key} must be an array of objects")
    return tuple(value)


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _string(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("optional value must be a string or null")
    return value or None


def _boolean(value: object, key: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("value must be an array of strings")
    return tuple(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("optional value must be an integer or null")
    return value
