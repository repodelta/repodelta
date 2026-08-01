from __future__ import annotations

from dataclasses import dataclass

from prismcode.convergence.ordering import relation_key
from prismcode.model.structural_refs import (
    ordered_path_review_ids,
    path_review_ids,
    review_symbol_id,
)
from prismcode.model.contracts import (
    EvidenceItem,
    ProjectionDiagnostic,
    ProjectionRelation,
    ReviewRelevantStructuralClosure,
)


@dataclass(frozen=True)
class StructuralClosureSelection:
    selected: tuple[ProjectionRelation, ...]
    deferred: tuple[ProjectionRelation, ...]
    closure: ReviewRelevantStructuralClosure


def converge_structural_closure(
    *,
    paths: tuple[ProjectionRelation, ...],
    unreachable_paths: tuple[ProjectionRelation, ...],
    runtime: tuple[ProjectionRelation, ...],
    tests: tuple[ProjectionRelation, ...],
    evidence: dict[str, EvidenceItem],
    selected_anchor_ids: set[str],
    focus_id: str,
    max_paths_per_anchor: int,
    max_path_identities: int,
    max_runtime_context_identities: int,
    max_test_context_identities: int,
    diagnostics: list[ProjectionDiagnostic],
) -> StructuralClosureSelection:
    """Close changed backbone and terminal support with one minimal path union."""

    canonical_paths, duplicate_paths = _canonical_relations_by_target(paths)
    runtime_contexts, duplicate_runtime = _canonical_relations_by_target(runtime)
    test_contexts, duplicate_tests = _canonical_relations_by_target(tests)
    contexts = (*runtime_contexts, *test_contexts)
    direct_contexts = tuple(
        sorted(
            (item for item in contexts if not item.bridge_ids),
            key=relation_key,
        )
    )
    terminals = tuple(
        sorted(
            (item for item in contexts if item.bridge_ids),
            key=lambda item: (
                item.source_ordinal,
                0 if item.slot == "runtime_context" else 1,
                item.target_id,
            ),
        )
    )
    paths_by_target = {item.target_id: item for item in canonical_paths}
    selected_review_ids = {
        review_id
        for anchor_id in selected_anchor_ids
        if (review_id := review_symbol_id(evidence.get(anchor_id))) is not None
    }
    backbone_options: dict[
        tuple[str, str],
        list[tuple[str, ProjectionRelation]],
    ] = {}
    for path in canonical_paths:
        path_fact = evidence.get(path.target_id)
        if path_fact is None:
            continue
        sponsors = tuple(
            anchor_id
            for anchor_id in path.bridge_ids
            if anchor_id in selected_anchor_ids
        )
        if not sponsors:
            continue
        for connection in _changed_connections(
            path_fact,
            evidence,
            selected_review_ids,
        ):
            for sponsor in sponsors:
                backbone_options.setdefault(connection, []).append((sponsor, path))

    terminal_options: dict[
        str,
        list[tuple[str, ProjectionRelation]],
    ] = {}
    for terminal in terminals:
        for path_id in terminal.bridge_ids:
            path = paths_by_target.get(path_id)
            if path is None:
                continue
            for anchor_id in path.bridge_ids:
                if anchor_id in selected_anchor_ids:
                    terminal_options.setdefault(terminal.target_id, []).append(
                        (anchor_id, path)
                    )

    selected_paths: dict[str, ProjectionRelation] = {}
    selected_contexts: dict[str, ProjectionRelation] = {}
    selected_anchor_paths: set[tuple[str, str]] = set()
    sponsored = {anchor_id: 0 for anchor_id in selected_anchor_ids}
    context_counts = {"runtime_context": 0, "test_context": 0}
    context_limits = {
        "runtime_context": max_runtime_context_identities,
        "test_context": max_test_context_identities,
    }
    context_limit_omitted: dict[str, list[ProjectionRelation]] = {
        "runtime_context": [],
        "test_context": [],
    }

    for context in direct_contexts:
        if context_counts[context.slot] >= context_limits[context.slot]:
            context_limit_omitted[context.slot].append(context)
            continue
        selected_contexts[context.target_id] = context
        context_counts[context.slot] += 1

    def select_path(anchor_id: str, path: ProjectionRelation) -> bool:
        anchor_path = (anchor_id, path.target_id)
        if path.target_id in selected_paths:
            selected_anchor_paths.add(anchor_path)
            return True
        if anchor_path in selected_anchor_paths:
            return True
        if sponsored[anchor_id] >= max_paths_per_anchor:
            return False
        if len(selected_paths) >= max_path_identities:
            return False
        selected_paths[path.target_id] = path
        selected_anchor_paths.add(anchor_path)
        sponsored[anchor_id] += 1
        return True

    uncovered_backbone = []
    for connection in sorted(backbone_options):
        options = _canonical_options(
            backbone_options[connection],
            evidence,
            selected_paths,
        )
        if not any(select_path(anchor_id, path) for anchor_id, path in options):
            uncovered_backbone.append(connection)

    for terminal in terminals:
        if context_counts[terminal.slot] >= context_limits[terminal.slot]:
            context_limit_omitted[terminal.slot].append(terminal)
            continue
        options = _canonical_options(
            terminal_options.get(terminal.target_id, ()),
            evidence,
            selected_paths,
        )
        if any(select_path(anchor_id, path) for anchor_id, path in options):
            selected_contexts[terminal.target_id] = terminal
            context_counts[terminal.slot] += 1

    uncovered_terminals = tuple(
        terminal
        for terminal in terminals
        if terminal.target_id not in selected_contexts
        and terminal not in context_limit_omitted[terminal.slot]
        and terminal_options.get(terminal.target_id)
    )
    if uncovered_backbone or uncovered_terminals:
        diagnostics.append(
            ProjectionDiagnostic(
                focus_statement_id=focus_id,
                slot="structural_path",
                state="budget_truncated",
                message=(
                    f"Structural closure retained {len(selected_paths)} paths; "
                    f"{len(uncovered_backbone)} changed-backbone and "
                    f"{len(uncovered_terminals)} terminal obligations remain "
                    f"uncovered within per-anchor ({max_paths_per_anchor}) and "
                    f"total ({max_path_identities}) identity safety limits."
                ),
                affected_ids=(
                    *(
                        f"{source}->{target}"
                        for source, target in uncovered_backbone
                    ),
                    *(item.target_id for item in uncovered_terminals),
                ),
            )
        )
    for slot in ("runtime_context", "test_context"):
        omitted = context_limit_omitted[slot]
        if omitted:
            diagnostics.append(
                ProjectionDiagnostic(
                    focus_statement_id=focus_id,
                    slot=slot,
                    state="budget_truncated",
                    message=(
                        f"{sum(item.slot == slot for item in contexts)} canonical "
                        f"{slot.replace('_', ' ')} identities were reachable for "
                        f"{focus_id}; {context_counts[slot]} are retained within "
                        f"the {context_limits[slot]} identity safety limit."
                    ),
                    affected_ids=tuple(item.target_id for item in omitted),
                )
            )
    for slot, slot_contexts in (
        ("runtime_context", runtime_contexts),
        ("test_context", test_contexts),
    ):
        upstream_deferred = tuple(
            item
            for item in slot_contexts
            if item.target_id not in selected_contexts
            and item not in context_limit_omitted[slot]
            and item.target_id in terminal_options
        )
        if upstream_deferred:
            diagnostics.append(
                ProjectionDiagnostic(
                    focus_statement_id=focus_id,
                    slot=slot,
                    state="upstream_deferred",
                    message=(
                        f"{len(upstream_deferred)} canonical "
                        f"{slot.replace('_', ' ')} identities depend on "
                        "structural closure obligations deferred by a safety boundary."
                    ),
                    affected_ids=tuple(
                        item.target_id for item in upstream_deferred
                    ),
                )
            )

    selected = tuple(
        (
            *sorted(selected_paths.values(), key=relation_key),
            *(item for item in contexts if item.target_id in selected_contexts),
        )
    )
    selected_ids = {item.id for item in selected}
    deferred = tuple(
        item
        for item in (
            *canonical_paths,
            *duplicate_paths,
            *unreachable_paths,
            *runtime_contexts,
            *duplicate_runtime,
            *test_contexts,
            *duplicate_tests,
        )
        if item.id not in selected_ids
    )
    relevant_review_ids = set(selected_review_ids)
    relevant_review_ids.update(
        review_id
        for target_id in selected_contexts
        if (review_id := review_symbol_id(evidence.get(target_id))) is not None
    )
    for path in selected_paths.values():
        relevant_review_ids.update(
            path_review_ids(evidence.get(path.target_id), evidence)
        )
    relation_change_evidence_ids = tuple(
        item.id
        for item in evidence.values()
        if item.structural_relation_change is not None
        and item.structural_relation_change.source_review_symbol_id
        in relevant_review_ids
        and item.structural_relation_change.target_review_symbol_id
        in relevant_review_ids
    )
    return StructuralClosureSelection(
        selected=selected,
        deferred=deferred,
        closure=ReviewRelevantStructuralClosure(
            path_relation_ids=tuple(
                item.id for item in selected_paths.values()
            ),
            relation_change_evidence_ids=relation_change_evidence_ids,
        ),
    )


