from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from prismcode.model.contracts import (
    AssociationSignature,
    ChangeRelation,
    ChangedFile,
    ChangedLine,
    ChangeOperation,
    Diagnostic,
    EvidenceCatalog,
    EvidenceClassification,
    EvidenceItem,
    GuardrailScanDiagnostic,
    GuardrailScanResult,
    GuardrailScanResultSet,
    ReviewSourcePacket,
    SourceRef,
    StructuralChangeIdentity,
    StructuralOwnershipChangeIdentity,
    StructuralOwnershipIdentity,
    StructuralRelationChangeIdentity,
    SuppliedEvidence,
    VerificationObservation,
    VerificationIdentity,
)
from prismcode.changes.hunks import (
    ChangedHunk,
    DiffHunkCollection,
)
from prismcode.facts.lexical import association_signature, merge_signatures
from prismcode.providers.structural import (
    GraphSymbol,
    StructuralGraphCollection,
    StructuralGraphResult,
    StructuralPath,
    StructuralRevision,
)

_DOCUMENT_SUFFIXES = {".md", ".mdx", ".rst", ".txt", ".pdf", ".doc", ".docx"}
_WORKFLOW_PREFIXES = (".github/workflows/", ".circleci/")
_CONFIG_NAMES = {
    "pyproject.toml",
    "setup.cfg",
    "tox.ini",
    "package.json",
    "tsconfig.json",
    "dockerfile",
}
_DEPENDENCY_NAMES = {
    "requirements.txt",
    "poetry.lock",
    "uv.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "cargo.lock",
    "go.sum",
}


def build_evidence_catalog(
    packet: ReviewSourcePacket,
    changes: DiffHunkCollection,
    structural_graph: StructuralGraphCollection | None = None,
    *,
    supplied: tuple[SuppliedEvidence, ...] = (),
    guardrail_scan_results: GuardrailScanResultSet = GuardrailScanResultSet(),
) -> EvidenceCatalog:
    """Normalize source, structural, and supplied facts into one ID-addressed catalog."""

    items: dict[str, EvidenceItem] = {}
    hunks_by_path: dict[str, list[ChangedHunk]] = {}
    for hunk in changes.hunks:
        hunks_by_path.setdefault(hunk.file_path, []).append(hunk)
    hunks_by_id = {hunk.id: hunk for hunk in changes.hunks}
    change_relations = tuple(
        relation for hunk in changes.hunks for relation in hunk.relations
    )
    mapped_lines: dict[tuple[StructuralRevision, str], set[int]] = {}
    has_base_graph = (
        structural_graph is not None
        and structural_graph.for_revision("base") is not None
    )
    ownership_diagnostics: tuple[Diagnostic, ...] = ()
    structural_relation_diagnostics: tuple[Diagnostic, ...] = ()
    if structural_graph is not None:
        for revision_graph in structural_graph.revisions:
            for overlap in revision_graph.overlaps:
                mapped_lines.setdefault(
                    (revision_graph.revision_side, overlap.hunk_id),
                    set(),
                ).update(overlap.changed_lines)

    for changed_file in packet.changed_files:
        file_hunks = hunks_by_path.get(changed_file.path, ())
        if not file_hunks:
            _put(items, _changed_file_fallback(changed_file))
            continue
        for hunk in file_hunks:
            for relation in hunk.relations:
                uncovered_added = tuple(
                    line
                    for line in relation.added
                    if line.number not in mapped_lines.get(("head", hunk.id), set())
                )
                uncovered_removed = (
                    tuple(
                        line
                        for line in relation.removed
                        if line.number
                        not in mapped_lines.get(("base", hunk.id), set())
                    )
                    if has_base_graph or relation.kind == "removed"
                    else ()
                )
                if uncovered_added or uncovered_removed:
                    _put(
                        items,
                        _change_relation_item(
                            changed_file,
                            relation,
                            added=uncovered_added,
                            removed=(
                                uncovered_removed
                                if has_base_graph
                                else relation.removed
                            ),
                        ),
                    )

    if structural_graph is not None:
        for revision_graph in structural_graph.revisions:
            _put_structural_revision(
                items,
                revision_graph,
                hunks_by_id=hunks_by_id,
            )
        _assign_review_symbol_ids(items)
        _put_structural_changes(
            items,
            change_relations=change_relations,
            changed_files=packet.changed_files,
        )
        ownership_diagnostics = _put_structural_ownership_changes(
            items,
            structural_graph,
        )
        structural_relation_diagnostics = _put_structural_relation_changes(
            items,
            structural_graph,
        )

    for observation in packet.verification_observations:
        _put(items, verification_evidence(observation))
    for result in guardrail_scan_results.results:
        if result.state != "unavailable":
            _put(items, boundary_evidence(result))
    for item in supplied:
        _put(
            items,
            provided_evidence(
                summary=item.summary,
                kind=item.kind,
                classification=item.classification,
                sources=item.sources,
                statement_ids=item.statement_ids,
            ),
        )

    catalog = EvidenceCatalog(
        items=tuple(sorted(items.values(), key=lambda item: item.id)),
        change_relations=change_relations,
        diagnostics=(
            *changes.diagnostics,
            *ownership_diagnostics,
            *structural_relation_diagnostics,
            *(
                diagnostic
                for result in guardrail_scan_results.results
                for diagnostic in result.diagnostics
            ),
        ),
        guardrail_scan_diagnostics=tuple(
            GuardrailScanDiagnostic(
                code=diagnostic.code,
                message=diagnostic.message,
                plan_id=result.plan_id,
                guardrail_id=result.guardrail_id,
            )
            for result in guardrail_scan_results.results
            for diagnostic in result.diagnostics
        ),
    )
    catalog.validate_consistency()
    return catalog


