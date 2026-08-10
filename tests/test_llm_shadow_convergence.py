from __future__ import annotations

from repodelta.llm.convergence import converge_shadow_candidate_identities
from repodelta.model.contracts import (
    AssociationReason,
    EvidenceCatalog,
    EvidenceItem,
    StructuralChangeIdentity,
    TransformationClaim,
    TransformationEvidenceBinding,
)


def _changed(
    evidence_id: str,
    relation_id: str,
) -> EvidenceItem:
    return EvidenceItem(
        id=evidence_id,
        summary=f"Modified function: {evidence_id}",
        kind="structural_change",
        classification="code",
        profile="production",
        authority="structural_provider",
        revision_side="review",
        operation="modified",
        role="changed_anchor",
        changed=True,
        change_relation_ids=(relation_id,),
        structural_change=StructuralChangeIdentity(
            review_symbol_id=f"review:{evidence_id}"
        ),
    )


def _binding(evidence_id: str) -> TransformationEvidenceBinding:
    return TransformationEvidenceBinding(
        id=f"TAB:T1:{evidence_id}",
        claim_id="T1",
        evidence_id=evidence_id,
        evidence_role="change",
        association="exact_identifier",
        reasons=(AssociationReason(kind="exact_identifier", detail="exact"),),
    )


def test_convergence_expands_only_same_hunk_canonical_anchors() -> None:
    direct = _changed("E:direct", "relation:shared")
    same_hunk = _changed("E:same", "relation:shared")
    unrelated = _changed("E:other", "relation:other")
    catalog = EvidenceCatalog(items=(direct, same_hunk, unrelated))

    result = converge_shadow_candidate_identities(
        TransformationClaim(id="T1", kind="change", text="Change direct."),
        catalog,
        {direct.id, same_hunk.id, unrelated.id},
        (_binding(direct.id),),
        (),
        max_candidates=10,
    )

    assert tuple(item.evidence_id for item in result.identities) == (
        direct.id,
        same_hunk.id,
    )
    assert tuple(item.tier for item in result.identities) == (
        "identifier",
        "same_hunk",
    )


def test_convergence_reports_the_deferred_tier_without_competing_direct_anchors() -> None:
    first = _changed("E:first", "relation:first")
    second = _changed("E:second", "relation:second")
    catalog = EvidenceCatalog(items=(first, second))

    direct = converge_shadow_candidate_identities(
        TransformationClaim(id="T1", kind="change", text="Change both."),
        catalog,
        {first.id, second.id},
        (_binding(first.id), _binding(second.id)),
        (),
        max_candidates=2,
    )
    truncated = converge_shadow_candidate_identities(
        TransformationClaim(id="T1", kind="change", text="Change both."),
        catalog,
        {first.id, second.id},
        (_binding(first.id), _binding(second.id)),
        (),
        max_candidates=1,
    )

    assert {item.evidence_id for item in direct.identities} == {
        first.id,
        second.id,
    }
    assert truncated.deferred_count == 1
    assert truncated.deferred_tier == "identifier"
