from __future__ import annotations

import ast
from pathlib import Path
from typing import Literal

from repodelta.model.contracts import (
    Diagnostic,
    FileSelector,
    ProviderDescriptor,
    ProviderFact,
    ProviderFileCoverage,
    ProviderGap,
    ProviderObservation,
    column_subject,
    table_subject,
)
from repodelta.providers.checkout import (
    checkout_revision,
    is_symlinked,
    tracked_checkout_clean,
)

ALEMBIC_MIGRATION_PROVIDER = "alembic-migration"

_MAX_BYTES_PER_FILE = 2_000_000

# The op.* calls whose schema effect this provider can state. Only the body of a
# module-level ``upgrade()`` is examined; ``downgrade()`` is outside the
# declaration, so a downgrade cannot contradict or corroborate an upgrade fact.
_CAPABILITIES = (
    "op.add_column",
    "op.alter_column.nullable",
    "op.create_table",
    "op.drop_column",
)

# Column keywords that carry no semantics beyond what a fact states. Any other
# keyword (server_default, primary_key, unique, ...) is recognized-but-unaccounted.
_BENIGN_COLUMN_KEYWORDS = frozenset({"comment", "doc"})
# alter_column hints that describe the current column and do not change it.
_ALTER_HINT_KEYWORDS = frozenset(
    {"existing_type", "existing_nullable", "existing_server_default", "existing_comment"}
)

Side = Literal["base", "head"]


class _Body:
    """Facts and gaps of one migration file, kept in source order."""

    def __init__(self, side: Side, path: str) -> None:
        self.side = side
        self.path = path
        self.facts: list[ProviderFact] = []
        self.gaps: list[ProviderGap] = []

    def fact(
        self,
        node: ast.AST,
        capability: str,
        subject: str,
        attribute: str,
        value: str,
    ) -> None:
        self.facts.append(
            ProviderFact(
                provider=ALEMBIC_MIGRATION_PROVIDER,
                capability=capability,
                subject=subject,
                attribute=attribute,
                value=value,
                revision_side=self.side,
                path=self.path,
                line_start=node.lineno,  # type: ignore[attr-defined]
                line_end=getattr(node, "end_lineno", None) or node.lineno,  # type: ignore[attr-defined]
            )
        )

    def gap(self, node: ast.AST, reason: str) -> None:
        excerpt = " ".join(ast.unparse(node).split())[:240]
        self.gaps.append(
            ProviderGap(line=node.lineno, reason=reason, excerpt=excerpt)  # type: ignore[attr-defined]
        )


def _string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value:
        return node.value
    return None


def _boolean(node: ast.AST | None) -> bool | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return node.value
    return None


def _op_call(statement: ast.stmt) -> tuple[str, ast.Call] | None:
    """Return (method, call) for a bare ``op.<method>(...)`` statement."""

    if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
        return None
    function = statement.value.func
    if (
        isinstance(function, ast.Attribute)
        and isinstance(function.value, ast.Name)
        and function.value.id == "op"
    ):
        return function.attr, statement.value
    return None


def _is_column(node: ast.AST) -> ast.Call | None:
    if not isinstance(node, ast.Call):
        return None
    function = node.func
    name = (
        function.attr
        if isinstance(function, ast.Attribute)
        else function.id
        if isinstance(function, ast.Name)
        else ""
    )
    return node if name == "Column" else None


def _column_has_unaccounted_semantics(column: ast.Call) -> bool:
    # A positional argument after the name and type is a constraint or default
    # (ForeignKey, CheckConstraint, ...); nullable=False is NOT NULL, which the
    # SQL provider also leaves as an unaccounted modifier rather than extracting.
    if len(column.args) > 2:
        return True
    for keyword in column.keywords:
        if keyword.arg is None:
            return True
        if keyword.arg in _BENIGN_COLUMN_KEYWORDS:
            continue
        if keyword.arg == "nullable" and _boolean(keyword.value) is True:
            continue
        return True
    return False