def _put_structural_revision(
    items: dict[str, EvidenceItem],
    structural_graph: StructuralGraphResult,
    *,
    hunks_by_id: dict[str, ChangedHunk],
) -> None:
        revision_side = structural_graph.revision_side
        changed_symbol_ids = {
            overlap.symbol.id for overlap in structural_graph.overlaps
        }
        path_ids = {
            _path_key(path, revision_side): evidence_id(
                "structural_path", _path_key(path, revision_side)
            )
            for path in structural_graph.paths
        }
        symbol_paths: dict[str, set[str]] = {}
        for path in structural_graph.paths:
            path_id = path_ids[_path_key(path, revision_side)]
            symbol_paths.setdefault(path.seed_symbol_id, set()).add(path_id)
            for step in path.steps:
                symbol_paths.setdefault(step.source.id, set()).add(path_id)
                symbol_paths.setdefault(step.target.id, set()).add(path_id)

        for relation in structural_graph.ownership_relations:
            for symbol in (relation.parent, relation.child):
                if symbol.id in changed_symbol_ids:
                    continue
                _put(
                    items,
                    _symbol_item(
                        symbol,
                        changed=False,
                        operation="unchanged",
                        revision_side=revision_side,
                        structural_path_ids=tuple(
                            sorted(symbol_paths.get(symbol.id, ()))
                        ),
                    ),
                )

        for overlap in structural_graph.overlaps:
            hunk = hunks_by_id.get(overlap.hunk_id)
            relation_ids, operation, head_signature, base_signature = (
                _overlap_change(
                    hunk,
                    overlap.changed_lines,
                    revision_side=revision_side,
                )
            )
            _put(
                items,
                _symbol_item(
                    overlap.symbol,
                    changed=True,
                    operation=operation,
                    revision_side=revision_side,
                    change_relation_ids=relation_ids,
                    structural_path_ids=tuple(
                        sorted(symbol_paths.get(overlap.symbol.id, ()))
                    ),
                    extra_sources=overlap.sources,
                    head_signature=head_signature,
                    base_signature=base_signature,
                    changed_hunk_ids=(overlap.hunk_id,),
                    changed_lines=overlap.changed_lines,
                ),
            )

        for relation in structural_graph.ownership_relations:
            ownership_id = _ownership_evidence_id(
                relation.parent.id,
                relation.child.id,
                revision_side,
            )
            _put(
                items,
                EvidenceItem(
                    id=ownership_id,
                    kind="structural_ownership",
                    summary=(
                        f"Observed ownership: {relation.parent.qualified_name} "
                        f"contains {relation.child.qualified_name}"
                    ),
                    classification=_path_classification(relation.child.file_path),
                    profile="unknown",
                    authority="structural_provider",
                    revision_side=revision_side,
                    operation="observed",
                    role="structural_ownership",
                    sources=relation.sources,
                    structural_ownership=StructuralOwnershipIdentity(
                        parent_provider_symbol_id=relation.parent.id,
                        child_provider_symbol_id=relation.child.id,
                        parent_symbol_evidence_id=_symbol_evidence_id(
                            relation.parent.id,
                            revision_side,
                        ),
                        child_symbol_evidence_id=_symbol_evidence_id(
                            relation.child.id,
                            revision_side,
                        ),
                    ),
                ),
            )
        for path in structural_graph.paths:
            for step in path.steps:
                for symbol in (step.source, step.target):
                    if symbol.id in changed_symbol_ids:
                        continue
                    _put(
                        items,
                        _symbol_item(
                            symbol,
                            changed=False,
                            operation="unchanged",
                            revision_side=revision_side,
                            structural_path_ids=tuple(
                                sorted(symbol_paths.get(symbol.id, ()))
                            ),
                        ),
                    )
            path_id = path_ids[_path_key(path, revision_side)]
            _put(
                items,
                EvidenceItem(
                    id=path_id,
                    kind="structural_path",
                    summary=_path_summary(path),
                    classification=path.classification,
                    profile="structural_path",
                    authority="structural_provider",
                    revision_side=revision_side,
                    operation="observed",
                    role="structural_path",
                    sources=path.sources,
                    structural_path_ids=(path_id,),
                    metadata={
                        "seed_symbol_id": path.seed_symbol_id,
                        "depth": path.depth,
                        "steps": tuple(
                            {
                                "source_evidence_id": _symbol_evidence_id(
                                    step.source.id,
                                    revision_side,
                                ),
                                "target_evidence_id": _symbol_evidence_id(
                                    step.target.id,
                                    revision_side,
                                ),
                                "relation": step.relation,
                                "direction": step.direction,
                            }
                            for step in path.steps
                        ),
                    },
                ),
            )


