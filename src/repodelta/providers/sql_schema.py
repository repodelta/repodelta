from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Literal, Protocol

from repodelta.model.contracts import (
    Diagnostic,
    SqlSchemaFileCoverage,
    SqlSchemaGap,
    SqlSchemaResult,
    SqlSchemaStatement,
)

_MAX_BYTES_PER_FILE = 2_000_000

_TOKEN = re.compile(
    r"""
    (?P<line_comment>--[^\n]*)
    |(?P<block_comment>/\*.*?\*/)
    |(?P<single_quoted>'(?:[^']|'')*')
    |(?P<double_quoted>"(?:[^"]|"")*")
    |(?P<dollar_quoted>\$(?P<tag>[A-Za-z_]*)\$.*?\$(?P=tag)\$)
    |(?P<terminator>;)
    """,
    re.VERBOSE | re.DOTALL,
)

_IDENTIFIER = r'"?[A-Za-z_][\w.]*"?'
_CREATE_TABLE_VERB = re.compile(r"^CREATE\s+TABLE\b", re.IGNORECASE)
_CREATE_TABLE = re.compile(
    rf"^CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<table>{_IDENTIFIER})\s*\(",
    re.IGNORECASE,
)
_ALTER_TABLE_VERB = re.compile(
    rf"^ALTER\s+TABLE\s+(?P<table>{_IDENTIFIER})\s+", re.IGNORECASE
)
_ADD_COLUMN_VERB = re.compile(r"\bADD\s+COLUMN\b", re.IGNORECASE)
_ADD_COLUMN = re.compile(
    rf"^ALTER\s+TABLE\s+(?P<table>{_IDENTIFIER})\s+"
    rf"ADD\s+COLUMN\s+(?P<column>{_IDENTIFIER})\s+\S",
    re.IGNORECASE,
)
_DROP_COLUMN_VERB = re.compile(r"\bDROP\s+COLUMN\b", re.IGNORECASE)
_DROP_COLUMN = re.compile(
    rf"^ALTER\s+TABLE\s+(?P<table>{_IDENTIFIER})\s+"
    rf"DROP\s+COLUMN\s+(?:IF\s+EXISTS\s+)?(?P<column>{_IDENTIFIER})\s*$",
    re.IGNORECASE,
)
_ALTER_COLUMN_VERB = re.compile(r"\bALTER\s+COLUMN\b", re.IGNORECASE)
_SET_NOT_NULL = re.compile(
    rf"^ALTER\s+TABLE\s+(?P<table>{_IDENTIFIER})\s+"
    rf"ALTER\s+COLUMN\s+(?P<column>{_IDENTIFIER})\s+SET\s+NOT\s+NULL\s*$",
    re.IGNORECASE,
)
_DROP_NOT_NULL = re.compile(
    rf"^ALTER\s+TABLE\s+(?P<table>{_IDENTIFIER})\s+"
    rf"ALTER\s+COLUMN\s+(?P<column>{_IDENTIFIER})\s+DROP\s+NOT\s+NULL\s*$",
    re.IGNORECASE,
)
_SET_NOT_NULL_VERB = re.compile(r"\bSET\s+NOT\s+NULL\b", re.IGNORECASE)
_DROP_NOT_NULL_VERB = re.compile(r"\bDROP\s+NOT\s+NULL\b", re.IGNORECASE)


def _identifier(raw: str) -> str:
    return raw.strip().strip('"')


def _split_statements(text: str) -> tuple[tuple[str, int, int], ...]:
    """Split on top-level ';' only, honoring quotes, comments, and $tag$ bodies.

    Comment text is dropped from the reconstructed statement (not just
    skipped while scanning for ';') so a leading '--' comment cannot hide a
    DDL keyword from the classifier.
    """

    statements: list[tuple[str, int, int]] = []
    pos = 0
    line = 1
    buffer: list[str] = []
    start_line: int | None = None

    def note(piece: str) -> None:
        nonlocal start_line
        if start_line is None and piece.strip():
            leading = piece[: len(piece) - len(piece.lstrip())]
            start_line = line + leading.count("\n")
        buffer.append(piece)

    def flush(end_line: int) -> None:
        nonlocal buffer, start_line
        chunk = "".join(buffer).strip()
        if chunk and start_line is not None:
            statements.append((chunk, start_line, end_line))
        buffer = []
        start_line = None

    for match in _TOKEN.finditer(text):
        segment = text[pos:match.start()]
        note(segment)
        line += segment.count("\n")

        token_text = match.group(0)
        if match.group("terminator"):
            flush(line)
            pos = match.end()
            continue
        if not match.group("line_comment") and not match.group("block_comment"):
            note(token_text)
        line += token_text.count("\n")
        pos = match.end()

    tail = text[pos:]
    note(tail)
    line += tail.count("\n")
    flush(line)
    return tuple(statements)


