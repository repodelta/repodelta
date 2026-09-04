from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from repodelta.model.contracts import (
    SqlSchemaFileCoverage,
    SqlSchemaGap,
    SqlSchemaResult,
    SqlSchemaStatement,
)
from repodelta.providers.sql_schema import _CAPABILITIES, RepositorySqlSchemaProvider


def _repository(tmp_path: Path, files: dict[str, str]) -> tuple[Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(root), "config", "user.name", "RepoDelta Test"],
        check=True,
    )
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-qm", "fixture"], check=True
    )
    revision = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return root, revision


def test_fully_supported_file_is_observed_without_gaps(tmp_path: Path) -> None:
    root, revision = _repository(
        tmp_path,
        {
            "migrations/001.sql": (
                "CREATE TABLE users (\n"
                "  id bigint,\n"
                "  email text\n"
                ");\n"
                "ALTER TABLE users ADD COLUMN name text;\n"
                "ALTER TABLE users DROP COLUMN legacy_flag;\n"
            ),
        },
    )
    provider = RepositorySqlSchemaProvider(root, expected_head_revision=revision)

    result = provider.observe(head_paths=("migrations/001.sql",))

    assert [item.kind for item in result.statements] == [
        "create_table",
        "alter_table_add_column",
        "alter_table_drop_column",
    ]
    assert result.coverage == (
        SqlSchemaFileCoverage(
            revision_side="head",
            path="migrations/001.sql",
            state="observed",
            statement_count=3,
        ),
    )
    assert result.diagnostics == ()


def test_unsupported_construct_becomes_an_explicit_coverage_gap(
    tmp_path: Path,
) -> None:
    root, revision = _repository(
        tmp_path,
        {
            "migrations/001.sql": (
                "ALTER TABLE users ADD COLUMN name text;\n"
                "DO $$\nBEGIN\n  UPDATE users SET name = '';\nEND\n$$;\n"
            ),
        },
    )
    provider = RepositorySqlSchemaProvider(root, expected_head_revision=revision)

    result = provider.observe(head_paths=("migrations/001.sql",))

    assert len(result.statements) == 1
    coverage = result.coverage[0]
    assert coverage.state == "partial"
    assert coverage.statement_count == 1
    assert [gap.reason for gap in coverage.gaps] == ["unsupported_statement"]
    assert coverage.gaps[0].line == 2


def test_malformed_supported_construct_is_a_parse_failure_not_a_guess(
    tmp_path: Path,
) -> None:
    root, revision = _repository(
        tmp_path,
        {"migrations/001.sql": "ALTER TABLE users ALTER COLUMN SET NOT NULL;\n"},
    )
    provider = RepositorySqlSchemaProvider(root, expected_head_revision=revision)

    result = provider.observe(head_paths=("migrations/001.sql",))

    assert result.statements == ()
    coverage = result.coverage[0]
    assert coverage.state == "partial"
    assert [gap.reason for gap in coverage.gaps] == ["parse_failure"]


def test_add_column_with_unaccounted_modifier_is_a_gap_not_silent(
    tmp_path: Path,
) -> None:
    root, revision = _repository(
        tmp_path,
        {
            "migrations/001.sql": (
                "ALTER TABLE users ADD COLUMN email text NOT NULL "
                "DEFAULT some_vendor_function();\n"
            ),
        },
    )
    provider = RepositorySqlSchemaProvider(root, expected_head_revision=revision)

    result = provider.observe(head_paths=("migrations/001.sql",))

    # The safe fact -- a column was added -- is still recorded.
    assert len(result.statements) == 1
    statement = result.statements[0]
    assert statement.kind == "alter_table_add_column"
    assert statement.column == "email"
    assert statement.nullable is None

    # But NOT NULL / DEFAULT in the same statement are not silently folded
    # into "fully observed" -- they become an explicit gap on the same line.
    coverage = result.coverage[0]
    assert coverage.state == "partial"
    assert coverage.statement_count == 1
    assert [gap.reason for gap in coverage.gaps] == ["unaccounted_column_semantics"]
    assert coverage.gaps[0].line == 1