def _put_structural_changes(
    items: dict[str, EvidenceItem],
    *,
    change_relations: tuple[ChangeRelation, ...],
    changed_files: tuple[ChangedFile, ...],
) -> None:
    """Converge revision symbols into one canonical operation truth."""

    relations_by_id = {item.id: item for item in change_relations}
    mapped_relation_lines: dict[
        tuple[StructuralRevision, str],
        set[int],
    ] = {}
    for item in items.values():
        if item.kind != "symbol" or not item.changed:
            continue
        changed_lines = set(item.metadata.get("changed_lines", ()))
        for relation_id in item.change_relation_ids:
            relation = relations_by_id[relation_id]
            directional_lines = set(
                relation.added_lines
                if item.revision_side == "head"
                else relation.removed_lines
            )
            mapped_relation_lines.setdefault(
                (item.revision_side, relation_id),
                set(),
            ).update(changed_lines & directional_lines)
    file_statuses = {item.path: item.status.casefold() for item in changed_files}
    symbols_by_review_id: dict[str, dict[str, EvidenceItem]] = {}
    for item in items.values():
        if item.kind != "symbol" or not item.changed:
            continue
        review_symbol_id = str(item.metadata["review_symbol_id"])
        symbols_by_review_id.setdefault(review_symbol_id, {})[
            item.revision_side
        ] = item

    for review_symbol_id, revisions in symbols_by_review_id.items():
        base = revisions.get("base")
        head = revisions.get("head")
        operation = _structural_change_operation(
            base=base,
            head=head,
            relations_by_id=relations_by_id,
            mapped_relation_lines=mapped_relation_lines,
            file_statuses=file_statuses,
        )
        exemplar = head or base
        assert exemplar is not None
        _put(
            items,
            EvidenceItem(
                id=evidence_id("structural_change", review_symbol_id),
                summary=(
                    f"{operation.title()} {exemplar.metadata['symbol_kind']}: "
                    f"{exemplar.metadata['qualified_name']}"
                ),
                kind="structural_change",
                classification=exemplar.classification,
                profile=exemplar.profile,
                authority="structural_provider",
                revision_side="review",
                operation=operation,
                role="changed_anchor",
                changed=True,
                head_signature=merge_signatures(
                    *(
                        item.head_signature
                        for item in (base, head)
                        if item is not None
                    )
                ),
                base_signature=merge_signatures(
                    *(
                        item.base_signature
                        for item in (base, head)
                        if item is not None
                    )
                ),
                sources=_unique_sources(
                    (
                        *(base.sources if base is not None else ()),
                        *(head.sources if head is not None else ()),
                    )
                ),
                change_relation_ids=tuple(
                    sorted(
                        {
                            *(base.change_relation_ids if base is not None else ()),
                            *(head.change_relation_ids if head is not None else ()),
                        }
                    )
                ),
                structural_path_ids=tuple(
                    sorted(
                        {
                            *(base.structural_path_ids if base is not None else ()),
                            *(head.structural_path_ids if head is not None else ()),
                        }
                    )
                ),
                structural_change=StructuralChangeIdentity(
                    review_symbol_id=review_symbol_id,
                    base_symbol_evidence_id=base.id if base is not None else None,
                    head_symbol_evidence_id=head.id if head is not None else None,
                ),
                metadata={
                    "review_symbol_id": review_symbol_id,
                    "qualified_name": exemplar.metadata["qualified_name"],
                    "path": exemplar.metadata["path"],
                    "symbol_kind": exemplar.metadata["symbol_kind"],
                    "start_line": exemplar.metadata["start_line"],
                },
            ),
        )


def _structural_change_operation(
    *,
    base: EvidenceItem | None,
    head: EvidenceItem | None,
    relations_by_id: dict[str, ChangeRelation],
    mapped_relation_lines: dict[tuple[StructuralRevision, str], set[int]],
    file_statuses: dict[str, str],
) -> ChangeOperation:
    if base is not None and head is not None:
        return "modified"

    exemplar = head or base
    assert exemplar is not None
    if exemplar.metadata["symbol_kind"] == "file":
        status = file_statuses.get(str(exemplar.metadata["path"]), "modified")
        if status == "added" and head is not None:
            return "added"
        if status == "removed" and base is not None:
            return "removed"
        return "modified"

    relation_ids = exemplar.change_relation_ids
    relations = tuple(relations_by_id[item] for item in relation_ids)
    if head is not None and relations and all(
        relation.kind == "added" for relation in relations
    ):
        return "added"
    if base is not None and relations and all(
        relation.kind == "removed" for relation in relations
    ):
        return "removed"
    opposite_revision: StructuralRevision = "base" if head is not None else "head"
    if relation_ids and all(
        _opposite_relation_is_fully_mapped(
            relations_by_id[relation_id],
            relation_id=relation_id,
            opposite_revision=opposite_revision,
            mapped_relation_lines=mapped_relation_lines,
        )
        for relation_id in relation_ids
    ):
        return "added" if head is not None else "removed"
    return "modified"


