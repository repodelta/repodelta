from __future__ import annotations

import subprocess
from pathlib import Path

from repodelta.model.contracts import AnalysisInput, ChangedFile, ReviewSourcePacket
from repodelta.pipeline import DeterministicAnalyzer
from repodelta.presentation.html import render_html
from repodelta.presentation.status import (
    format_provider_coverage,
    format_unclaimed_files,
)
from repodelta.providers.alembic_migration import RepositoryAlembicProvider
from repodelta.providers.sql_schema import (
    RepositorySqlSchemaProvider,
    SqlSchemaEvidenceProvider,
)

_FILES = {
    # Code: no evidence provider declares applicability here.
    "app/service.py": "def handler():\n    return 1\n",
    "docs/notes.md": "# notes\n",
    "migrations/002_email.sql": (
        "ALTER TABLE users ALTER COLUMN email SET NOT NULL;\n"
        "ALTER TABLE users ALTER COLUMN nickname SET NOT NULL;\n"
        "CREATE INDEX ix_users_email ON users (email);\n"
    ),
    "alembic/versions/0002_email.py": (
        "from alembic import op\n"
        "\n"
        "def upgrade():\n"
        '    op.alter_column("users", "email", nullable=False)\n'
        '    op.alter_column("users", "nickname", nullable=True)\n'
        '    op.execute("UPDATE users SET email = lower(email)")\n'
    ),
}


def _repository(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for key, value in (("user.email", "t@example.com"), ("user.name", "Test")):
        subprocess.run(["git", "-C", str(root), "config", key, value], check=True)
    for name, content in _FILES.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "change"], check=True)
    revision = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return root, revision


def test_mixed_change_set_shows_routing_corroboration_conflict_and_the_gap(
    tmp_path: Path,
) -> None:
    root, revision = _repository(tmp_path)
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=308,
        title="tighten users.email",
        source_records=(),
        changed_files=tuple(
            ChangedFile(base_path=None, head_path=path, status="added")
            for path in _FILES
        ),
        head_sha=revision,
    ).with_revision()
    analyzer = DeterministicAnalyzer(
        evidence_providers=(
            SqlSchemaEvidenceProvider(
                RepositorySqlSchemaProvider(root, expected_head_revision=revision)
            ),
            RepositoryAlembicProvider(root, expected_head_revision=revision),
        )
    )

    brief = analyzer.analyze(AnalysisInput(packet=packet))
    brief.evidence_catalog.validate_consistency()
    overview = brief.overview

    # Routing: each provider examined only what it declared; the rest is a fact.
    plan = brief.evidence_catalog.provider_plan
    assert {entry.provider: entry.head_paths for entry in plan.entries} == {
        "alembic-migration": ("alembic/versions/0002_email.py",),
        "sql-schema": ("migrations/002_email.sql",),
    }
    assert overview.unclaimed_changed_files == ("app/service.py", "docs/notes.md")

    # Per-provider coverage: what each examined, and what it could not interpret.
    rows = {row.provider: row for row in overview.provider_coverage}
    assert {name: row.state for name, row in rows.items()} == {
        "alembic-migration": "partial",
        "sql-schema": "partial",
    }
    assert [gap.reason for gap in rows["alembic-migration"].files[0].gaps] == [
        "unsupported_statement"
    ]
    assert [gap.reason for gap in rows["sql-schema"].files[0].gaps] == [
        "unsupported_statement"
    ]
    assert "op.alter_column.nullable" in rows["alembic-migration"].capabilities
    assert "alter_column_set_not_null" in rows["sql-schema"].capabilities

    # Corroboration: both providers state users.email is NOT NULL -> one fact.
    facts = {
        (item.schema_fact.subject, item.schema_fact.value): item
        for item in brief.evidence_catalog.items
        if item.kind == "schema_fact"
    }
    email = facts[("column:users.email", "false")]
    assert email.providers == ("alembic-migration", "sql-schema")
    assert {source.path for source in email.sources} == {
        "alembic/versions/0002_email.py",
        "migrations/002_email.sql",
    }

    # Conflict: nickname is NOT NULL in SQL and nullable in Alembic. Both kept.
    assert facts[("column:users.nickname", "false")].providers == ("sql-schema",)
    assert facts[("column:users.nickname", "true")].providers == ("alembic-migration",)
    (conflict,) = overview.provider_conflicts
    assert (conflict.subject, conflict.attribute) == (
        "column:users.nickname",
        "nullable",
    )
    assert [side.value for side in conflict.sides] == ["false", "true"]
    assert any(item.label == "Provider conflicts" for item in overview.attention)

    # The conclusion-free guardrail: nothing merged or scored.
    assert len([i for i in facts.values() if i.schema_fact.subject == "column:users.nickname"]) == 2

    # Presentation sinks consume the canonical result without re-deciding it.
    lines = [format_provider_coverage(row) for row in overview.provider_coverage]
    assert lines[0].startswith("Evidence provider alembic-migration: partial ·")
    assert "1/1 files examined, 1 uninterpreted" in lines[0]
    html = render_html(brief)
    assert "Evidence provider alembic-migration: partial" in html
    assert "Evidence provider sql-schema: partial" in html
    assert "2 changed files claimed by no provider" in html
    assert "Provider conflicts" in html
    assert format_unclaimed_files(overview.unclaimed_changed_files) == (
        "Evidence providers: 2 changed files claimed by no provider · "
        "app/service.py, docs/notes.md"
    )
