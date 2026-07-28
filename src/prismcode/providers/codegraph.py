from __future__ import annotations

import hashlib
import sqlite3
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from prismcode.model.contracts import Diagnostic, SourceRef
from prismcode.changes.hunks import ChangedHunk
from prismcode.providers.structural import (
    GraphPathStep,
    GraphSymbol,
    HunkSymbolOverlap,
    OwnershipLimit,
    StructuralGraphIndexStatus,
    StructuralGraphResult,
    StructuralOwnershipCoverage,
    StructuralOwnershipPolicy,
    StructuralOwnershipRelation,
    StructuralRevision,
    StructuralPath,
    StructuralSeedCoverage,
    StructuralTraversalPolicy,
    TraversalLimit,
)

_PROVIDER = "codegraph"
_SUPPORTED_KINDS = (
    "file",
    "function",
    "method",
    "class",
    "route",
    "variable",
    "constant",
)
_NON_STRUCTURAL_SUFFIXES = {
    ".md",
    ".mdx",
    ".rst",
    ".txt",
    ".pdf",
    ".doc",
    ".docx",
}
_REQUIRED_COLUMNS = {
    "nodes": {
        "id",
        "kind",
        "name",
        "qualified_name",
        "file_path",
        "language",
        "start_line",
        "end_line",
    },
    "edges": {"source", "target", "kind"},
    "files": {"path", "content_hash"},
}


@dataclass
class _SeedTraversal:
    seed: GraphSymbol
    queue: list[
        tuple[GraphSymbol, tuple[GraphPathStep, ...], frozenset[str]]
    ]
    discovered: set[str]
    paths: list[StructuralPath] = field(default_factory=list)
    limiting_dimensions: set[TraversalLimit] = field(default_factory=set)
    cursor: int = 0
    current: (
        tuple[GraphSymbol, tuple[GraphPathStep, ...], frozenset[str]] | None
    ) = None
    neighbors: tuple[GraphPathStep, ...] = ()
    neighbor_cursor: int = 0
    exhausted: bool = False