def _opposite_relation_is_fully_mapped(
    relation: ChangeRelation,
    *,
    relation_id: str,
    opposite_revision: StructuralRevision,
    mapped_relation_lines: dict[tuple[StructuralRevision, str], set[int]],
) -> bool:
    opposite_lines = set(
        relation.removed_lines
        if opposite_revision == "base"
        else relation.added_lines
    )
    return bool(opposite_lines) and opposite_lines <= mapped_relation_lines.get(
        (opposite_revision, relation_id),
        set(),
    )


def _assign_review_symbol_ids(items: dict[str, EvidenceItem]) -> None:
    """Replace candidate keys with exact, collision-safe review identities."""

    symbols_by_candidate: dict[str, list[EvidenceItem]] = {}
    for item in items.values():
        if item.kind == "symbol":
            symbols_by_candidate.setdefault(
                str(item.metadata["review_symbol_id"]),
                [],
            ).append(item)

    for candidate, symbols in symbols_by_candidate.items():
        revision_counts = {
            revision: sum(item.revision_side == revision for item in symbols)
            for revision in ("base", "head")
        }
        ambiguous = any(count > 1 for count in revision_counts.values())
        for item in symbols:
            review_symbol_id = (
                evidence_id(
                    "review_symbol",
                    "\0".join(
                        (
                            candidate,
                            item.revision_side,
                            str(item.metadata["symbol_id"]),
                        )
                    ),
                )
                if ambiguous
                else candidate
            )
            items[item.id] = replace(
                item,
                metadata={
                    **item.metadata,
                    "review_symbol_id": review_symbol_id,
                },
            )


def _put_structural_ownership_changes(
    items: dict[str, EvidenceItem],
    structural_graph: StructuralGraphCollection,
) -> tuple[Diagnostic, ...]:
    """Converge revision ancestry into one canonical ownership truth."""

    observed: dict[
        tuple[str, str],
        dict[StructuralRevision, str],
    ] = {}
    for item in tuple(items.values()):
        if item.kind != "structural_ownership":
            continue
        identity = item.structural_ownership
        assert identity is not None
        parent = items[identity.parent_symbol_evidence_id]
        child = items[identity.child_symbol_evidence_id]
        observed.setdefault(
            (
                str(parent.metadata["review_symbol_id"]),
                str(child.metadata["review_symbol_id"]),
            ),
            {},
        )[item.revision_side] = item.id

    changed_operations = {
        item.structural_change.review_symbol_id: item.operation
        for item in items.values()
        if item.kind == "structural_change"
        and item.structural_change is not None
    }
    deferred = {"added": 0, "removed": 0}
    for key, revisions in sorted(observed.items()):
        base_id = revisions.get("base")
        head_id = revisions.get("head")
        operation = _revision_relation_operation(
            base_present=base_id is not None,
            head_present=head_id is not None,
            added_endpoint=_ownership_endpoint_changed(
                key,
                changed_operations,
                "added",
            ),
            removed_endpoint=_ownership_endpoint_changed(
                key,
                changed_operations,
                "removed",
            ),
            base_proves_absence=_opposite_ownership_proves_absence(
                structural_graph,
                items,
                "base",
                key[1],
            ),
            head_proves_absence=_opposite_ownership_proves_absence(
                structural_graph,
                items,
                "head",
                key[1],
            ),
        )
        if operation is None:
            deferred["added" if head_id is not None else "removed"] += 1
            continue

        provenance_ids = tuple(
            value for value in (head_id, base_id) if value is not None
        )
        provenance = tuple(items[value] for value in provenance_ids)
        classifications = {item.classification for item in provenance}
        _put(
            items,
            EvidenceItem(
                id=evidence_id(
                    "structural_ownership_change",
                    "\0".join(key),
                ),
                summary=(
                    f"{operation.title()} structural ownership: "
                    f"{key[0]} contains {key[1]}"
                ),
                kind="structural_ownership_change",
                classification=(
                    next(iter(classifications))
                    if len(classifications) == 1
                    else "mixed"
                ),
                profile="unknown",
                authority="structural_provider",
                revision_side="review",
                operation=operation,
                role="structural_ownership",
                changed=operation != "retained",
                sources=_unique_sources(
                    tuple(
                        source
                        for item in provenance
                        for source in item.sources
                    )
                ),
                structural_ownership_change=StructuralOwnershipChangeIdentity(
                    parent_review_symbol_id=key[0],
                    child_review_symbol_id=key[1],
                    base_ownership_evidence_id=base_id,
                    head_ownership_evidence_id=head_id,
                ),
            ),
        )

    diagnostics = []
    for operation, count in deferred.items():
        if count:
            diagnostics.append(
                Diagnostic(
                    code="structural_ownership_delta_partial_coverage",
                    message=(
                        f"{count} observed {operation} ownership "
                        f"candidate{'s were' if count != 1 else ' was'} retained "
                        "as revision provenance because opposite-revision "
                        "ownership coverage did not prove absence."
                    ),
                    severity="info",
                )
            )
    return tuple(diagnostics)


def _ownership_endpoint_changed(
    key: tuple[str, str],
    changed_operations: dict[str, ChangeOperation],
    operation: ChangeOperation,
) -> bool:
    return any(changed_operations.get(symbol_id) == operation for symbol_id in key)


