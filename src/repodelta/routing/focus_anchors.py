from __future__ import annotations

from dataclasses import dataclass

from repodelta.model.contracts import (
    AssociationReason,
    EvidenceItem,
    ProjectionRelation,
    Requirement,
    RequirementProfile,
    ReviewStatement,
)
from repodelta.routing.association import (
    distinctive_signature_terms,
    evidence_reasons,
)
from repodelta.routing.relations import candidate_key, projection_relation
from repodelta.routing.semantics import (
    eligible_changed_anchor,
    evidence_signature,
    focus_evidence_role,
)


@dataclass(frozen=True)
class FocusAnchorAssociationSet:
    """Complete, unselected changed-anchor truth for one review focus."""

    eligible_anchor_ids: tuple[str, ...]
    relations: tuple[ProjectionRelation, ...]


def associate_focus_anchors(
    focus: Requirement,
    associated_claim_ids: set[str],
    claims: tuple[ReviewStatement, ...],
    changed_anchors: tuple[EvidenceItem, ...],
    *,
    focus_distinctive_terms: frozenset[str],
    claim_distinctive_terms: dict[str, frozenset[str]],
    profile: RequirementProfile,
) -> FocusAnchorAssociationSet:
    """Apply eligibility and association once, without selection or truncation."""

    anchors = tuple(
        item
        for item in changed_anchors
        if eligible_changed_anchor(item, profile, focus)
    )
    claims_by_id = {item.id: item for item in claims}
    direct_anchor_terms = distinctive_signature_terms(
        tuple((anchor.id, evidence_signature(anchor, focus)) for anchor in anchors)
    )
    anchor_terms_by_claim = {
        claim_id: distinctive_signature_terms(
            tuple(
                (anchor.id, evidence_signature(anchor, claim))
                for anchor in anchors
            )
        )
        for claim_id in associated_claim_ids
        for claim in (claims_by_id.get(claim_id),)
        if claim is not None
    }
    direct_reasons_by_anchor = {
        anchor.id: evidence_reasons(
            focus,
            evidence_signature(anchor, focus),
            distinctive_terms=focus_distinctive_terms,
        )
        for anchor in anchors
    }
    discriminative_direct_reasons_by_anchor = {
        anchor.id: evidence_reasons(
            focus,
            evidence_signature(anchor, focus),
            distinctive_terms=(
                focus_distinctive_terms
                & direct_anchor_terms.get(anchor.id, frozenset())
            ),
        )
        for anchor in anchors
    }
    discriminative_phrase_profiles = {
        anchor.profile
        for anchor in anchors
        if (
            reasons := discriminative_direct_reasons_by_anchor[anchor.id]
        )
        and reasons[0].kind == "distinctive_phrase"
    }

    relations = []
    for ordinal, anchor in enumerate(anchors):
        evidence_role = focus_evidence_role(profile, anchor.profile)
        if focus.id in anchor.associated_statement_ids:
            relations.append(
                projection_relation(
                    focus.id,
                    "changed_anchor",
                    "evidence",
                    anchor.id,
                    "provided_association",
                    (
                        AssociationReason(
                            kind="provided_association",
                            detail=(
                                "The provider explicitly associates this fact "
                                "with the focus."
                            ),
                        ),
                    ),
                    evidence_role=evidence_role,
                    source_ordinal=ordinal,
                )
            )
            continue

        direct = _converged_direct_reasons(
            direct_reasons_by_anchor[anchor.id],
            discriminative_direct_reasons_by_anchor[anchor.id],
            has_discriminative_phrase_cohort=(
                anchor.profile in discriminative_phrase_profiles
            ),
        )
        bridges, bridge_terms = _claim_bridges(
            anchor,
            associated_claim_ids,
            claims_by_id,
            claim_distinctive_terms,
            anchor_terms_by_claim,
        )
        if focus.kind == "guardrail" and direct:
            direct = tuple(
                reason
                for reason in direct
                if reason.kind == "exact_identifier"
            )

        if direct:
            reasons = direct
            if bridges:
                reasons = (
                    *reasons,
                    _claim_bridge_reason(bridge_terms),
                )
            relations.append(
                projection_relation(
                    focus.id,
                    "changed_anchor",
                    "evidence",
                    anchor.id,
                    direct[0].kind,
                    reasons,
                    evidence_role=evidence_role,
                    bridge_ids=bridges,
                    source_ordinal=ordinal,
                )
            )
        elif bridges:
            relations.append(
                projection_relation(
                    focus.id,
                    "changed_anchor",
                    "evidence",
                    anchor.id,
                    "claim_bridge",
                    (_claim_bridge_reason(bridge_terms),),
                    evidence_role=evidence_role,
                    bridge_ids=bridges,
                    source_ordinal=ordinal,
                )
            )

    return FocusAnchorAssociationSet(
        eligible_anchor_ids=tuple(item.id for item in anchors),
        relations=tuple(sorted(relations, key=candidate_key)),
    )


def _claim_bridges(
    anchor: EvidenceItem,
    associated_claim_ids: set[str],
    claims_by_id: dict[str, ReviewStatement],
    claim_distinctive_terms: dict[str, frozenset[str]],
    anchor_terms_by_claim: dict[str, dict[str, frozenset[str]]],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    bridges = []
    matched_terms: set[str] = set()
    for claim_id in sorted(associated_claim_ids):
        claim = claims_by_id.get(claim_id)
        if claim is None:
            continue
        bridge_terms = (
            claim_distinctive_terms.get(claim_id, frozenset())
            & anchor_terms_by_claim.get(claim_id, {}).get(
                anchor.id,
                frozenset(),
            )
        )
        reasons = evidence_reasons(
            claim,
            evidence_signature(anchor, claim),
            distinctive_terms=bridge_terms,
        )
        if not reasons:
            continue
        bridges.append(claim_id)
        matched_terms.update(reasons[0].matched_terms)
    return tuple(bridges), tuple(sorted(matched_terms))


def _claim_bridge_reason(matched_terms: tuple[str, ...]) -> AssociationReason:
    return AssociationReason(
        kind="claim_bridge",
        detail=(
            "An associated PR claim has a deterministic identifier or "
            "discriminative phrase relation to this changed anchor."
        ),
        matched_terms=matched_terms,
    )


def _converged_direct_reasons(
    direct: tuple[AssociationReason, ...],
    discriminative: tuple[AssociationReason, ...],
    *,
    has_discriminative_phrase_cohort: bool,
) -> tuple[AssociationReason, ...]:
    if not direct:
        return ()
    if direct[0].kind == "exact_identifier":
        return direct
    if discriminative:
        return discriminative
    if has_discriminative_phrase_cohort:
        return ()
    return direct