def test_add_column_without_modifiers_stays_fully_observed(
    tmp_path: Path,
) -> None:
    root, revision = _repository(
        tmp_path,
        {"migrations/001.sql": "ALTER TABLE users ADD COLUMN external_id text;\n"},
    )
    provider = RepositorySqlSchemaProvider(root, expected_head_revision=revision)

    result = provider.observe(head_paths=("migrations/001.sql",))

    assert len(result.statements) == 1
    assert result.coverage[0].state == "observed"
    assert result.coverage[0].gaps == ()


def test_create_table_with_column_modifiers_is_a_gap_not_silent(
    tmp_path: Path,
) -> None:
    root, revision = _repository(
        tmp_path,
        {
            "migrations/001.sql": (
                "CREATE TABLE users (\n"
                "  id bigint PRIMARY KEY,\n"
                "  email text NOT NULL\n"
                ");\n"
            ),
        },
    )
    provider = RepositorySqlSchemaProvider(root, expected_head_revision=revision)

    result = provider.observe(head_paths=("migrations/001.sql",))

    # The safe fact -- the table exists -- is still recorded.
    assert len(result.statements) == 1
    assert result.statements[0].kind == "create_table"
    assert result.statements[0].table == "users"

    # But the column-level semantics inside the body (PRIMARY KEY, NOT NULL)
    # are unaccounted for and must not disappear into "fully observed".
    coverage = result.coverage[0]
    assert coverage.state == "partial"
    assert [gap.reason for gap in coverage.gaps] == ["unaccounted_column_semantics"]


def test_create_table_without_column_modifiers_stays_fully_observed(
    tmp_path: Path,
) -> None:
    root, revision = _repository(
        tmp_path,
        {"migrations/001.sql": "CREATE TABLE users (\n  id bigint,\n  email text\n);\n"},
    )
    provider = RepositorySqlSchemaProvider(root, expected_head_revision=revision)

    result = provider.observe(head_paths=("migrations/001.sql",))

    assert len(result.statements) == 1
    assert result.coverage[0].state == "observed"
    assert result.coverage[0].gaps == ()


def test_create_table_with_an_unclosed_body_is_a_parse_failure_not_a_fact(
    tmp_path: Path,
) -> None:
    root, revision = _repository(
        tmp_path,
        # No closing paren -- truncated/malformed, not a real table shape.
        {"migrations/001.sql": "CREATE TABLE users (\n  id bigint\n;\n"},
    )
    provider = RepositorySqlSchemaProvider(root, expected_head_revision=revision)

    result = provider.observe(head_paths=("migrations/001.sql",))

    # No "table declared" fact for syntax that never actually closed.
    assert result.statements == ()
    coverage = result.coverage[0]
    assert coverage.state == "partial"
    assert coverage.statement_count == 0
    assert [gap.reason for gap in coverage.gaps] == ["parse_failure"]


def test_create_table_body_close_survives_a_paren_inside_a_string_literal(
    tmp_path: Path,
) -> None:
    root, revision = _repository(
        tmp_path,
        {
            "migrations/001.sql": (
                "CREATE TABLE users (\n"
                "  note text DEFAULT '(n/a)'\n"
                ");\n"
            ),
        },
    )
    provider = RepositorySqlSchemaProvider(root, expected_head_revision=revision)

    result = provider.observe(head_paths=("migrations/001.sql",))

    # A paren inside a quoted default value must not be mistaken for the
    # body's structural close (or its absence).
    assert len(result.statements) == 1
    assert result.statements[0].kind == "create_table"


