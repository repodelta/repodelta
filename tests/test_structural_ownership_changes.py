from __future__ import annotations

from prismcode.changes.hunks import DiffHunkCollection
from prismcode.facts.catalog import build_evidence_catalog
from prismcode.model.contracts import ReviewSourcePacket, SourceRef
from prismcode.providers.structural import (
    GraphSymbol,
    StructuralGraphCollection,
    StructuralGraphIndexStatus,
    StructuralGraphResult,
    StructuralOwnershipCoverage,
    StructuralOwnershipRelation,
)


def _symbol(identifier: str, *, kind: str = "class") -> GraphSymbol:
    return GraphSymbol(
        id=identifier,
        kind=kind,
        name=identifier,
        qualified_name=f"service.{identifier}",
        file_path="src/service.py",
        language="python",
        start_line=1,
        end_line=4,
        sources=(
            SourceRef(
                label=identifier,
                path="src/service.py",
                line_start=1,
                line_end=4,
            ),
        ),
    )


def _ownership(parent: str = "P", child: str = "C") -> StructuralOwnershipRelation:
    return StructuralOwnershipRelation(
        parent=_symbol(parent),
        child=_symbol(child, kind="method"),
    )


def _result(
    revision: str,
    *relations: StructuralOwnershipRelation,
    observed: tuple[str, ...] = ("C",),
    coverage_state: str = "complete",
) -> StructuralGraphResult:
    return StructuralGraphResult(
        index=StructuralGraphIndexStatus(
            state="available",
            provider="codegraph",
            revision_side=revision,
        ),
        revision_side=revision,
        ownership_relations=relations,
        ownership_coverage=StructuralOwnershipCoverage(
            state=coverage_state,
            observed_symbol_ids=observed,
            relation_count=len(relations),
            limiting_dimensions=(
                ("depth_budget",) if coverage_state == "truncated" else ()
            ),
        ),
    )


def _catalog(*results: StructuralGraphResult):
    return build_evidence_catalog(
        ReviewSourcePacket(
            repository="acme/widget",
            pull_request=1,
            title="Change ownership",
            source_records=(),
        ).with_revision(),
        DiffHunkCollection(),
        StructuralGraphCollection(revisions=results),
    )


def _changes(catalog):
    return tuple(
        item
        for item in catalog.items
        if item.kind == "structural_ownership_change"
    )


def test_same_ownership_on_both_revisions_is_retained_once() -> None:
    catalog = _catalog(
        _result("base", _ownership()),
        _result("head", _ownership()),
    )

    changes = _changes(catalog)
    assert len(changes) == 1
    assert changes[0].operation == "retained"
    identity = changes[0].structural_ownership_change
    assert identity is not None
    assert (
        identity.parent_provider_symbol_id,
        identity.child_provider_symbol_id,
    ) == ("P", "C")
    assert identity.base_ownership_evidence_id is not None
    assert identity.head_ownership_evidence_id is not None


def test_complete_applicable_coverage_proves_added_and_removed_ownership() -> None:
    added = _catalog(
        _result("base", observed=("C",)),
        _result("head", _ownership()),
    )
    removed = _catalog(
        _result("base", _ownership()),
        _result("head", observed=("C",)),
    )

    assert [item.operation for item in _changes(added)] == ["added"]
    assert [item.operation for item in _changes(removed)] == ["removed"]


def test_incomplete_or_inapplicable_coverage_defers_absence_inference() -> None:
    partial = _catalog(
        _result("base", observed=("C",), coverage_state="truncated"),
        _result("head", _ownership()),
    )
    inapplicable = _catalog(
        _result("base", observed=("other",)),
        _result("head", _ownership()),
    )

    for catalog in (partial, inapplicable):
        assert _changes(catalog) == ()
        assert [
            item.code
            for item in catalog.diagnostics
            if item.code == "structural_ownership_delta_partial_coverage"
        ] == ["structural_ownership_delta_partial_coverage"]
        assert len(
            [
                item
                for item in catalog.items
                if item.kind == "structural_ownership"
            ]
        ) == 1


def test_ownership_only_ancestors_are_revision_provenance_not_changed_anchors() -> None:
    catalog = _catalog(_result("head", _ownership()))

    symbols = tuple(item for item in catalog.items if item.kind == "symbol")
    assert {item.metadata["symbol_id"] for item in symbols} == {"P", "C"}
    assert all(item.changed is False for item in symbols)
    assert all(item.role in {"runtime_context", "test_context"} for item in symbols)
    ownership = next(
        item for item in catalog.items if item.kind == "structural_ownership"
    )
    identity = ownership.structural_ownership
    assert identity is not None
    assert {
        identity.parent_symbol_evidence_id,
        identity.child_symbol_evidence_id,
    } == {item.id for item in symbols}
