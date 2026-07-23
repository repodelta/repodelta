from __future__ import annotations

import hashlib
import sqlite3
import subprocess
from pathlib import Path

from .contracts import Diagnostic, SourceRef
from .diff_hunks import ChangedHunk
from .structural_graph import (
    GraphSymbol,
    HunkSymbolOverlap,
    StructuralGraphIndexStatus,
    StructuralGraphResult,
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


class CodegraphProvider:
    """Read a repository-local Codegraph SQLite index without mutating it."""

    def __init__(
        self,
        repo_root: str | Path,
        *,
        expected_revision: str | None = None,
    ):
        self.repo_root = Path(repo_root).resolve()
        self.database_path = self.repo_root / ".codegraph" / "codegraph.db"
        self.expected_revision = str(expected_revision or "").strip()

    def inspect_index(
        self, *, requested_files: tuple[str, ...] = ()
    ) -> StructuralGraphIndexStatus:
        requested = tuple(dict.fromkeys(_repo_path(path) for path in requested_files))
        requested = tuple(path for path in requested if path)
        if not self.database_path.is_file():
            return StructuralGraphIndexStatus(
                state="missing",
                provider=_PROVIDER,
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
                indexed_files = int(
                    connection.execute("SELECT COUNT(*) FROM files").fetchone()[0]
                )
                file_rows = _file_rows(connection, requested)
        except (OSError, sqlite3.Error) as exc:
            return StructuralGraphIndexStatus(
                state="error",
                provider=_PROVIDER,
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
                        "The target checkout is not at the analyzed PR head; "
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
            revision=checkout_revision,
            database_path=str(self.database_path),
            indexed_files=indexed_files,
            requested_files=len(requested),
            diagnostics=tuple(diagnostics),
        )

    def symbols_overlapping(
        self, hunks: tuple[ChangedHunk, ...]
    ) -> StructuralGraphResult:
        eligible_hunks = tuple(
            hunk for hunk in hunks if _is_structural_candidate(hunk.file_path)
        )
        skipped_files = tuple(
            dict.fromkeys(
                hunk.file_path
                for hunk in hunks
                if not _is_structural_candidate(hunk.file_path)
            )
        )
        requested_files = tuple(
            dict.fromkeys(hunk.file_path for hunk in eligible_hunks)
        )
        index = self.inspect_index(requested_files=requested_files)
        diagnostics = list(index.diagnostics)
        diagnostics.extend(
            Diagnostic(
                code="structural_graph_file_not_applicable",
                message=(
                    f"{path} is not a code-structure input and was excluded "
                    "from Codegraph coverage."
                ),
                severity="info",
                sources=(SourceRef(label="changed file", path=path),),
            )
            for path in skipped_files
        )
        if not index.usable:
            return StructuralGraphResult(
                index=index,
                hunk_count=len(eligible_hunks),
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
            for hunk in eligible_hunks
            if hunk.added_lines and hunk.file_path not in unindexed_files
        )
        for hunk in eligible_hunks:
            if hunk.file_path in unindexed_files:
                continue
            if hunk.is_deletion_only:
                diagnostics.append(
                    Diagnostic(
                        code="structural_graph_base_index_required",
                        message=(
                            f"{hunk.id} only removes lines; exact symbol mapping "
                            "requires a base-revision structural index."
                        ),
                        sources=(SourceRef(label="diff hunk", path=hunk.file_path),),
                    )
                )
            elif not hunk.added_lines:
                diagnostics.append(
                    Diagnostic(
                        code="structural_graph_hunk_has_no_changed_lines",
                        message=f"{hunk.id} has no new-file changed lines to map.",
                        sources=(SourceRef(label="diff hunk", path=hunk.file_path),),
                    )
                )
        if not queryable:
            return StructuralGraphResult(
                index=index,
                hunk_count=len(eligible_hunks),
                diagnostics=tuple(diagnostics),
            )

        overlaps: list[HunkSymbolOverlap] = []
        try:
            with self._connect() as connection:
                connection.row_factory = sqlite3.Row
                for hunk in queryable:
                    symbols = self._symbols_for_hunk(connection, hunk)
                    if not symbols:
                        diagnostics.append(
                            Diagnostic(
                                code="structural_graph_no_symbol_overlap",
                                message=(
                                    f"No indexed symbol span contains the changed "
                                    f"lines in {hunk.id}."
                                ),
                                sources=(
                                    SourceRef(label="diff hunk", path=hunk.file_path),
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
                                        path=hunk.file_path,
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
            index=index,
            hunk_count=len(eligible_hunks),
            overlaps=tuple(overlaps),
            diagnostics=tuple(diagnostics),
        )

    def _symbols_for_hunk(
        self, connection: sqlite3.Connection, hunk: ChangedHunk
    ) -> list[tuple[GraphSymbol, tuple[int, ...]]]:
        low, high = min(hunk.added_lines), max(hunk.added_lines)
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
            (hunk.file_path, *_SUPPORTED_KINDS, high, low),
        ).fetchall()
        symbols = [_symbol(row) for row in rows]
        selected: dict[str, tuple[GraphSymbol, set[int]]] = {}
        for line in hunk.added_lines:
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