class CodegraphProvider:
    """Read a repository-local Codegraph SQLite index without mutating it."""

    def __init__(
        self,
        repo_root: str | Path,
        *,
        expected_revision: str | None = None,
        revision_side: StructuralRevision = "head",
    ):
        self.repo_root = Path(repo_root).resolve()
        self.database_path = self.repo_root / ".codegraph" / "codegraph.db"
        self.expected_revision = str(expected_revision or "").strip()
        self.revision_side = revision_side

    def inspect_index(
        self, *, requested_files: tuple[str, ...] = ()
    ) -> StructuralGraphIndexStatus:
        requested = tuple(dict.fromkeys(_repo_path(path) for path in requested_files))
        requested = tuple(path for path in requested if path)
        if not self.database_path.is_file():
            return StructuralGraphIndexStatus(
                state="missing",
                provider=_PROVIDER,
                revision_side=self.revision_side,
                database_path=str(self.database_path),
                requested_files=len(requested),
                diagnostics=(
                    Diagnostic(
                        code="codegraph_index_missing",
                        message=(
                            "No repository-local .codegraph/codegraph.db was found; "
                            "structural mapping is unavailable."
                        ),
                    ),
                ),
            )
        try:
            with self._connect() as connection:
                schema_error = _schema_error(connection)
                if schema_error:
                    return StructuralGraphIndexStatus(
                        state="invalid",
                        provider=_PROVIDER,
                        revision_side=self.revision_side,
                        database_path=str(self.database_path),
                        requested_files=len(requested),
                        diagnostics=(
                            Diagnostic(
                                code="codegraph_schema_invalid",
                                message=schema_error,
                                severity="error",
                            ),
                        ),
                    )
                file_rows = _file_rows(connection, requested)
        except (OSError, sqlite3.Error) as exc:
            return StructuralGraphIndexStatus(
                state="error",
                provider=_PROVIDER,
                revision_side=self.revision_side,
                database_path=str(self.database_path),
                requested_files=len(requested),
                diagnostics=(
                    Diagnostic(
                        code="codegraph_index_unreadable",
                        message=f"Codegraph index could not be read: {type(exc).__name__}.",
                        severity="error",
                    ),
                ),
            )

        diagnostics: list[Diagnostic] = []
        checkout_revision = _checkout_revision(self.repo_root)
        revision_mismatch = bool(
            self.expected_revision
            and checkout_revision != self.expected_revision
        )
        if revision_mismatch:
            diagnostics.append(
                Diagnostic(
                    code="codegraph_checkout_revision_mismatch",
                    message=(
                        f"The {self.revision_side} checkout is not at the "
                        f"analyzed PR {self.revision_side}; "
                        "its structural index was not used."
                    ),
                    severity="error",
                )
            )
        missing = [path for path in requested if path not in file_rows]
        stale: list[str] = []
        for path, expected_hash in file_rows.items():
            local_path = self.repo_root / path
            if local_path.is_file() and _sha256(local_path) != expected_hash:
                stale.append(path)
        for path in missing:
            diagnostics.append(
                Diagnostic(
                    code="codegraph_file_not_indexed",
                    message=f"{path} is not present in the Codegraph index.",
                    sources=(SourceRef(label="changed file", path=path),),
                )
            )
        for path in stale:
            diagnostics.append(
                Diagnostic(
                    code="codegraph_index_stale",
                    message=f"Codegraph content hash does not match the current {path}.",
                    sources=(SourceRef(label="changed file", path=path),),
                )
            )

        if revision_mismatch or stale:
            state = "stale"
        elif missing:
            state = "partial" if len(missing) < len(requested) else "missing"
        else:
            state = "available"
        return StructuralGraphIndexStatus(
            state=state,
            provider=_PROVIDER,
            revision_side=self.revision_side,
            revision=checkout_revision,
            database_path=str(self.database_path),
            indexed_files=len(file_rows),
            requested_files=len(requested),
            diagnostics=tuple(diagnostics),
        )

    def symbols_overlapping(
        self, hunks: tuple[ChangedHunk, ...]
    ) -> StructuralGraphResult:
        revision_paths = {
            hunk.id: (
                hunk.head_path
                if self.revision_side == "head"
                else hunk.base_path
            )
            for hunk in hunks
        }
        structural_hunks = tuple(
            hunk
            for hunk in hunks
            if revision_paths[hunk.id]
            and _is_structural_candidate(revision_paths[hunk.id] or "")
        )
        applicable_hunks = tuple(
            hunk for hunk in structural_hunks if self._changed_lines(hunk)
        )
        applicable_files = frozenset(
            hunk.path_for_revision(self.revision_side)
            for hunk in applicable_hunks
        )
        non_structural_files = tuple(
            dict.fromkeys(
                revision_paths[hunk.id]
                for hunk in hunks
                if revision_paths[hunk.id]
                and not _is_structural_candidate(revision_paths[hunk.id] or "")
            )
        )
        revision_inapplicable_files = tuple(
            dict.fromkeys(
                hunk.path_for_revision(self.revision_side)
                for hunk in structural_hunks
                if hunk.path_for_revision(self.revision_side)
                not in applicable_files
            )
        )
        requested_files = tuple(
            dict.fromkeys(
                hunk.path_for_revision(self.revision_side)
                for hunk in applicable_hunks
            )
        )
        provenance_diagnostics = (
            *(
                Diagnostic(
                    code="structural_graph_file_not_applicable",
                    message=(
                        f"{path} is not a code-structure input and was excluded "
                        "from Codegraph coverage."
                    ),
                    severity="info",
                    sources=(SourceRef(label="changed file", path=path),),
                )
                for path in non_structural_files
            ),
            *(
                Diagnostic(
                    code="structural_graph_revision_not_applicable",
                    message=(
                        f"{path} has no {self.revision_side}-revision changed "
                        "lines and was excluded from that revision's Codegraph "
                        "coverage."
                    ),
                    severity="info",
                    sources=(SourceRef(label="changed file", path=path),),
                )
                for path in revision_inapplicable_files
            ),
        )
        if not applicable_hunks:
            return StructuralGraphResult(
                revision_side=self.revision_side,
                index=StructuralGraphIndexStatus(
                    state="available",
                    provider=_PROVIDER,
                    revision_side=self.revision_side,
                    revision=_checkout_revision(self.repo_root),
                    database_path=str(self.database_path),
                ),
                diagnostics=provenance_diagnostics,
            )

        index = self.inspect_index(requested_files=requested_files)
        diagnostics = [*index.diagnostics, *provenance_diagnostics]
        if not index.usable:
            return StructuralGraphResult(
                revision_side=self.revision_side,
                index=index,
                hunk_count=len(applicable_hunks),
                diagnostics=tuple(diagnostics),
            )

        unindexed_files = {
            source.path
            for diagnostic in index.diagnostics
            if diagnostic.code == "codegraph_file_not_indexed"
            for source in diagnostic.sources
            if source.path
        }
        queryable = tuple(
            hunk
            for hunk in applicable_hunks
            if hunk.path_for_revision(self.revision_side)
            not in unindexed_files
        )
        if not queryable:
            return StructuralGraphResult(
                revision_side=self.revision_side,
                index=index,
                hunk_count=len(applicable_hunks),
                diagnostics=tuple(diagnostics),
            )

        overlaps: list[HunkSymbolOverlap] = []
        try:
            with self._connect() as connection:
                connection.row_factory = sqlite3.Row
                for hunk in queryable:
                    symbols = self._symbols_for_hunk(
                        connection,
                        hunk,
                        self._changed_lines(hunk),
                    )
                    if not symbols:
                        diagnostics.append(
                            Diagnostic(
                                code="structural_graph_no_symbol_overlap",
                                message=(
                                    f"No indexed symbol span contains the changed "
                                    f"lines in {hunk.id}."
                                ),
                                sources=(
                                    SourceRef(
                                        label="diff hunk",
                                        path=hunk.path_for_revision(
                                            self.revision_side
                                        ),
                                    ),
                                ),
                            )
                        )
                        continue
                    for symbol, lines in symbols:
                        overlaps.append(
                            HunkSymbolOverlap(
                                hunk_id=hunk.id,
                                symbol=symbol,
                                changed_lines=lines,
                                sources=(
                                    SourceRef(
                                        label="diff hunk",
                                        path=hunk.path_for_revision(
                                            self.revision_side
                                        ),
                                        line_start=min(lines),
                                        line_end=max(lines),
                                    ),
                                    *symbol.sources,
                                ),
                            )
                        )
        except sqlite3.Error as exc:
            diagnostics.append(
                Diagnostic(
                    code="codegraph_query_failed",
                    message=f"Codegraph symbol query failed: {type(exc).__name__}.",
                    severity="error",
                )
            )
        return StructuralGraphResult(
            revision_side=self.revision_side,
            index=index,
            hunk_count=len(applicable_hunks),
            overlaps=tuple(overlaps),
            diagnostics=tuple(diagnostics),
        )

    def expand_structure(
        self,
        result: StructuralGraphResult,
        *,
        policy: StructuralTraversalPolicy = StructuralTraversalPolicy(),
        ownership_policy: StructuralOwnershipPolicy = StructuralOwnershipPolicy(),
    ) -> StructuralGraphResult:
        """Expand executable paths and collect separate structural ownership."""

        if not result.index.usable or not result.overlaps:
            return result
        if any(
            value < 1
            for value in (
                policy.max_depth,
                policy.max_nodes_per_seed,
                policy.max_paths_per_seed,
                policy.max_total_nodes,
                policy.max_total_paths,
            )
        ):
            return result

        seed_symbols = {
            overlap.symbol.id: overlap.symbol for overlap in result.overlaps
        }
        paths: list[StructuralPath] = []
        ownership_relations: tuple[StructuralOwnershipRelation, ...] = ()
        ownership_coverage: StructuralOwnershipCoverage | None = None
        ordered_seeds = tuple(
            sorted(seed_symbols.values(), key=lambda item: item.qualified_name)
        )
        traversals = [
            _SeedTraversal(
                seed=seed,
                queue=[(seed, (), frozenset({seed.id}))],
                discovered={seed.id},
            )
            for seed in ordered_seeds
        ]
        global_discovered = set(seed_symbols)
        query_phase = "path"
        try:
            with self._connect() as connection:
                connection.row_factory = sqlite3.Row
                review_budget_reached = False
                for depth in range(1, policy.max_depth + 1):
                    phase_active = True
                    while phase_active:
                        phase_active = False
                        for traversal in traversals:
                            if traversal.exhausted:
                                continue
                            if len(paths) >= policy.max_total_paths:
                                review_budget_reached = True
                                break
                            path = self._advance_seed(
                                connection,
                                traversal,
                                target_depth=depth,
                                policy=policy,
                                global_discovered=global_discovered,
                            )
                            if path is not None:
                                paths.append(path)
                                phase_active = True
                        if review_budget_reached:
                            break
                    if review_budget_reached:
                        for traversal in traversals:
                            if not traversal.exhausted:
                                traversal.limiting_dimensions.add(
                                    "review_path_budget"
                                )
                                traversal.exhausted = True
                        break
                observed_symbols = {
                    symbol.id: symbol
                    for path in paths
                    for symbol in (
                        seed_symbols[path.seed_symbol_id],
                        *(step.target for step in path.steps),
                    )
                }
                observed_symbols.update(seed_symbols)
                query_phase = "ownership"
                ownership_relations, ownership_limits = (
                    self._collect_ownership_relations(
                        connection,
                        tuple(observed_symbols.values()),
                        policy=ownership_policy,
                    )
                )
                ownership_coverage = StructuralOwnershipCoverage(
                    state="truncated" if ownership_limits else "complete",
                    observed_symbol_ids=tuple(sorted(observed_symbols)),
                    relation_count=len(ownership_relations),
                    limiting_dimensions=ownership_limits,
                )
        except sqlite3.Error as exc:
            if query_phase == "ownership":
                ownership_coverage = StructuralOwnershipCoverage(
                    state="unavailable",
                    observed_symbol_ids=tuple(sorted(seed_symbols)),
                    relation_count=0,
                )
            return StructuralGraphResult(
                revision_side=self.revision_side,
                index=result.index,
                hunk_count=result.hunk_count,
                overlaps=result.overlaps,
                paths=tuple(paths),
                ownership_relations=ownership_relations,
                ownership_coverage=ownership_coverage,
                traversal_coverage=_seed_coverage(traversals),
                diagnostics=(
                    *result.diagnostics,
                    Diagnostic(
                        code=(
                            "codegraph_ownership_query_failed"
                            if query_phase == "ownership"
                            else "codegraph_path_query_failed"
                        ),
                        message=(
                            f"Codegraph {query_phase} query failed: "
                            f"{type(exc).__name__}."
                        ),
                        severity="error",
                    ),
                ),
            )

        coverage = _seed_coverage(traversals)
        diagnostics = list(result.diagnostics)
        if (
            ownership_coverage is not None
            and ownership_coverage.state == "truncated"
        ):
            diagnostics.append(
                Diagnostic(
                    code="structural_graph_ownership_truncated",
                    message=(
                        "Structural ownership ancestry reached its deterministic "
                        "safety boundary "
                        f"({ownership_policy.max_depth} levels, "
                        f"{ownership_policy.max_relations} relations; "
                        f"limited by {' and '.join(ownership_coverage.limiting_dimensions)})."
                    ),
                    severity="info",
                )
            )
        for item in coverage:
            if item.state != "truncated":
                continue
            diagnostics.append(
                Diagnostic(
                    code="structural_graph_seed_traversal_truncated",
                    message=(
                        f"Structural traversal for seed {item.seed_symbol_id} "
                        "reached its deterministic "
                        f"{' and '.join(value.replace('_', ' ') for value in item.limiting_dimensions)} "
                        "boundary "
                        f"({item.node_count} nodes, {item.path_count} paths, "
                        f"{policy.max_depth} hops)."
                    ),
                    severity="info",
                    sources=item.sources,
                )
            )
        return StructuralGraphResult(
            revision_side=self.revision_side,
            index=result.index,
            hunk_count=result.hunk_count,
            overlaps=result.overlaps,
            paths=tuple(paths),
            ownership_relations=ownership_relations,
            ownership_coverage=ownership_coverage,
            traversal_coverage=tuple(coverage),
            diagnostics=tuple(diagnostics),
        )

    def _collect_ownership_relations(
        self,
        connection: sqlite3.Connection,
        symbols: tuple[GraphSymbol, ...],
        *,
        policy: StructuralOwnershipPolicy,
    ) -> tuple[
        tuple[StructuralOwnershipRelation, ...],
        tuple[OwnershipLimit, ...],
    ]:
        """Collect bounded `contains` ancestry without creating runtime paths."""

        if policy.max_depth < 1 or policy.max_relations < 1 or not symbols:
            return (), ()
        known = {symbol.id: symbol for symbol in symbols}
        frontier = set(known)
        visited = set(frontier)
        relations: dict[tuple[str, str], StructuralOwnershipRelation] = {}
        for _depth in range(policy.max_depth):
            level = self._ownership_parents(connection, tuple(sorted(frontier)))
            next_frontier: set[str] = set()
            for parent, child in level:
                known[parent.id] = parent
                known[child.id] = child
                if _creates_ownership_cycle(
                    relations,
                    parent_id=parent.id,
                    child_id=child.id,
                ):
                    continue
                if (
                    (parent.id, child.id) not in relations
                    and len(relations) >= policy.max_relations
                ):
                    return (
                        _ordered_ownership_relations(relations),
                        ("relation_budget",),
                    )
                relations[(parent.id, child.id)] = StructuralOwnershipRelation(
                    parent=parent,
                    child=child,
                    sources=(*parent.sources, *child.sources),
                )
                if parent.id not in visited:
                    visited.add(parent.id)
                    next_frontier.add(parent.id)
            if not next_frontier:
                return _ordered_ownership_relations(relations), ()
            frontier = next_frontier
        has_unseen_parent = any(
            parent.id not in known
            for parent, _child in self._ownership_parents(
                connection,
                tuple(sorted(frontier)),
            )
        )
        return (
            _ordered_ownership_relations(relations),
            ("depth_budget",) if has_unseen_parent else (),
        )

    def _ownership_parents(
        self,
        connection: sqlite3.Connection,
        child_ids: tuple[str, ...],
    ) -> tuple[tuple[GraphSymbol, GraphSymbol], ...]:
        if not child_ids:
            return ()
        placeholders = ",".join("?" for _ in child_ids)
        rows = connection.execute(
            f"""
            SELECT
                p.id AS parent_id, p.kind AS parent_kind, p.name AS parent_name,
                p.qualified_name AS parent_qualified_name,
                p.file_path AS parent_file_path, p.language AS parent_language,
                p.start_line AS parent_start_line, p.end_line AS parent_end_line,
                c.id AS child_id, c.kind AS child_kind, c.name AS child_name,
                c.qualified_name AS child_qualified_name,
                c.file_path AS child_file_path, c.language AS child_language,
                c.start_line AS child_start_line, c.end_line AS child_end_line
            FROM edges e
            JOIN nodes p ON p.id = e.source
            JOIN nodes c ON c.id = e.target
            WHERE e.kind = 'contains' AND e.target IN ({placeholders})
            ORDER BY p.qualified_name, c.qualified_name
            """,
            child_ids,
        ).fetchall()
        return tuple(
            (
                _prefixed_symbol(row, "parent"),
                _prefixed_symbol(row, "child"),
            )
            for row in rows
        )

    def _advance_seed(
        self,
        connection: sqlite3.Connection,
        traversal: _SeedTraversal,
        *,
        target_depth: int,
        policy: StructuralTraversalPolicy,
        global_discovered: set[str],
    ) -> StructuralPath | None:
        """Emit one path at the requested depth or finish that depth phase."""

        while not traversal.exhausted:
            if traversal.current is None:
                if traversal.cursor >= len(traversal.queue):
                    traversal.exhausted = True
                    return None
                candidate = traversal.queue[traversal.cursor]
                _current, candidate_steps, _visited = candidate
                if len(candidate_steps) >= target_depth:
                    return None
                traversal.current = candidate
                traversal.cursor += 1
                current, steps, _visited = traversal.current
                traversal.neighbors = self._neighbor_steps(
                    connection,
                    current,
                    policy.relation_allowlist,
                )
                traversal.neighbor_cursor = 0

            current, steps, visited = traversal.current
            if traversal.neighbor_cursor >= len(traversal.neighbors):
                traversal.current = None
                continue
            step = traversal.neighbors[traversal.neighbor_cursor]
            traversal.neighbor_cursor += 1
            if step.target.id in visited:
                continue
            if len(traversal.paths) >= policy.max_paths_per_seed:
                traversal.limiting_dimensions.add("seed_path_budget")
                traversal.exhausted = True
                return None
            if (
                step.target.id not in traversal.discovered
                and len(traversal.discovered) >= policy.max_nodes_per_seed
            ):
                traversal.limiting_dimensions.add("seed_node_budget")
                continue
            if (
                step.target.id not in global_discovered
                and len(global_discovered) >= policy.max_total_nodes
            ):
                traversal.limiting_dimensions.add("review_node_budget")
                continue
            traversal.discovered.add(step.target.id)
            global_discovered.add(step.target.id)
            next_steps = (*steps, step)
            path_symbols = (
                traversal.seed,
                *(item.target for item in next_steps),
            )
            path = StructuralPath(
                seed_symbol_id=traversal.seed.id,
                steps=next_steps,
                classification=_classify_path(path_symbols),
                sources=tuple(
                    source
                    for symbol in path_symbols
                    for source in symbol.sources
                ),
            )
            traversal.paths.append(path)
            traversal.queue.append(
                (
                    step.target,
                    next_steps,
                    visited | {step.target.id},
                )
            )
            return path
        return None

    def _neighbor_steps(
        self,
        connection: sqlite3.Connection,
        symbol: GraphSymbol,
        relation_allowlist: tuple[str, ...],
    ) -> tuple[GraphPathStep, ...]:
        relations = tuple(dict.fromkeys(relation_allowlist))
        if not relations:
            return ()
        placeholders = ",".join("?" for _ in relations)
        rows = connection.execute(
            f"""
            SELECT e.source, e.target, e.kind,
                   s.id AS source_id, s.kind AS source_kind, s.name AS source_name,
                   s.qualified_name AS source_qualified_name,
                   s.file_path AS source_file_path, s.language AS source_language,
                   s.start_line AS source_start_line, s.end_line AS source_end_line,
                   t.id AS target_id, t.kind AS target_kind, t.name AS target_name,
                   t.qualified_name AS target_qualified_name,
                   t.file_path AS target_file_path, t.language AS target_language,
                   t.start_line AS target_start_line, t.end_line AS target_end_line
            FROM edges e
            JOIN nodes s ON s.id = e.source
            JOIN nodes t ON t.id = e.target
            WHERE e.kind IN ({placeholders})
              AND (e.source = ? OR e.target = ?)
            ORDER BY e.kind, s.qualified_name, t.qualified_name
            """,
            (*relations, symbol.id, symbol.id),
        ).fetchall()
        steps: list[GraphPathStep] = []
        for row in rows:
            outgoing = str(row["source"]) == symbol.id
            neighbor = _prefixed_symbol(row, "target" if outgoing else "source")
            steps.append(
                GraphPathStep(
                    source=symbol,
                    target=neighbor,
                    relation=str(row["kind"]),
                    direction="outgoing" if outgoing else "incoming",
                )
            )
        return tuple(steps)

    def _symbols_for_hunk(
        self,
        connection: sqlite3.Connection,
        hunk: ChangedHunk,
        changed_lines: tuple[int, ...],
    ) -> list[tuple[GraphSymbol, tuple[int, ...]]]:
        low, high = min(changed_lines), max(changed_lines)
        placeholders = ",".join("?" for _ in _SUPPORTED_KINDS)
        rows = connection.execute(
            f"""
            SELECT id, kind, name, qualified_name, file_path, language,
                   start_line, end_line
            FROM nodes
            WHERE file_path = ?
              AND kind IN ({placeholders})
              AND start_line <= ?
              AND end_line >= ?
            ORDER BY start_line, end_line, qualified_name
            """,
            (
                hunk.path_for_revision(self.revision_side),
                *_SUPPORTED_KINDS,
                high,
                low,
            ),
        ).fetchall()
        symbols = [_symbol(row) for row in rows]
        selected: dict[str, tuple[GraphSymbol, set[int]]] = {}
        for line in changed_lines:
            containing = [
                symbol
                for symbol in symbols
                if symbol.start_line <= line <= symbol.end_line
            ]
            if not containing:
                continue
            narrowest_span = min(
                symbol.end_line - symbol.start_line for symbol in containing
            )
            narrowest = [
                symbol
                for symbol in containing
                if symbol.end_line - symbol.start_line == narrowest_span
            ]
            for symbol in narrowest:
                selected.setdefault(symbol.id, (symbol, set()))[1].add(line)
        return [
            (symbol, tuple(sorted(lines)))
            for symbol, lines in selected.values()
        ]

    def _changed_lines(self, hunk: ChangedHunk) -> tuple[int, ...]:
        return (
            hunk.added_lines
            if self.revision_side == "head"
            else hunk.removed_lines
        )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path.as_uri() + "?mode=ro", uri=True)