def _classify(
    revision_side: Literal["base", "head"],
    path: str,
    text: str,
    line_start: int,
    line_end: int,
) -> tuple[SqlSchemaStatement | None, SqlSchemaGap | None]:
    normalized = " ".join(text.split())
    if match := _CREATE_TABLE.match(text.strip()):
        return (
            SqlSchemaStatement(
                revision_side=revision_side,
                path=path,
                line_start=line_start,
                line_end=line_end,
                kind="create_table",
                table=_identifier(match.group("table")),
                normalized_text=normalized,
            ),
            None,
        )
    if _CREATE_TABLE_VERB.match(text.strip()):
        return None, SqlSchemaGap(
            line=line_start, reason="parse_failure", excerpt=normalized[:240]
        )
    if _ALTER_TABLE_VERB.match(text.strip()):
        if match := _SET_NOT_NULL.match(text.strip()):
            return (
                SqlSchemaStatement(
                    revision_side=revision_side,
                    path=path,
                    line_start=line_start,
                    line_end=line_end,
                    kind="alter_column_set_not_null",
                    table=_identifier(match.group("table")),
                    column=_identifier(match.group("column")),
                    nullable=False,
                    normalized_text=normalized,
                ),
                None,
            )
        if match := _DROP_NOT_NULL.match(text.strip()):
            return (
                SqlSchemaStatement(
                    revision_side=revision_side,
                    path=path,
                    line_start=line_start,
                    line_end=line_end,
                    kind="alter_column_drop_not_null",
                    table=_identifier(match.group("table")),
                    column=_identifier(match.group("column")),
                    nullable=True,
                    normalized_text=normalized,
                ),
                None,
            )
        if _ALTER_COLUMN_VERB.search(text) and (
            _SET_NOT_NULL_VERB.search(text) or _DROP_NOT_NULL_VERB.search(text)
        ):
            return None, SqlSchemaGap(
                line=line_start, reason="parse_failure", excerpt=normalized[:240]
            )
        if match := _ADD_COLUMN.match(text.strip()):
            return (
                SqlSchemaStatement(
                    revision_side=revision_side,
                    path=path,
                    line_start=line_start,
                    line_end=line_end,
                    kind="alter_table_add_column",
                    table=_identifier(match.group("table")),
                    column=_identifier(match.group("column")),
                    normalized_text=normalized,
                ),
                None,
            )
        if _ADD_COLUMN_VERB.search(text):
            return None, SqlSchemaGap(
                line=line_start, reason="parse_failure", excerpt=normalized[:240]
            )
        if match := _DROP_COLUMN.match(text.strip()):
            return (
                SqlSchemaStatement(
                    revision_side=revision_side,
                    path=path,
                    line_start=line_start,
                    line_end=line_end,
                    kind="alter_table_drop_column",
                    table=_identifier(match.group("table")),
                    column=_identifier(match.group("column")),
                    normalized_text=normalized,
                ),
                None,
            )
        if _DROP_COLUMN_VERB.search(text):
            return None, SqlSchemaGap(
                line=line_start, reason="parse_failure", excerpt=normalized[:240]
            )
        return None, SqlSchemaGap(
            line=line_start, reason="unsupported_statement", excerpt=normalized[:240]
        )
    return None, SqlSchemaGap(
        line=line_start, reason="unsupported_statement", excerpt=normalized[:240]
    )


def _observe_text(
    revision_side: Literal["base", "head"], path: str, text: str
) -> tuple[tuple[SqlSchemaStatement, ...], SqlSchemaFileCoverage]:
    statements: list[SqlSchemaStatement] = []
    gaps: list[SqlSchemaGap] = []
    for stmt_text, line_start, line_end in _split_statements(text):
        statement, gap = _classify(revision_side, path, stmt_text, line_start, line_end)
        if statement is not None:
            statements.append(statement)
        if gap is not None:
            gaps.append(gap)
    state: Literal["observed", "partial"] = "partial" if gaps else "observed"
    coverage = SqlSchemaFileCoverage(
        revision_side=revision_side,
        path=path,
        state=state,
        statement_count=len(statements),
        gaps=tuple(gaps),
    )
    return tuple(statements), coverage


class SqlSchemaProvider(Protocol):
    """Read-only DDL observation. Providers never fold statements into a schema."""

    def observe(
        self,
        *,
        head_paths: tuple[str, ...] = (),
        base_paths: tuple[str, ...] = (),
    ) -> SqlSchemaResult: ...


def unavailable_sql_schema_result(
    *,
    head_paths: tuple[str, ...] = (),
    base_paths: tuple[str, ...] = (),
    message: str = "No repository SQL schema provider was configured.",
) -> SqlSchemaResult:
    coverage = tuple(
        SqlSchemaFileCoverage(revision_side=side, path=path, state="unavailable")
        for side, paths in (("head", head_paths), ("base", base_paths))
        for path in paths
    )
    diagnostics = (
        (Diagnostic(code="sql_schema_provider_unavailable", message=message),)
        if coverage
        else ()
    )
    return SqlSchemaResult(coverage=coverage, diagnostics=diagnostics)


