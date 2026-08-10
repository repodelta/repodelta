from __future__ import annotations

from dataclasses import replace

import pytest

from repodelta.changes.hunks import parse_changed_files
from repodelta.facts.catalog import build_evidence_catalog
from repodelta.model.contracts import (
    ChangedFile,
    EvidenceCatalog,
    ReviewSourcePacket,
    StructuralReplacementCandidate,
)
from repodelta.providers.structural import (
    GraphSymbol,
    HunkSymbolOverlap,
    StructuralGraphCollection,
    StructuralGraphIndexStatus,
    StructuralGraphResult,
)


def _symbol(
    identifier: str,
    qualified_name: str,
    *,
    kind: str = "function",
) -> GraphSymbol:
    return GraphSymbol(
        id=identifier,
        kind=kind,
        name=qualified_name.rsplit(".", 1)[-1],
        qualified_name=qualified_name,
        file_path="src/service.py",
        language="python",
        start_line=1,
        end_line=1,
    )


def _catalog(
    base_symbols: tuple[GraphSymbol, ...],
    head_symbols: tuple[GraphSymbol, ...],
) -> EvidenceCatalog:
    changed_file = ChangedFile(
        base_path="src/service.py",
        head_path="src/service.py",
        patch="@@ -1 +1 @@\n-def old(): pass\n+def new(): pass\n",
    )
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=1,
        title="Replace a symbol",
        source_records=(),
        changed_files=(changed_file,),
    ).with_revision()
    changes = parse_changed_files(packet.changed_files)
    hunk_id = changes.hunks[0].id
    graph = StructuralGraphCollection(
        revisions=(
            StructuralGraphResult(
                index=StructuralGraphIndexStatus(
                    state="available",
                    provider="codegraph",
                    revision_side="base",
                ),
                revision_side="base",
                hunk_count=1,
                overlaps=tuple(
                    HunkSymbolOverlap(hunk_id, symbol, (1,))
                    for symbol in base_symbols
                ),
            ),
            StructuralGraphResult(
                index=StructuralGraphIndexStatus(
                    state="available",
                    provider="codegraph",
                    revision_side="head",
                ),
                revision_side="head",
                hunk_count=1,
                overlaps=tuple(
                    HunkSymbolOverlap(hunk_id, symbol, (1,))
                    for symbol in head_symbols
                ),
            ),
        )
    )
    return build_evidence_catalog(packet, changes, graph)


def test_exact_replacement_relation_collects_non_authoritative_candidate() -> None:
    catalog = _catalog(
        (_symbol("old", "service.old"),),
        (_symbol("new", "service.new"),),
    )

    changes = {
        item.operation: item
        for item in catalog.items
        if item.kind == "structural_change"
    }
    assert set(changes) == {"removed", "added"}
    candidate = catalog.structural_replacement_candidates[0]
    assert candidate.removed_change_evidence_id == changes["removed"].id
    assert candidate.added_change_evidence_id == changes["added"].id
    assert candidate.change_relation_ids == (catalog.change_relations[0].id,)
    assert candidate.signals == (
        "shared_replacement_relation",
        "same_symbol_kind",
    )
    assert all(
        item.kind != "structural_replacement_candidate"
        for item in catalog.items
    )


def test_many_to_many_candidates_are_stable_and_not_selected() -> None:
    catalog = _catalog(
        (
            _symbol("old-a", "service.old_a"),
            _symbol("old-b", "service.old_b"),
        ),
        (
            _symbol("new-a", "service.new_a"),
            _symbol("new-b", "service.new_b"),
        ),
    )
    repeated = _catalog(
        (
            _symbol("old-b", "service.old_b"),
            _symbol("old-a", "service.old_a"),
        ),
        (
            _symbol("new-b", "service.new_b"),
            _symbol("new-a", "service.new_a"),
        ),
    )

    assert len(catalog.structural_replacement_candidates) == 4
    assert catalog.structural_replacement_candidates == (
        repeated.structural_replacement_candidates
    )


def test_different_symbol_kinds_do_not_form_a_candidate() -> None:
    catalog = _catalog(
        (_symbol("old", "service.old", kind="class"),),
        (_symbol("new", "service.new", kind="function"),),
    )

    assert catalog.structural_replacement_candidates == ()


def test_candidate_rejects_same_endpoint() -> None:
    with pytest.raises(ValueError, match="endpoints must differ"):
        StructuralReplacementCandidate(
            id="replacement:invalid",
            removed_change_evidence_id="E:change:same",
            added_change_evidence_id="E:change:same",
            change_relation_ids=("relation:1",),
        )


@pytest.mark.parametrize(
    ("removed_id", "added_id", "message"),
    (
        ("missing", "valid_added", "removed endpoint"),
        ("valid_added", "valid_removed", "removed endpoint"),
        ("valid_removed", "missing", "added endpoint"),
    ),
)
def test_catalog_rejects_invalid_candidate_endpoints(
    removed_id: str,
    added_id: str,
    message: str,
) -> None:
    catalog = _catalog(
        (_symbol("old", "service.old"),),
        (_symbol("new", "service.new"),),
    )
    candidate = catalog.structural_replacement_candidates[0]
    added = next(
        item
        for item in catalog.items
        if item.id == candidate.added_change_evidence_id
    )
    removed = next(
        item
        for item in catalog.items
        if item.id == candidate.removed_change_evidence_id
    )
    endpoint_ids = {
        "missing": "E:structural_change:missing",
        "valid_added": added.id,
        "valid_removed": removed.id,
    }
    invalid = StructuralReplacementCandidate(
        id="replacement:invalid",
        removed_change_evidence_id=endpoint_ids[removed_id],
        added_change_evidence_id=endpoint_ids[added_id],
        change_relation_ids=candidate.change_relation_ids,
    )

    with pytest.raises(ValueError, match=message):
        replace(
            catalog,
            structural_replacement_candidates=(invalid,),
        ).validate_consistency()


def test_catalog_rejects_non_added_candidate_endpoint() -> None:
    catalog = _catalog(
        (_symbol("old", "service.old"),),
        (_symbol("new", "service.new"),),
    )
    candidate = catalog.structural_replacement_candidates[0]
    items = tuple(
        replace(item, operation="removed")
        if item.id == candidate.added_change_evidence_id
        else item
        for item in catalog.items
    )

    with pytest.raises(ValueError, match="added endpoint"):
        replace(catalog, items=items).validate_consistency()