def _symbol(row: sqlite3.Row) -> GraphSymbol:
    file_path = str(row["file_path"])
    start_line = int(row["start_line"])
    end_line = int(row["end_line"])
    return GraphSymbol(
        id=str(row["id"]),
        kind=str(row["kind"]),
        name=str(row["name"]),
        qualified_name=str(row["qualified_name"]),
        file_path=file_path,
        language=str(row["language"]),
        start_line=start_line,
        end_line=end_line,
        sources=(
            SourceRef(
                label="Codegraph symbol",
                path=file_path,
                line_start=start_line,
                line_end=end_line,
            ),
        ),
    )


def _prefixed_symbol(row: sqlite3.Row, prefix: str) -> GraphSymbol:
    file_path = str(row[f"{prefix}_file_path"])
    start_line = int(row[f"{prefix}_start_line"])
    end_line = int(row[f"{prefix}_end_line"])
    return GraphSymbol(
        id=str(row[f"{prefix}_id"]),
        kind=str(row[f"{prefix}_kind"]),
        name=str(row[f"{prefix}_name"]),
        qualified_name=str(row[f"{prefix}_qualified_name"]),
        file_path=file_path,
        language=str(row[f"{prefix}_language"]),
        start_line=start_line,
        end_line=end_line,
        sources=(
            SourceRef(
                label="Codegraph symbol",
                path=file_path,
                line_start=start_line,
                line_end=end_line,
            ),
        ),
    )


