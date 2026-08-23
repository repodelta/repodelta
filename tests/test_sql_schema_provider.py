from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from repodelta.model.contracts import SqlSchemaFileCoverage, SqlSchemaGap, SqlSchemaStatement
from repodelta.providers.sql_schema import RepositorySqlSchemaProvider


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
                "  id bigint PRIMARY KEY,\n"
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