def _opposite_ownership_proves_absence(
    structural_graph: StructuralGraphCollection,
    items: dict[str, EvidenceItem],
    revision: StructuralRevision,
    child_review_symbol_id: str,
) -> bool:
    result = structural_graph.for_revision(revision)
    coverage = result.ownership_coverage if result is not None else None
    provider_symbol_ids = {
        str(item.metadata["symbol_id"])
        for item in items.values()
        if item.kind == "symbol"
        and item.metadata.get("review_symbol_id") == child_review_symbol_id
    }
    return (
        result is not None
        and result.index.state == "available"
        and coverage is not None
        and coverage.state == "complete"
        and bool(provider_symbol_ids & set(coverage.observed_symbol_ids))
    )


def _revision_relation_operation(
    *,
    base_present: bool,
    head_present: bool,
    added_endpoint: bool,
    removed_endpoint: bool,
    base_proves_absence: bool,
    head_proves_absence: bool,
) -> ChangeOperation | None:
    """Return the sole review operation for a revision-aware relation."""

    if base_present and head_present:
        return "retained"
    if head_present and (added_endpoint or base_proves_absence):
        return "added"
    if base_present and (removed_endpoint or head_proves_absence):
        return "removed"
    return None


def _put_structural_relation_changes(
    items: dict[str, EvidenceItem],
    structural_graph: StructuralGraphCollection,
) -> tuple[Diagnostic, ...]:
    """Converge revision paths into one canonical directed-relation truth."""

    observed: dict[
        tuple[str, str, str],
        dict[StructuralRevision, set[str]],
    ] = {}
    path_seed_ids: dict[str, str] = {}
    for item in tuple(items.values()):
        if item.kind != "structural_path":
            continue
        revision = item.revision_side
        if revision not in {"base", "head"}:
            continue
        path_seed_ids[item.id] = str(item.metadata["seed_symbol_id"])
        for step in item.metadata.get("steps", ()):
            source = items[step["source_evidence_id"]]
            target = items[step["target_evidence_id"]]
            source_review_id = str(source.metadata["review_symbol_id"])
            target_review_id = str(target.metadata["review_symbol_id"])
            if step["direction"] == "incoming":
                source_review_id, target_review_id = (
                    target_review_id,
                    source_review_id,
                )
            key = (
                source_review_id,
                target_review_id,
                step["relation"],
            )
            observed.setdefault(key, {}).setdefault(revision, set()).add(item.id)

    changed_operations = {
        item.structural_change.review_symbol_id: item.operation
        for item in items.values()
        if item.kind == "structural_change"
        and item.structural_change is not None
    }
    deferred = {"added": 0, "removed": 0}
    for key, revisions in sorted(observed.items()):
        base_path_ids = tuple(sorted(revisions.get("base", ())))
        head_path_ids = tuple(sorted(revisions.get("head", ())))
        operation = _revision_relation_operation(
            base_present=bool(base_path_ids),
            head_present=bool(head_path_ids),
            added_endpoint=_relation_endpoint_changed(
                key,
                changed_operations,
                "added",
            ),
            removed_endpoint=_relation_endpoint_changed(
                key,
                changed_operations,
                "removed",
            ),
            base_proves_absence=_opposite_revision_proves_absence(
                structural_graph,
                "base",
                head_path_ids,
                path_seed_ids,
            ),
            head_proves_absence=_opposite_revision_proves_absence(
                structural_graph,
                "head",
                base_path_ids,
                path_seed_ids,
            ),
        )
        if operation is None:
            deferred["added" if head_path_ids else "removed"] += 1
            continue

        exemplar_paths = (*head_path_ids, *base_path_ids)
        path_items = tuple(items[path_id] for path_id in exemplar_paths)
        classifications = {item.classification for item in path_items}
        identity = "\0".join(key)
        _put(
            items,
            EvidenceItem(
                id=evidence_id("structural_relation_change", identity),
                summary=(
                    f"{operation.title()} structural relation: "
                    f"{key[0]} -[{key[2]}]-> {key[1]}"
                ),
                kind="structural_relation_change",
                classification=(
                    next(iter(classifications))
                    if len(classifications) == 1
                    else "mixed"
                ),
                profile="structural_path",
                authority="structural_provider",
                revision_side="review",
                operation=operation,
                role="structural_relation",
                changed=operation != "retained",
                sources=_unique_sources(
                    tuple(
                        source
                        for path in path_items
                        for source in path.sources
                    )
                ),
                structural_path_ids=tuple(sorted(set(exemplar_paths))),
                structural_relation_change=StructuralRelationChangeIdentity(
                    source_review_symbol_id=key[0],
                    target_review_symbol_id=key[1],
                    relation=key[2],
                    base_path_evidence_ids=base_path_ids,
                    head_path_evidence_ids=head_path_ids,
                ),
            ),
        )

    diagnostics = []
    for operation, count in deferred.items():
        if count:
            diagnostics.append(
                Diagnostic(
                    code="structural_relation_delta_partial_coverage",
                    message=(
                        f"{count} observed {operation} structural relation "
                        f"candidate{'s were' if count != 1 else ' was'} retained "
                        "as revision provenance because opposite-revision "
                        "traversal did not prove absence."
                    ),
                    severity="info",
                )
            )
    return tuple(diagnostics)