def _create_table(body: _Body, statement: ast.stmt, call: ast.Call) -> None:
    table = _string(call.args[0]) if call.args else None
    if table is None or any(keyword.arg == "table_name" for keyword in call.keywords):
        body.gap(statement, "parse_failure")
        return
    if any(keyword.arg == "schema" for keyword in call.keywords):
        # A schema-qualified table is a different subject than the bare name;
        # asserting the bare name would risk false corroboration.
        body.gap(statement, "unsupported_statement")
        return
    body.fact(statement, "op.create_table", table_subject(table), "exists", "true")
    for argument in call.args[1:]:
        column = _is_column(argument)
        if column is None or _column_has_unaccounted_semantics(column):
            body.gap(statement, "unaccounted_column_semantics")
            return


def _add_column(body: _Body, statement: ast.stmt, call: ast.Call) -> None:
    table = _string(call.args[0]) if len(call.args) == 2 else None
    column = _is_column(call.args[1]) if len(call.args) == 2 else None
    name = _string(column.args[0]) if column is not None and column.args else None
    if table is None or column is None or name is None or any(
        keyword.arg in {"table_name", "column"} for keyword in call.keywords
    ):
        body.gap(statement, "parse_failure")
        return
    if any(keyword.arg for keyword in call.keywords):
        body.gap(statement, "unsupported_statement")
        return
    body.fact(
        statement, "op.add_column", column_subject(table, name), "exists", "true"
    )
    if _column_has_unaccounted_semantics(column):
        body.gap(statement, "unaccounted_column_semantics")


def _drop_column(body: _Body, statement: ast.stmt, call: ast.Call) -> None:
    table = _string(call.args[0]) if len(call.args) == 2 else None
    column = _string(call.args[1]) if len(call.args) == 2 else None
    if table is None or column is None or any(
        keyword.arg in {"table_name", "column_name"} for keyword in call.keywords
    ):
        body.gap(statement, "parse_failure")
        return
    if call.keywords:
        body.gap(statement, "unsupported_statement")
        return
    body.fact(
        statement, "op.drop_column", column_subject(table, column), "exists", "false"
    )


def _alter_column(body: _Body, statement: ast.stmt, call: ast.Call) -> None:
    table = _string(call.args[0]) if len(call.args) == 2 else None
    column = _string(call.args[1]) if len(call.args) == 2 else None
    if table is None or column is None:
        body.gap(statement, "parse_failure")
        return
    keywords = {keyword.arg: keyword.value for keyword in call.keywords}
    if None in keywords or "schema" in keywords:
        body.gap(statement, "unsupported_statement")
        return
    if "nullable" not in keywords:
        body.gap(statement, "unsupported_statement")
        return
    nullable = _boolean(keywords["nullable"])
    if nullable is None:
        body.gap(statement, "parse_failure")
        return
    body.fact(
        statement,
        "op.alter_column.nullable",
        column_subject(table, column),
        "nullable",
        "true" if nullable else "false",
    )
    if set(keywords) - {"nullable"} - _ALTER_HINT_KEYWORDS:
        body.gap(statement, "unaccounted_column_semantics")


_HANDLERS = {
    "create_table": _create_table,
    "add_column": _add_column,
    "drop_column": _drop_column,
    "alter_column": _alter_column,
}


def observe_migration_text(
    side: Side, path: str, text: str
) -> tuple[tuple[ProviderFact, ...], ProviderFileCoverage]:
    body = _Body(side, path)
    try:
        module = ast.parse(text)
    except (SyntaxError, ValueError):
        body.gaps.append(ProviderGap(line=1, reason="parse_failure"))
        return (), ProviderFileCoverage(side, path, "partial", 0, tuple(body.gaps))
    upgrade = next(
        (
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "upgrade"
        ),
        None,
    )
    if upgrade is None:
        body.gaps.append(
            ProviderGap(line=1, reason="unsupported_statement", excerpt="no upgrade()")
        )
    else:
        for statement in upgrade.body:
            if isinstance(statement, ast.Pass) or (
                isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Constant)
                and isinstance(statement.value.value, str)
            ):
                continue
            call = _op_call(statement)
            handler = _HANDLERS.get(call[0]) if call is not None else None
            if call is None or handler is None:
                body.gap(statement, "unsupported_statement")
                continue
            handler(body, statement, call[1])
    return tuple(body.facts), ProviderFileCoverage(
        revision_side=side,
        path=path,
        state="partial" if body.gaps else "observed",
        fact_count=len(body.facts),
        gaps=tuple(body.gaps),
    )