def test_create_table_body_close_not_fooled_by_a_paren_inside_a_dollar_quote(
    tmp_path: Path,
) -> None:
    root, revision = _repository(
        tmp_path,
        {
            # No real closing paren for the CREATE TABLE body -- the ')'
            # is inside a $$...$$ dollar-quoted default value.
            "migrations/001.sql": (
                "CREATE TABLE users (\n"
                "  note text DEFAULT $$abc)def$$\n"
            ),
        },
    )
    provider = RepositorySqlSchemaProvider(root, expected_head_revision=revision)

    result = provider.observe(head_paths=("migrations/001.sql",))

    assert result.statements == ()
    coverage = result.coverage[0]
    assert coverage.state == "partial"
    assert [gap.reason for gap in coverage.gaps] == ["parse_failure"]


def test_create_table_body_close_survives_a_real_dollar_quoted_default(
    tmp_path: Path,
) -> None:
    root, revision = _repository(
        tmp_path,
        {
            "migrations/001.sql": (
                "CREATE TABLE users (\n"
                "  note text DEFAULT $$abc)def$$\n"
                ");\n"
            ),
        },
    )
    provider = RepositorySqlSchemaProvider(root, expected_head_revision=revision)

    result = provider.observe(head_paths=("migrations/001.sql",))

    assert len(result.statements) == 1
    assert result.statements[0].kind == "create_table"


def test_symlinked_sql_input_fails_closed_instead_of_following_the_link(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.sql"
    outside.write_text("CREATE TABLE secret_leak (id bigint);\n", encoding="utf-8")
    root, revision = _repository(tmp_path, {"README.md": "hello\n"})
    (root / "migrations").mkdir(parents=True, exist_ok=True)
    (root / "migrations" / "001.sql").symlink_to(outside)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-qm", "add symlink"], check=True
    )
    revision = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    provider = RepositorySqlSchemaProvider(root, expected_head_revision=revision)

    result = provider.observe(head_paths=("migrations/001.sql",))

    assert result.statements == ()
    assert result.coverage == (
        SqlSchemaFileCoverage(
            revision_side="head", path="migrations/001.sql", state="unavailable"
        ),
    )
    assert [d.code for d in result.diagnostics] == [
        "sql_schema_symlink_outside_checkout"
    ]


def test_symlink_within_the_checkout_is_still_observed(tmp_path: Path) -> None:
    root, revision = _repository(
        tmp_path, {"migrations/real.sql": "CREATE TABLE inside_repo (id bigint);\n"}
    )
    (root / "migrations" / "alias.sql").symlink_to(root / "migrations" / "real.sql")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-qm", "add alias"], check=True
    )
    revision = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    provider = RepositorySqlSchemaProvider(root, expected_head_revision=revision)

    result = provider.observe(head_paths=("migrations/alias.sql",))

    assert len(result.statements) == 1
    assert result.statements[0].table == "inside_repo"
    assert result.coverage[0].state == "observed"


def test_capabilities_are_declared_on_every_observed_result(
    tmp_path: Path,
) -> None:
    root, revision = _repository(
        tmp_path, {"migrations/001.sql": "CREATE TABLE users (id bigint);\n"}
    )
    provider = RepositorySqlSchemaProvider(root, expected_head_revision=revision)

    result = provider.observe(head_paths=("migrations/001.sql",))

    assert result.capabilities == _CAPABILITIES
    assert set(statement.kind for statement in result.statements) <= set(
        result.capabilities
    )


def test_statement_outside_declared_capabilities_is_rejected() -> None:
    statement = SqlSchemaStatement(
        revision_side="head",
        path="x.sql",
        line_start=1,
        line_end=1,
        kind="create_table",
        table="users",
    )
    result = SqlSchemaResult(
        capabilities=("alter_table_add_column",),
        statements=(statement,),
        coverage=(
            SqlSchemaFileCoverage(
                revision_side="head", path="x.sql", state="observed", statement_count=1
            ),
        ),
    )
    with pytest.raises(ValueError, match="outside its declared capabilities"):
        result.validate_consistency()