def _relation_endpoint_changed(
    key: tuple[str, str, str],
    changed_operations: dict[str, ChangeOperation],
    operation: ChangeOperation,
) -> bool:
    return any(changed_operations.get(symbol_id) == operation for symbol_id in key[:2])


def _opposite_revision_proves_absence(
    structural_graph: StructuralGraphCollection,
    revision: StructuralRevision,
    observed_path_ids: tuple[str, ...],
    path_seed_ids: dict[str, str],
) -> bool:
    result = structural_graph.for_revision(revision)
    if result is None or result.index.state != "available":
        return False
    coverage = {item.seed_symbol_id: item.state for item in result.traversal_coverage}
    return any(
        coverage.get(path_seed_ids[path_id]) == "complete"
        for path_id in observed_path_ids
    )


def evidence_id(kind: str, identity: str) -> str:
    digest = hashlib.sha256(f"{kind}\0{identity}".encode("utf-8")).hexdigest()[:20]
    return f"E:{kind}:{digest}"


def boundary_evidence(result: GuardrailScanResult) -> EvidenceItem:
    """Normalize one observed bounded scan as the sole boundary-fact identity."""

    match_sources = tuple(
        SourceRef(
            label=f"guardrail scan · {match.surface}",
            path=match.path,
            line_start=match.line,
            line_end=match.line,
        )
        for match in result.matches
    )
    return EvidenceItem(
        id=evidence_id("boundary_fact", result.id),
        summary=(
            f"Bounded head scan observed {len(result.matches)} candidate "
            f"match{'es' if len(result.matches) != 1 else ''} "
            f"with {result.state} coverage."
        ),
        kind="boundary_fact",
        classification="mixed",
        profile="unknown",
        authority="guardrail_scan_provider",
        revision_side="head",
        operation="observed",
        role="boundary_fact",
        associated_statement_ids=(result.guardrail_id,),
        guardrail_scan_result=result,
        sources=match_sources,
    )


