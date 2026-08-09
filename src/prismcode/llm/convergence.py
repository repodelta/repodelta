from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from prismcode.model.contracts import (
    EvidenceCatalog,
    EvidenceItem,
    TransformationClaim,
    TransformationEvidenceBinding,
)
from prismcode.routing.transformation import eligible_transformation_evidence


ShadowCandidateTier = Literal[
    "baseline",
    "provided",
    "identifier",
    "phrase",
    "bridge",
    "same_hunk",
    "fallback",
]

_ASSOCIATION_TIER: dict[str, ShadowCandidateTier] = {
    "provided_association": "provided",
    "explicit_reference": "provided",
    "current_head": "provided",
    "exact_identifier": "identifier",
    "distinctive_phrase": "phrase",
    "claim_bridge": "bridge",
    "structural_bridge": "bridge",
}
_TIER_ORDER = {
    "baseline": 0,
    "provided": 1,
    "identifier": 2,
    "phrase": 3,
    "bridge": 4,
    "same_hunk": 5,
    "fallback": 6,
}
_CANONICAL_ANCHOR_KINDS = frozenset({"structural_change", "change_relation"})


@dataclass(frozen=True)
class ShadowCandidateIdentity:
    evidence_id: str
    tier: ShadowCandidateTier
    association: str


@dataclass(frozen=True)
class ShadowCandidateConvergence:
    identities: tuple[ShadowCandidateIdentity, ...]
    eligible_count: int
    deferred_count: int
    deferred_tier: ShadowCandidateTier | None = None


def converge_shadow_candidate_identities(
    claim: TransformationClaim,
    evidence_catalog: EvidenceCatalog,
    observed_ids: set[str],
    bindings: tuple[TransformationEvidenceBinding, ...],
    baseline_ids: tuple[str, ...],
    *,
    max_candidates: int,
) -> ShadowCandidateConvergence:
    """Select one claim-scoped canonical identity set before packet projection."""

    evidence = evidence_catalog.by_id()
    ordinal = {item.id: index for index, item in enumerate(evidence_catalog.items)}
    candidates: dict[str, ShadowCandidateIdentity] = {}

    def retain(evidence_id: str, tier: ShadowCandidateTier, association: str) -> None:
        if evidence_id not in evidence:
            return
        existing = candidates.get(evidence_id)
        if existing is None or _TIER_ORDER[tier] < _TIER_ORDER[existing.tier]:
            candidates[evidence_id] = ShadowCandidateIdentity(
                evidence_id=evidence_id,
                tier=tier,
                association=association,
            )

    for evidence_id in baseline_ids:
        retain(evidence_id, "baseline", "deterministic_baseline")
    for binding in sorted(
        bindings,
        key=lambda item: (
            _TIER_ORDER[_ASSOCIATION_TIER[item.association]],
            ordinal.get(item.evidence_id, len(ordinal)),
            item.evidence_id,
        ),
    ):
        retain(
            binding.evidence_id,
            _ASSOCIATION_TIER[binding.association],
            binding.association,
        )

    direct_ids = tuple(candidates)
    direct_relation_ids = {
        relation_id
        for evidence_id in direct_ids
        for relation_id in evidence[evidence_id].change_relation_ids
    }
    if direct_relation_ids:
        for item in evidence_catalog.items:
            if (
                item.id in observed_ids
                and item.kind in _CANONICAL_ANCHOR_KINDS
                and _eligible_shadow_candidate(claim, item)
                and direct_relation_ids.intersection(item.change_relation_ids)
            ):
                retain(item.id, "same_hunk", "shared_change_relation")
    elif not direct_ids:
        eligible_anchors = tuple(
            item
            for item in evidence_catalog.items
            if item.id in observed_ids
            and item.kind in _CANONICAL_ANCHOR_KINDS
            and _eligible_shadow_candidate(claim, item)
        )
        preferred_kind = (
            "structural_change"
            if any(item.kind == "structural_change" for item in eligible_anchors)
            else "change_relation"
        )
        for item in eligible_anchors:
            if item.kind == preferred_kind:
                retain(item.id, "fallback", "typed_changed_anchor_fallback")

    ordered = tuple(
        sorted(
            candidates.values(),
            key=lambda item: (
                _TIER_ORDER[item.tier],
                ordinal.get(item.evidence_id, len(ordinal)),
                item.evidence_id,
            ),
        )
    )
    selected = ordered[:max_candidates]
    deferred = ordered[max_candidates:]
    return ShadowCandidateConvergence(
        identities=selected,
        eligible_count=len(ordered),
        deferred_count=len(deferred),
        deferred_tier=deferred[0].tier if deferred else None,
    )


def _eligible_shadow_candidate(
    claim: TransformationClaim,
    item: EvidenceItem,
) -> bool:
    """Extend only shadow admission for generic state measurement."""

    if claim.kind == "before_state":
        return bool(item.base_signature.identifiers or item.base_signature.tokens)
    if claim.kind == "after_state":
        return bool(item.head_signature.identifiers or item.head_signature.tokens)
    return eligible_transformation_evidence(claim, item)