def _is_test_path(path: str) -> bool:
    normalized = path.casefold().replace("\\", "/")
    name = Path(normalized).name
    return (
        normalized.startswith(("test/", "tests/"))
        or "/test/" in normalized
        or "/tests/" in normalized
        or name.startswith("test_")
        or name.endswith(("_test.py", ".test.js", ".test.ts", ".spec.js", ".spec.ts"))
    )


def _classify_path(symbols: tuple[GraphSymbol, ...]) -> str:
    kinds = {_is_test_path(symbol.file_path) for symbol in symbols}
    if kinds == {True}:
        return "test"
    if kinds == {False}:
        return "runtime"
    return "mixed"


def _seed_coverage(
    traversals: list[_SeedTraversal],
) -> tuple[StructuralSeedCoverage, ...]:
    order: tuple[TraversalLimit, ...] = (
        "seed_node_budget",
        "seed_path_budget",
        "review_node_budget",
        "review_path_budget",
    )
    return tuple(
        StructuralSeedCoverage(
            seed_symbol_id=item.seed.id,
            state="truncated" if item.limiting_dimensions else "complete",
            node_count=len(item.discovered),
            path_count=len(item.paths),
            limiting_dimensions=tuple(
                limit for limit in order if limit in item.limiting_dimensions
            ),
            sources=item.seed.sources,
        )
        for item in traversals
    )