class RepositorySqlSchemaProvider:
    """Observe exact base/head checkouts without interpreting the DDL further."""

    def __init__(
        self,
        head_root: str | Path,
        *,
        expected_head_revision: str | None,
        base_root: str | Path | None = None,
        expected_base_revision: str | None = None,
    ) -> None:
        self.roots = {
            "head": Path(head_root).resolve(),
            "base": Path(base_root).resolve() if base_root else None,
        }
        self.expected_revisions = {
            "head": expected_head_revision or "",
            "base": expected_base_revision or "",
        }

    def observe(
        self,
        *,
        head_paths: tuple[str, ...] = (),
        base_paths: tuple[str, ...] = (),
    ) -> SqlSchemaResult:
        statements: list[SqlSchemaStatement] = []
        coverage: list[SqlSchemaFileCoverage] = []
        diagnostics: list[Diagnostic] = []
        for side, paths in (("head", head_paths), ("base", base_paths)):
            if not paths:
                continue
            side_statements, side_coverage, side_diagnostics = self._observe_side(
                side, paths
            )
            statements.extend(side_statements)
            coverage.extend(side_coverage)
            diagnostics.extend(side_diagnostics)
        result = SqlSchemaResult(
            statements=tuple(statements),
            coverage=tuple(coverage),
            diagnostics=tuple(diagnostics),
        )
        result.validate_consistency()
        return result

    def _observe_side(
        self, side: Literal["base", "head"], paths: tuple[str, ...]
    ) -> tuple[
        tuple[SqlSchemaStatement, ...],
        tuple[SqlSchemaFileCoverage, ...],
        tuple[Diagnostic, ...],
    ]:
        root = self.roots[side]
        if root is None:
            return (), self._unavailable_coverage(side, paths), (
                Diagnostic(
                    code="sql_schema_base_input_missing",
                    message=(
                        "Base SQL schema evidence is unavailable because no base "
                        "checkout was provided; removal is not inferred."
                    ),
                ),
            )
        revision = _checkout_revision(root)
        expected = self.expected_revisions[side]
        if not revision or (expected and revision != expected):
            return (), self._unavailable_coverage(side, paths), (
                Diagnostic(
                    code="sql_schema_stale_checkout",
                    message=(
                        f"SQL schema scanning requires {side} checkout "
                        f"{expected or '(unknown)'}; observed "
                        f"{revision or '(unavailable)'}."
                    ),
                ),
            )
        if not _tracked_checkout_clean(root):
            return (), self._unavailable_coverage(side, paths), (
                Diagnostic(
                    code="sql_schema_dirty_checkout",
                    message=(
                        f"SQL schema scanning requires tracked {side} checkout "
                        "content to match the reviewed revision exactly."
                    ),
                ),
            )
        statements: list[SqlSchemaStatement] = []
        coverage: list[SqlSchemaFileCoverage] = []
        diagnostics: list[Diagnostic] = []
        for path in paths:
            file_statements, file_coverage, file_diagnostic = self._observe_file(
                root, side, path
            )
            statements.extend(file_statements)
            coverage.append(file_coverage)
            if file_diagnostic is not None:
                diagnostics.append(file_diagnostic)
        return tuple(statements), tuple(coverage), tuple(diagnostics)

    def _observe_file(
        self, root: Path, side: Literal["base", "head"], path: str
    ) -> tuple[
        tuple[SqlSchemaStatement, ...], SqlSchemaFileCoverage, Diagnostic | None
    ]:
        target = root / path
        try:
            raw = target.read_bytes()
        except OSError:
            return (
                (),
                SqlSchemaFileCoverage(revision_side=side, path=path, state="unavailable"),
                Diagnostic(
                    code="sql_schema_file_unreadable",
                    message=f"{side} checkout is missing tracked file {path}.",
                ),
            )
        if len(raw) > _MAX_BYTES_PER_FILE:
            return (
                (),
                SqlSchemaFileCoverage(revision_side=side, path=path, state="unavailable"),
                Diagnostic(
                    code="sql_schema_file_too_large",
                    message=(
                        f"{path} exceeds the {_MAX_BYTES_PER_FILE}-byte scan limit; "
                        "no statements were observed."
                    ),
                ),
            )
        text = raw.decode("utf-8", errors="replace")
        statements, coverage = _observe_text(side, path, text)
        return statements, coverage, None

    @staticmethod
    def _unavailable_coverage(
        side: Literal["base", "head"], paths: tuple[str, ...]
    ) -> tuple[SqlSchemaFileCoverage, ...]:
        return tuple(
            SqlSchemaFileCoverage(revision_side=side, path=path, state="unavailable")
            for path in paths
        )


def _checkout_revision(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()


def _tracked_checkout_clean(root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
            check=True, capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return not result.stdout.strip()