def provided_evidence(
    *,
    summary: str,
    kind: str,
    classification: EvidenceClassification,
    sources: tuple[SourceRef, ...] = (),
    statement_ids: tuple[str, ...] = (),
) -> EvidenceItem:
    identity = json.dumps(
        {
            "summary": summary,
            "kind": kind,
            "classification": classification,
            "sources": [
                {
                    "label": source.label,
                    "url": source.url,
                    "path": source.path,
                    "line_start": source.line_start,
                    "line_end": source.line_end,
                }
                for source in sources
            ],
            "statement_ids": statement_ids,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return EvidenceItem(
        id=evidence_id("provided", identity),
        summary=summary,
        kind=kind,
        classification=classification,
        profile=(
            "verification"
            if classification in {"ci", "runtime"}
            else "test"
            if classification == "test"
            else "document"
            if classification == "document"
            else "production"
        ),
        authority="supplied",
        revision_side="review",
        operation="observed",
        role="provided_context",
        associated_statement_ids=statement_ids,
        sources=sources,
        metadata={
            "provided": True,
        },
    )


def _changed_file_fallback(changed_file: ChangedFile) -> EvidenceItem:
    path = changed_file.path
    summary = f"{changed_file.status.title()} file: {path}"
    return EvidenceItem(
        id=evidence_id("changed_file", path),
        kind="changed_file",
        summary=summary,
        classification=_path_classification(path),
        profile=_fact_profile(path),
        authority="github_diff",
        revision_side=(
            "base" if changed_file.status == "removed" else "head"
        ),
        operation=(
            "removed"
            if changed_file.status == "removed"
            else "added"
            if changed_file.status == "added"
            else "renamed"
            if changed_file.status == "renamed"
            else "modified"
        ),
        role="changed_anchor",
        changed=True,
        head_signature=association_signature(summary, path),
        sources=(
            SourceRef(
                label="changed file fallback",
                url=changed_file.source_url,
                path=path,
            ),
        ),
        metadata={
            "path": path,
            "status": changed_file.status,
            "additions": changed_file.additions,
            "deletions": changed_file.deletions,
            "changes": changed_file.changes,
            "fallback_reason": "patch_or_hunk_unavailable",
        },
    )


def _change_relation_item(
    changed_file: ChangedFile,
    relation: ChangeRelation,
    *,
    added: tuple[ChangedLine, ...],
    removed: tuple[ChangedLine, ...],
) -> EvidenceItem:
    path = relation.file_path
    head_text = "\n".join(item.text for item in added)
    base_text = "\n".join(item.text for item in removed)
    display_lines = added or removed
    line_start = min((item.number for item in display_lines), default=0)
    line_end = max((item.number for item in display_lines), default=line_start)
    identity = f"{relation.id}:{','.join(str(item.number) for item in added)}"
    summary = (
        f"{relation.kind.title()} change: {path}:{line_start}-{line_end}"
    )
    return EvidenceItem(
        id=evidence_id("change_relation", identity),
        kind="change_relation",
        summary=summary,
        classification=_path_classification(path),
        profile=_fact_profile(path),
        authority="github_diff",
        revision_side="base" if relation.kind == "removed" else "head",
        operation=relation.kind,
        role="changed_anchor",
        changed=True,
        head_signature=association_signature(summary, path, head_text),
        base_signature=association_signature(summary, path, base_text),
        change_relation_ids=(relation.id,),
        sources=(
            SourceRef(
                label="diff hunk",
                url=changed_file.source_url,
                path=path,
                line_start=line_start,
                line_end=line_end,
            ),
        ),
        metadata={
            "hunk_id": relation.hunk_id,
            "path": path,
            "added_lines": tuple(item.number for item in added),
            "removed_lines": tuple(item.number for item in removed),
            "head_preview": head_text[:4000],
            "base_preview": base_text[:4000],
        },
    )


def verification_evidence_id(observation_id: str) -> str:
    return evidence_id("verification", observation_id)


def verification_evidence(observation: VerificationObservation) -> EvidenceItem:
    identity = VerificationIdentity(
        provider=observation.provider.strip().casefold() or "unknown",
        kind=observation.kind,
        name=" ".join(observation.name.split()).casefold(),
    )
    return EvidenceItem(
        id=verification_evidence_id(observation.id),
        summary=(
            f"{observation.name}: {observation.status}/"
            f"{observation.conclusion or 'no conclusion'}"
        ),
        kind=observation.kind,
        classification="runtime" if observation.kind == "manual" else "ci",
        profile="verification",
        authority="verification_provider",
        revision_side="review",
        operation="observed",
        role="verification",
        observed_head_sha=observation.head_sha,
        verification_identity=identity,
        verification_status=observation.status.strip().casefold() or "unknown",
        verification_conclusion=observation.conclusion.strip().casefold(),
        sources=(SourceRef(label=observation.name, url=observation.details_url),),
    )


def _symbol_item(
    symbol: GraphSymbol,
    *,
    changed: bool,
    operation: ChangeOperation,
    revision_side: StructuralRevision = "head",
    structural_path_ids: tuple[str, ...],
    extra_sources: tuple[SourceRef, ...] = (),
    head_signature: AssociationSignature = AssociationSignature(),
    base_signature: AssociationSignature = AssociationSignature(),
    change_relation_ids: tuple[str, ...] = (),
    changed_hunk_ids: tuple[str, ...] = (),
    changed_lines: tuple[int, ...] = (),
) -> EvidenceItem:
    canonical_signature = association_signature(
        symbol.qualified_name,
        symbol.file_path,
    )
    return EvidenceItem(
        id=_symbol_evidence_id(symbol.id, revision_side),
        kind="symbol",
        summary=f"{'Changed' if changed else 'Unchanged'} {symbol.kind}: {symbol.qualified_name}",
        classification=_path_classification(symbol.file_path),
        profile=_fact_profile(symbol.file_path),
        authority="structural_provider",
        revision_side=revision_side,
        operation=operation,
        role=(
            "revision_fact"
            if changed
            else "test_context"
            if _fact_profile(symbol.file_path) == "test"
            else "runtime_context"
        ),
        changed=changed,
        head_signature=(
            merge_signatures(canonical_signature, head_signature)
            if revision_side == "head"
            else head_signature
        ),
        base_signature=(
            merge_signatures(canonical_signature, base_signature)
            if revision_side == "base"
            else base_signature
        ),
        sources=_unique_sources((*symbol.sources, *extra_sources)),
        change_relation_ids=change_relation_ids,
        structural_path_ids=structural_path_ids,
        metadata={
            "symbol_id": symbol.id,
            "review_symbol_id": _review_symbol_id(
                symbol.file_path,
                symbol.qualified_name,
                symbol.kind,
            ),
            "symbol_kind": symbol.kind,
            "qualified_name": symbol.qualified_name,
            "path": symbol.file_path,
            "language": symbol.language,
            "start_line": symbol.start_line,
            "end_line": symbol.end_line,
            "changed_hunk_ids": changed_hunk_ids,
            "changed_lines": changed_lines,
        },
    )


def _review_symbol_id(path: str, qualified_name: str, kind: str) -> str:
    """Return the exact logical identity candidate shared across revisions."""

    return evidence_id(
        "review_symbol",
        "\0".join((path, qualified_name, kind)),
    )


def _overlap_change(
    hunk: ChangedHunk | None,
    changed_lines: tuple[int, ...],
    *,
    revision_side: StructuralRevision,
) -> tuple[
    tuple[str, ...],
    ChangeOperation,
    AssociationSignature,
    AssociationSignature,
]:
    if hunk is None:
        return (
            (),
            "modified",
            AssociationSignature(),
            AssociationSignature(),
        )
    covered = set(changed_lines)
    selected_relations = tuple(
        relation
        for relation in hunk.relations
        if covered
        & set(
            relation.added_lines
            if revision_side == "head"
            else relation.removed_lines
        )
    )
    head_values = []
    base_values = []
    for relation in selected_relations:
        selected = tuple(
            item.text
            for item in (
                relation.added
                if revision_side == "head"
                else relation.removed
            )
            if item.number in covered
        )
        if not selected:
            continue
        if revision_side == "head":
            head_values.extend(selected)
            base_values.extend(item.text for item in relation.removed)
        else:
            base_values.extend(selected)
            head_values.extend(item.text for item in relation.added)
    return (
        tuple(item.id for item in selected_relations),
        (
            (
                "added"
                if all(item.kind == "added" for item in selected_relations)
                else "replaced"
            )
            if revision_side == "head"
            else (
                "removed"
                if all(item.kind == "removed" for item in selected_relations)
                else "replaced"
            )
        ),
        association_signature(*head_values),
        association_signature(*base_values),
    )


def _path_key(path: StructuralPath, revision_side: StructuralRevision) -> str:
    steps = "|".join(
        f"{step.source.id}>{step.direction}:{step.relation}>{step.target.id}"
        for step in path.steps
    )
    identity = f"{path.seed_symbol_id}|{steps}"
    return identity if revision_side == "head" else f"base|{identity}"


def _symbol_evidence_id(
    symbol_id: str,
    revision_side: StructuralRevision,
) -> str:
    identity = symbol_id if revision_side == "head" else f"base:{symbol_id}"
    return evidence_id("symbol", identity)


def _ownership_evidence_id(
    parent_symbol_id: str,
    child_symbol_id: str,
    revision_side: StructuralRevision,
) -> str:
    identity = f"{parent_symbol_id}\0{child_symbol_id}"
    if revision_side == "base":
        identity = f"base\0{identity}"
    return evidence_id("structural_ownership", identity)


def _path_summary(path: StructuralPath) -> str:
    if not path.steps:
        return path.seed_symbol_id
    parts = [path.steps[0].source.qualified_name]
    for step in path.steps:
        arrow = "→" if step.direction == "outgoing" else "←"
        parts.append(f"{arrow}[{step.relation}] {step.target.qualified_name}")
    return " ".join(parts)


def _path_classification(path: str) -> EvidenceClassification:
    normalized = path.casefold().replace("\\", "/")
    name = Path(normalized).name
    if (
        normalized.startswith(("test/", "tests/"))
        or "/test/" in normalized
        or "/tests/" in normalized
        or name.startswith("test_")
        or name.endswith(("_test.py", ".test.js", ".test.ts", ".spec.js", ".spec.ts"))
    ):
        return "test"
    if Path(normalized).suffix in _DOCUMENT_SUFFIXES:
        return "document"
    return "code"


def _fact_profile(path: str) -> str:
    normalized = path.casefold().replace("\\", "/")
    name = Path(normalized).name
    suffix = Path(normalized).suffix
    if _path_classification(path) == "test":
        return "test"
    if suffix in _DOCUMENT_SUFFIXES:
        return "document"
    if normalized.startswith(_WORKFLOW_PREFIXES):
        return "workflow"
    if name in _DEPENDENCY_NAMES:
        return "dependency"
    if name in _CONFIG_NAMES or suffix in {".ini", ".toml", ".yaml", ".yml", ".json"}:
        return "configuration"
    if "migration" in normalized or "schema" in normalized:
        return "schema"
    if any(part in normalized.split("/") for part in ("vendor", "generated", "dist")):
        return "generated"
    return "production"


def _put(items: dict[str, EvidenceItem], candidate: EvidenceItem) -> None:
    existing = items.get(candidate.id)
    if existing is None:
        items[candidate.id] = candidate
        return
    if existing.kind != candidate.kind:
        raise ValueError(f"evidence ID collision for {candidate.id}")
    items[candidate.id] = replace(
        existing,
        changed=existing.changed or candidate.changed,
        operation=_merged_change_operation(existing, candidate),
        sources=_unique_sources((*existing.sources, *candidate.sources)),
        change_relation_ids=tuple(
            sorted(
                {
                    *existing.change_relation_ids,
                    *candidate.change_relation_ids,
                }
            )
        ),
        structural_path_ids=tuple(
            sorted({*existing.structural_path_ids, *candidate.structural_path_ids})
        ),
        head_signature=merge_signatures(
            existing.head_signature,
            candidate.head_signature,
        ),
        base_signature=merge_signatures(
            existing.base_signature,
            candidate.base_signature,
        ),
        metadata=_merge_metadata(existing, candidate),
        summary=candidate.summary if candidate.changed and not existing.changed else existing.summary,
    )


def _merged_change_operation(
    existing: EvidenceItem,
    candidate: EvidenceItem,
) -> ChangeOperation:
    if not candidate.changed:
        return existing.operation
    if not existing.changed:
        return candidate.operation
    return (
        "added"
        if existing.operation == candidate.operation == "added"
        else "replaced"
    )


def _merge_metadata(
    existing: EvidenceItem,
    candidate: EvidenceItem,
) -> dict[str, object]:
    metadata = {**candidate.metadata, **existing.metadata}
    if candidate.kind != "symbol":
        return metadata
    metadata["changed_hunk_ids"] = tuple(
        sorted(
            {
                *existing.metadata.get("changed_hunk_ids", ()),
                *candidate.metadata.get("changed_hunk_ids", ()),
            }
        )
    )
    metadata["changed_lines"] = tuple(
        sorted(
            {
                *existing.metadata.get("changed_lines", ()),
                *candidate.metadata.get("changed_lines", ()),
            }
        )
    )
    return metadata


def _unique_sources(sources: Iterable[SourceRef]) -> tuple[SourceRef, ...]:
    seen: set[tuple[object, ...]] = set()
    result = []
    for source in sources:
        key = (
            source.label,
            source.url,
            source.path,
            source.line_start,
            source.line_end,
        )
        if key not in seen:
            seen.add(key)
            result.append(source)
    return tuple(result)