def test_stale_head_checkout_is_unavailable_not_guessed(tmp_path: Path) -> None:
    root, revision = _repository(
        tmp_path, {"migrations/001.sql": "CREATE TABLE users (id bigint);\n"}
    )
    provider = RepositorySqlSchemaProvider(root, expected_head_revision="deadbeef")

    result = provider.observe(head_paths=("migrations/001.sql",))

    assert result.statements == ()
    assert result.coverage == (
        SqlSchemaFileCoverage(
            revision_side="head", path="migrations/001.sql", state="unavailable"
        ),
    )
    assert [d.code for d in result.diagnostics] == ["sql_schema_stale_checkout"]


def test_dirty_tracked_checkout_is_unavailable(tmp_path: Path) -> None:
    root, revision = _repository(
        tmp_path, {"migrations/001.sql": "CREATE TABLE users (id bigint);\n"}
    )
    (root / "migrations" / "001.sql").write_text("-- edited after commit\n")
    provider = RepositorySqlSchemaProvider(root, expected_head_revision=revision)

    result = provider.observe(head_paths=("migrations/001.sql",))

    assert [d.code for d in result.diagnostics] == ["sql_schema_dirty_checkout"]


def test_missing_base_checkout_is_unavailable_and_never_infers_removal(
    tmp_path: Path,
) -> None:
    root, revision = _repository(
        tmp_path, {"migrations/001.sql": "CREATE TABLE users (id bigint);\n"}
    )
    provider = RepositorySqlSchemaProvider(root, expected_head_revision=revision)

    result = provider.observe(base_paths=("migrations/000.sql",))

    assert result.statements == ()
    assert result.coverage == (
        SqlSchemaFileCoverage(
            revision_side="base", path="migrations/000.sql", state="unavailable"
        ),
    )
    assert [d.code for d in result.diagnostics] == ["sql_schema_base_input_missing"]


def test_no_requested_sql_files_produces_no_noise(tmp_path: Path) -> None:
    root, revision = _repository(tmp_path, {"README.md": "hello\n"})
    provider = RepositorySqlSchemaProvider(root, expected_head_revision=revision)

    result = provider.observe()

    assert result.statements == ()
    assert result.coverage == ()
    assert result.diagnostics == ()


def test_missing_tracked_file_is_unavailable_with_diagnostic(
    tmp_path: Path,
) -> None:
    root, revision = _repository(
        tmp_path, {"migrations/001.sql": "CREATE TABLE users (id bigint);\n"}
    )
    provider = RepositorySqlSchemaProvider(root, expected_head_revision=revision)

    result = provider.observe(head_paths=("migrations/absent.sql",))

    assert result.coverage == (
        SqlSchemaFileCoverage(
            revision_side="head", path="migrations/absent.sql", state="unavailable"
        ),
    )
    assert [d.code for d in result.diagnostics] == ["sql_schema_file_unreadable"]


def test_statement_requires_column_for_non_create_table_kinds() -> None:
    with pytest.raises(ValueError, match="requires a column"):
        SqlSchemaStatement(
            revision_side="head",
            path="x.sql",
            line_start=1,
            line_end=1,
            kind="alter_table_add_column",
            table="users",
        )


def test_create_table_statement_cannot_carry_a_column() -> None:
    with pytest.raises(ValueError, match="cannot carry a column"):
        SqlSchemaStatement(
            revision_side="head",
            path="x.sql",
            line_start=1,
            line_end=1,
            kind="create_table",
            table="users",
            column="email",
        )


def test_observed_coverage_cannot_carry_gaps() -> None:
    with pytest.raises(ValueError, match="observed coverage cannot carry gaps"):
        SqlSchemaFileCoverage(
            revision_side="head",
            path="x.sql",
            state="observed",
            gaps=(SqlSchemaGap(line=1, reason="unsupported_statement"),),
        )


def test_partial_coverage_requires_a_gap() -> None:
    with pytest.raises(ValueError, match="partial coverage requires a gap"):
        SqlSchemaFileCoverage(revision_side="head", path="x.sql", state="partial")
