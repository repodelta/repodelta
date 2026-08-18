from __future__ import annotations

import pytest

from repodelta.model.contracts import (
    StructuralFocusMembership,
    StructuralFocusOverlay,
    StructuralFocusProvenance,
)
from repodelta.projection.build import _association_membership_class


def _provenance(admission_class: str, source_id: str = "source"):
    return StructuralFocusProvenance(
        producer="test_producer",
        admission_class=admission_class,
        source_ids=(source_id,),
    )


@pytest.mark.parametrize(
    ("membership_class", "role", "is_direct"),
    (
        ("asserted", "changed_anchor", True),
        ("matched", "changed_anchor", True),
        ("suggested", "changed_anchor", False),
        ("context", "runtime_context", False),
        ("unresolved", "unresolved", False),
    ),
)
def test_membership_classes_own_direct_mapping_boundary(
    membership_class,
    role,
    is_direct,
) -> None:
    membership = StructuralFocusMembership(
        member_kind="node",
        member_id=f"N:{membership_class}",
        membership_class=membership_class,
        structural_role=role,
        provenance=(_provenance(membership_class),),
    )

    assert membership.is_direct_mapping is is_direct


@pytest.mark.parametrize(
    "values",
    (
        {"producer": "", "source_ids": ("source",)},
        {"producer": "producer", "source_ids": ()},
        {"producer": "producer", "source_ids": ("source", "source")},
    ),
)
def test_focus_provenance_fails_closed_without_canonical_identity(values) -> None:
    with pytest.raises(ValueError, match="requires producer sources"):
        StructuralFocusProvenance(
            admission_class="context",
            **values,
        )


def test_context_provenance_cannot_promote_a_reachable_node() -> None:
    with pytest.raises(ValueError, match="cannot become a changed anchor"):
        StructuralFocusMembership(
            member_kind="node",
            member_id="N:path",
            membership_class="context",
            structural_role="changed_anchor",
            provenance=(_provenance("context", "E:path"),),
        )


def test_non_node_membership_cannot_become_a_semantic_mapping() -> None:
    with pytest.raises(ValueError, match="requires a changed node anchor"):
        StructuralFocusMembership(
            member_kind="edge",
            member_id="E:calls",
            membership_class="asserted",
            structural_role="relation_endpoint",
            provenance=(_provenance("asserted", "E:calls"),),
        )


def test_membership_preserves_strongest_producer_class() -> None:
    membership = StructuralFocusMembership(
        member_kind="node",
        member_id="N:anchor",
        membership_class="matched",
        structural_role="changed_anchor",
        provenance=(
            _provenance("context", "E:path"),
            _provenance("matched", "P:exact"),
        ),
    )
    assert membership.membership_class == "matched"

    with pytest.raises(ValueError, match="strongest provenance"):
        StructuralFocusMembership(
            member_kind="node",
            member_id="N:anchor",
            membership_class="context",
            structural_role="connector",
            provenance=membership.provenance,
        )


def test_overlay_rejects_two_authorities_for_one_member() -> None:
    membership = StructuralFocusMembership(
        member_kind="node",
        member_id="N:anchor",
        membership_class="matched",
        structural_role="changed_anchor",
        provenance=(_provenance("matched"),),
    )
    with pytest.raises(ValueError, match="duplicate memberships"):
        StructuralFocusOverlay(memberships=(membership, membership))


def test_current_head_cannot_become_changed_anchor_membership() -> None:
    with pytest.raises(ValueError, match="verification applicability"):
        _association_membership_class("current_head")
