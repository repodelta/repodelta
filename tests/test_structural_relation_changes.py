from __future__ import annotations

from prismcode.changes.hunks import DiffHunkCollection
from prismcode.facts.catalog import build_evidence_catalog
from prismcode.model.contracts import ReviewSourcePacket
from prismcode.providers.structural import (
    GraphPathStep,
    GraphSymbol,
    StructuralGraphCollection,
    StructuralGraphIndexStatus,
    StructuralGraphResult,
    StructuralPath,
    StructuralSeedCoverage,
)


def _symbol(identifier: str) -> GraphSymbol:
    return GraphSymbol(
        id=identifier,
        kind="function",
        name=identifier,
        qualified_name=f"service.{identifier}",
        file_path=f"src/{identifier}.py",
        language="python",
        start_line=1,
        end_line=2,
    )


def _path(
    *identifiers: str,
    seed: str = "A",
    directions: tuple[str, ...] | None = None,
) -> StructuralPath:
    symbols = tuple(_symbol(identifier) for identifier in identifiers)
    path_directions = directions or ("outgoing",) * (len(symbols) - 1)
    return StructuralPath(
        seed_symbol_id=seed,
        steps=tuple(
            GraphPathStep(
                source=source,
                target=target,
                relation="calls",
                direction=direction,
            )
            for source, target, direction in zip(
                symbols[:-1],
                symbols[1:],
                path_directions,
                strict=True,
            )
        ),
        classification="runtime",
    )


def _result(
    revision: str,
    *paths: StructuralPath,
    state: str = "available",
    complete_seed: str = "A",
) -> StructuralGraphResult:
    return StructuralGraphResult(
        index=StructuralGraphIndexStatus(
            state=state,
            provider="codegraph",
            revision_side=revision,
        ),
        revision_side=revision,
        paths=paths,
        traversal_coverage=(
            StructuralSeedCoverage(
                seed_symbol_id=complete_seed,
                state="complete",
                node_count=3,
                path_count=len(paths),
            ),
        ),
    )


def _catalog(*results: StructuralGraphResult):
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=1,
        title="Change relations",
        source_records=(),
    ).with_revision()
    return build_evidence_catalog(
        packet,
        DiffHunkCollection(),
        StructuralGraphCollection(revisions=results),
    )


def _relation_changes(catalog):
    return tuple(
        item
        for item in catalog.items
        if item.kind == "structural_relation_change"
    )


def test_same_directed_relation_on_both_revisions_is_retained() -> None:
    catalog = _catalog(
        _result("base", _path("A", "B")),
        _result("head", _path("A", "B")),
    )

    changes = _relation_changes(catalog)
    assert len(changes) == 1
    assert changes[0].operation == "retained"
    identity = changes[0].structural_relation_change
    assert identity is not None
    assert (identity.source_provider_symbol_id, identity.target_provider_symbol_id) == (
        "A",
        "B",
    )
    assert len(identity.base_path_evidence_ids) == 1
    assert len(identity.head_path_evidence_ids) == 1


def test_complete_opposite_revision_proves_added_and_removed_relations() -> None:
    added = _catalog(
        _result("base"),
        _result("head", _path("A", "B")),
    )
    removed = _catalog(
        _result("base", _path("A", "B")),
        _result("head"),
    )

    assert [item.operation for item in _relation_changes(added)] == ["added"]
    assert [item.operation for item in _relation_changes(removed)] == ["removed"]


def test_incoming_and_outgoing_observations_share_actual_edge_identity() -> None:
    catalog = _catalog(
        _result("base", _path("A", "B")),
        _result(
            "head",
            _path("B", "A", seed="A", directions=("incoming",)),
        ),
    )

    changes = _relation_changes(catalog)
    assert len(changes) == 1
    assert changes[0].operation == "retained"


def test_duplicate_path_observations_converge_to_one_relation_change() -> None:
    catalog = _catalog(
        _result("base"),
        _result(
            "head",
            _path("A", "B"),
            _path("A", "B", "C"),
        ),
    )

    changes = _relation_changes(catalog)
    assert len(
        tuple(
            item
            for item in changes
            if item.structural_relation_change is not None
            and item.structural_relation_change.target_provider_symbol_id == "B"
        )
    ) == 1
    first_edge = next(
        item
        for item in changes
        if item.structural_relation_change is not None
        and item.structural_relation_change.target_provider_symbol_id == "B"
    )
    assert len(first_edge.structural_relation_change.head_path_evidence_ids) == 2


def test_partial_opposite_revision_defers_absence_inference() -> None:
    catalog = _catalog(
        _result("base", state="partial"),
        _result("head", _path("A", "B")),
    )

    assert _relation_changes(catalog) == ()
    assert [
        item.code
        for item in catalog.diagnostics
        if item.code == "structural_relation_delta_partial_coverage"
    ] == ["structural_relation_delta_partial_coverage"]
