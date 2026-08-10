from __future__ import annotations

from repodelta.model.contracts import AssociationKind, ProjectionRelation


_ASSOCIATION_ORDER: dict[AssociationKind, int] = {
    "provided_association": 0,
    "explicit_reference": 1,
    "exact_identifier": 2,
    "distinctive_phrase": 3,
    "claim_bridge": 4,
    "structural_bridge": 5,
    "current_head": 6,
}
_EVIDENCE_ROLE_ORDER = {
    "primary": 0,
    "test_support": 1,
    "document_support": 2,
}


def relation_key(item: ProjectionRelation) -> tuple[object, ...]:
    return (
        item.slot,
        _EVIDENCE_ROLE_ORDER[item.evidence_role],
        semantic_tier(item),
        item.source_ordinal,
        item.target_id,
    )


def semantic_tier(item: ProjectionRelation) -> int:
    return _ASSOCIATION_ORDER[item.association]
