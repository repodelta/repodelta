from __future__ import annotations

"""Boundary fixture: one SqlSchemaResult, two downstream questions.

This intentionally stops short of adequacy semantics. It only asserts that
capability, observation, coverage, and gaps survive faithfully enough for a
downstream consumer to tell the difference between "the evidence answers
this" and "the evidence has an explicit gap here" -- it does not compute a
PASS/FAIL/UNKNOWN verdict itself.
"""

import subprocess
from pathlib import Path

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


def test_observation_answers_one_question_and_gaps_the_other(
    tmp_path: Path,
) -> None:
    # 001: table exists, email has no constraint yet.
    # 002: email is declared NOT NULL -- an observed, supported statement.
    # 003: a dynamic block that could touch email but is deliberately
    #      outside the supported DDL subset -- an explicit coverage gap,
    #      not a silent "nothing changed" assumption.
    root, revision = _repository(
        tmp_path,
        {
            "migrations/001.sql": (
                "CREATE TABLE users (\n"
                "  id bigint,\n"
                "  email text\n"
                ");\n"
            ),
            "migrations/002.sql": (
                "ALTER TABLE users ALTER COLUMN email SET NOT NULL;\n"
            ),
            "migrations/003.sql": (
                "DO $$\n"
                "BEGIN\n"
                "  EXECUTE 'ALTER TABLE users ALTER COLUMN email DROP NOT NULL';\n"
                "END\n"
                "$$;\n"
            ),
        },
    )
    provider = RepositorySqlSchemaProvider(root, expected_head_revision=revision)

    result = provider.observe(
        head_paths=(
            "migrations/001.sql",
            "migrations/002.sql",
            "migrations/003.sql",
        )
    )

    # Question A: "Is there an observed statement declaring users.email
    # NOT NULL?" -- the evidence is sufficient to answer this directly.
    not_null_statements = [
        statement
        for statement in result.statements
        if statement.kind == "alter_column_set_not_null"
        and statement.table == "users"
        and statement.column == "email"
    ]
    assert len(not_null_statements) == 1
    assert not_null_statements[0].path == "migrations/002.sql"
    assert not_null_statements[0].line_start == 1

    # Question B: "Can we conclude no migration makes users.email nullable
    # again?" -- the same result cannot support this: 003 is an explicit
    # coverage gap, not an absence of change.
    coverage_by_path = {item.path: item for item in result.coverage}
    assert coverage_by_path["migrations/001.sql"].state == "observed"
    assert coverage_by_path["migrations/002.sql"].state == "observed"
    assert coverage_by_path["migrations/003.sql"].state == "partial"
    assert [gap.reason for gap in coverage_by_path["migrations/003.sql"].gaps] == [
        "unsupported_statement"
    ]

    fully_accounted_for = all(item.state == "observed" for item in result.coverage)
    assert fully_accounted_for is False

    # Capability travels with the result: a consumer can tell
    # alter_column_set_not_null was something this provider could recognize
    # at all, without reading the provider's source.
    assert "alter_column_set_not_null" in result.capabilities