class RepositoryAlembicProvider:
    """Observe Alembic revision files in exact base/head checkouts."""

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

    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider=ALEMBIC_MIGRATION_PROVIDER,
            capabilities=_CAPABILITIES,
            selectors=(
                FileSelector(kind="path_glob", pattern="*/versions/*.py"),
                FileSelector(kind="path_glob", pattern="versions/*.py"),
            ),
        )

    def observe(
        self,
        *,
        head_paths: tuple[str, ...] = (),
        base_paths: tuple[str, ...] = (),
    ) -> ProviderObservation:
        facts: list[ProviderFact] = []
        coverage: list[ProviderFileCoverage] = []
        diagnostics: list[Diagnostic] = []
        for side, paths in (("head", head_paths), ("base", base_paths)):
            if not paths:
                continue
            side_facts, side_coverage, side_diagnostics = self._observe_side(
                side, paths
            )
            facts.extend(side_facts)
            coverage.extend(side_coverage)
            diagnostics.extend(side_diagnostics)
        return ProviderObservation(
            provider=ALEMBIC_MIGRATION_PROVIDER,
            facts=tuple(facts),
            coverage=tuple(coverage),
            diagnostics=tuple(diagnostics),
        )

    def _observe_side(
        self, side: Side, paths: tuple[str, ...]
    ) -> tuple[
        tuple[ProviderFact, ...],
        tuple[ProviderFileCoverage, ...],
        tuple[Diagnostic, ...],
    ]:
        root = self.roots[side]
        if root is None:
            return self._refuse(
                side,
                paths,
                "alembic_base_input_missing",
                "Base Alembic evidence is unavailable because no base checkout "
                "was provided; removal is not inferred.",
            )
        revision = checkout_revision(root)
        expected = self.expected_revisions[side]
        if not revision or (expected and revision != expected):
            return self._refuse(
                side,
                paths,
                "alembic_stale_checkout",
                f"Alembic scanning requires {side} checkout "
                f"{expected or '(unknown)'}; observed {revision or '(unavailable)'}.",
            )
        if not tracked_checkout_clean(root):
            return self._refuse(
                side,
                paths,
                "alembic_dirty_checkout",
                f"Alembic scanning requires tracked {side} checkout content to "
                "match the reviewed revision exactly.",
            )
        facts: list[ProviderFact] = []
        coverage: list[ProviderFileCoverage] = []
        diagnostics: list[Diagnostic] = []
        for path in paths:
            file_facts, file_coverage, diagnostic = self._observe_file(
                root, side, path
            )
            facts.extend(file_facts)
            coverage.append(file_coverage)
            if diagnostic is not None:
                diagnostics.append(diagnostic)
        return tuple(facts), tuple(coverage), tuple(diagnostics)

    def _observe_file(
        self, root: Path, side: Side, path: str
    ) -> tuple[tuple[ProviderFact, ...], ProviderFileCoverage, Diagnostic | None]:
        unavailable = ProviderFileCoverage(side, path, "unavailable")
        if is_symlinked(root, path):
            return (), unavailable, Diagnostic(
                code="alembic_symlinked_input",
                message=(
                    f"{path} is a symlinked migration input; observed evidence "
                    "must be bound to the reviewed git revision, and a "
                    "symlink's target is not, so it was not read."
                ),
            )
        try:
            raw = (root / path).read_bytes()
        except OSError:
            return (), unavailable, Diagnostic(
                code="alembic_file_unreadable",
                message=f"{side} checkout is missing tracked file {path}.",
            )
        if len(raw) > _MAX_BYTES_PER_FILE:
            return (), unavailable, Diagnostic(
                code="alembic_file_too_large",
                message=(
                    f"{path} exceeds the {_MAX_BYTES_PER_FILE}-byte scan limit; "
                    "no facts were observed."
                ),
            )
        facts, coverage = observe_migration_text(
            side, path, raw.decode("utf-8", errors="replace")
        )
        return facts, coverage, None

    @staticmethod
    def _refuse(
        side: Side, paths: tuple[str, ...], code: str, message: str
    ) -> tuple[
        tuple[ProviderFact, ...],
        tuple[ProviderFileCoverage, ...],
        tuple[Diagnostic, ...],
    ]:
        return (
            (),
            tuple(ProviderFileCoverage(side, path, "unavailable") for path in paths),
            (Diagnostic(code=code, message=message),),
        )
