from __future__ import annotations

import hashlib
from typing import Literal

from prismcode.model.contracts import (
    AssociationKind,
    AssociationReason,
    FocusEvidenceRole,
    ProjectionRelation,
    ProjectionSlot,
)


def projection_relation(
    focus_id: str,
    slot: ProjectionSlot,
    target_type: Literal["statement", "evidence"],
    target_id: str,
    association: AssociationKind,
    reasons: tuple[AssociationReason, ...],
    *,
    evidence_role: FocusEvidenceRole = "primary",
    bridge_ids: tuple[str, ...] = (),
    source_ordinal: int = 0,
) -> ProjectionRelation:
    identity = (
        f"{focus_id}\0{slot}\0{target_type}\0{target_id}\0"
        f"{association}\0{evidence_role}"
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return ProjectionRelation(
        id=f"PR:{digest}",
        focus_statement_id=focus_id,
        slot=slot,
        target_type=target_type,
        target_id=target_id,
        association=association,
        reasons=reasons,
        evidence_role=evidence_role,
        bridge_ids=bridge_ids,
        source_ordinal=source_ordinal,
    )


def candidate_key(item: ProjectionRelation) -> tuple[object, ...]:
    return (
        item.slot,
        item.source_ordinal,
        item.target_id,
        item.association,
    )