def _ordered_ownership_relations(
    relations: dict[tuple[str, str], StructuralOwnershipRelation],
) -> tuple[StructuralOwnershipRelation, ...]:
    return tuple(
        sorted(
            relations.values(),
            key=lambda item: (
                item.parent.qualified_name,
                item.child.qualified_name,
                item.parent.id,
                item.child.id,
            ),
        )
    )


def _creates_ownership_cycle(
    relations: dict[tuple[str, str], StructuralOwnershipRelation],
    *,
    parent_id: str,
    child_id: str,
) -> bool:
    if parent_id == child_id:
        return True
    descendants: dict[str, set[str]] = {}
    for source_id, target_id in relations:
        descendants.setdefault(source_id, set()).add(target_id)
    frontier = [child_id]
    visited: set[str] = set()
    while frontier:
        current = frontier.pop()
        if current == parent_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        frontier.extend(descendants.get(current, ()))
    return False


def _schema_error(connection: sqlite3.Connection) -> str:
    tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    missing_tables = set(_REQUIRED_COLUMNS) - tables
    if missing_tables:
        return f"Codegraph index is missing tables: {sorted(missing_tables)}."
    for table, required in _REQUIRED_COLUMNS.items():
        present = {
            str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")
        }
        missing = required - present
        if missing:
            return f"Codegraph table {table} is missing columns: {sorted(missing)}."
    return ""


def _file_rows(
    connection: sqlite3.Connection, requested: tuple[str, ...]
) -> dict[str, str]:
    if not requested:
        return {}
    placeholders = ",".join("?" for _ in requested)
    return {
        str(row[0]): str(row[1])
        for row in connection.execute(
            f"SELECT path, content_hash FROM files WHERE path IN ({placeholders})",
            requested,
        )
    }


def _repo_path(path: str) -> str:
    normalized = str(path or "").strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized or normalized.startswith("/") or ".." in normalized.split("/"):
        return ""
    return normalized


def _is_structural_candidate(path: str) -> bool:
    return Path(path).suffix.casefold() not in _NON_STRUCTURAL_SUFFIXES


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checkout_revision(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""