def _canonical_options(
    options: tuple[tuple[str, ProjectionRelation], ...]
    | list[tuple[str, ProjectionRelation]],
    evidence: dict[str, EvidenceItem],
    selected_paths: dict[str, ProjectionRelation],
) -> tuple[tuple[str, ProjectionRelation], ...]:
    return tuple(
        sorted(
            options,
            key=lambda item: (
                0 if item[1].target_id in selected_paths else 1,
                _path_depth(item[1], evidence),
                relation_key(item[1]),
                item[0],
            ),
        )
    )


def _changed_connections(
    path: EvidenceItem,
    evidence: dict[str, EvidenceItem],
    selected_review_ids: set[str],
) -> tuple[tuple[str, str], ...]:
    ordered = tuple(
        review_id
        for review_id in ordered_path_review_ids(path, evidence)
        if review_id in selected_review_ids
    )
    return tuple(
        dict.fromkeys(zip(ordered, ordered[1:], strict=False))
    )


def _path_depth(
    relation: ProjectionRelation,
    evidence: dict[str, EvidenceItem],
) -> int:
    return int(evidence[relation.target_id].metadata.get("depth", 0))


def _canonical_relations_by_target(
    relations: tuple[ProjectionRelation, ...],
) -> tuple[tuple[ProjectionRelation, ...], tuple[ProjectionRelation, ...]]:
    by_target: dict[str, list[ProjectionRelation]] = {}
    for relation in relations:
        by_target.setdefault(relation.target_id, []).append(relation)
    canonical = []
    duplicates = []
    for target_relations in by_target.values():
        ordered = tuple(sorted(target_relations, key=relation_key))
        canonical.append(ordered[0])
        duplicates.extend(ordered[1:])
    return tuple(canonical), tuple(sorted(duplicates, key=relation_key))
