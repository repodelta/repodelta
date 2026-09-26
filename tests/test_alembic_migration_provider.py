from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from repodelta.providers.alembic_migration import (
    RepositoryAlembicProvider,
    observe_migration_text,
)


def _repository(tmp_path: Path, files: dict[str, str]) -> tuple[Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for key, value in (("user.email", "t@example.com"), ("user.name", "Test")):
        subprocess.run(["git", "-C", str(root), "config", key, value], check=True)
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
    revision = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return root, revision


def _observe(body: str):
    return observe_migration_text(
        "head", "alembic/versions/1.py", "from alembic import op\nimport sqlalchemy as sa\n\n" + body
    )


def _summary(facts):
    return [(f.capability, f.subject, f.attribute, f.value) for f in facts]


def test_supported_operations_become_neutral_facts_without_gaps() -> None:
    facts, coverage = _observe(
        "def upgrade():\n"
        '    """doc"""\n'
        '    op.create_table("Users", sa.Column("id", sa.Integer))\n'
        '    op.add_column("users", sa.Column("email", sa.Text(), nullable=True))\n'
        '    op.drop_column("users", "legacy")\n'
        '    op.alter_column("users", "email", nullable=False, existing_type=sa.Text())\n'
        "\n"
        "def downgrade():\n"
        '    op.drop_column("users", "email")\n'
    )

    assert _summary(facts) == [
        ("op.create_table", "table:users", "exists", "true"),
        ("op.add_column", "column:users.email", "exists", "true"),
        ("op.drop_column", "column:users.legacy", "exists", "false"),
        ("op.alter_column.nullable", "column:users.email", "nullable", "false"),
    ]
    assert (coverage.state, coverage.fact_count, coverage.gaps) == ("observed", 4, ())
    # downgrade() is outside the declaration and never asserts anything.
    assert all(fact.line_start < 12 for fact in facts)


@pytest.mark.parametrize(
    ("statement", "reason", "facts"),
    [
        ('op.create_index("ix", "users", ["email"])', "unsupported_statement", 0),
        ('op.execute("UPDATE users SET x = 1")', "unsupported_statement", 0),
        ("for name in NAMES:\n        op.drop_column(name, 'x')", "unsupported_statement", 0),
        ('if cond:\n        op.drop_column("users", "x")', "unsupported_statement", 0),
        ('alembic_op.drop_column("users", "x")', "unsupported_statement", 0),
        ("op.drop_column(TABLE, 'x')", "parse_failure", 0),
        ('op.drop_column("users", "x", schema="audit")', "unsupported_statement", 0),
        ('op.alter_column("users", "x", type_=sa.Text())', "unsupported_statement", 0),
        ('op.alter_column("users", "x", nullable=flag)', "parse_failure", 0),
        ('op.create_table("audit.log", schema="audit")', "unsupported_statement", 0),
        (
            'op.add_column("users", sa.Column("x", sa.Text(), nullable=False))',
            "unaccounted_column_semantics",
            1,
        ),
        (
            'op.add_column("users", sa.Column("x", sa.Text(), server_default="a"))',
            "unaccounted_column_semantics",
            1,
        ),
        (
            'op.create_table("t", sa.Column("id", sa.Integer, primary_key=True))',
            "unaccounted_column_semantics",
            1,
        ),
        (
            'op.create_table("t", sa.Column("id", sa.Integer), sa.ForeignKeyConstraint(["id"], ["u.id"]))',
            "unaccounted_column_semantics",
            1,
        ),
        (
            'op.alter_column("users", "x", nullable=False, server_default="a")',
            "unaccounted_column_semantics",
            1,
        ),
    ],
)
def test_unrecognized_or_unaccounted_constructs_are_explicit_gaps(
    statement: str, reason: str, facts: int
) -> None:
    extracted, coverage = _observe(f"def upgrade():\n    {statement}\n")

    assert coverage.state == "partial"
    assert [gap.reason for gap in coverage.gaps] == [reason]
    assert len(extracted) == facts == coverage.fact_count


def test_missing_upgrade_and_unparsable_files_are_gaps_not_silence() -> None:
    _, no_upgrade = _observe("def downgrade():\n    pass\n")
    _, broken = observe_migration_text("head", "v/1.py", "def upgrade(:\n")

    assert (no_upgrade.state, no_upgrade.gaps[0].reason) == (
        "partial",
        "unsupported_statement",
    )
    assert (broken.state, broken.gaps[0].reason) == ("partial", "parse_failure")


def test_provider_declares_path_applicability_and_capabilities(tmp_path: Path) -> None:
    descriptor = RepositoryAlembicProvider(
        tmp_path, expected_head_revision=None
    ).descriptor()

    assert descriptor.provider == "alembic-migration"
    assert descriptor.claims("alembic/versions/abc_add_users.py")
    assert descriptor.claims("versions/abc.py")
    assert not descriptor.claims("app/models.py")
    assert not descriptor.claims("migrations/001.sql")
    assert "op.alter_column.nullable" in descriptor.capabilities


def test_observes_exact_checkout_and_binds_facts_to_the_revision(tmp_path: Path) -> None:
    root, revision = _repository(
        tmp_path,
        {
            "alembic/versions/1.py": (
                "from alembic import op\n"
                "def upgrade():\n"
                '    op.alter_column("users", "email", nullable=False)\n'
            )
        },
    )
    provider = RepositoryAlembicProvider(root, expected_head_revision=revision)

    observation = provider.observe(head_paths=("alembic/versions/1.py",))
    observation.validate_consistency(
        provider.descriptor(), head_paths=("alembic/versions/1.py",)
    )

    (fact,) = observation.facts
    assert (fact.subject, fact.attribute, fact.value) == (
        "column:users.email", "nullable", "false",
    )
    assert (fact.path, fact.line_start, fact.revision_side) == (
        "alembic/versions/1.py", 3, "head",
    )


def test_symlinked_stale_dirty_and_missing_inputs_fail_closed(tmp_path: Path) -> None:
    root, revision = _repository(
        tmp_path,
        {
            "alembic/versions/real.py": "def upgrade():\n    pass\n",
            "elsewhere.py": "def upgrade():\n    pass\n",
        },
    )
    link = root / "alembic/versions/link.py"
    os.symlink(root / "elsewhere.py", link)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "link"], check=True)
    revision = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()

    linked = RepositoryAlembicProvider(root, expected_head_revision=revision).observe(
        head_paths=("alembic/versions/link.py",)
    )
    assert [item.state for item in linked.coverage] == ["unavailable"]
    assert linked.diagnostics[0].code == "alembic_symlinked_input"

    stale = RepositoryAlembicProvider(root, expected_head_revision="0" * 40).observe(
        head_paths=("alembic/versions/real.py",)
    )
    assert stale.diagnostics[0].code == "alembic_stale_checkout"
    assert [item.state for item in stale.coverage] == ["unavailable"]

    no_base = RepositoryAlembicProvider(root, expected_head_revision=revision).observe(
        base_paths=("alembic/versions/real.py",)
    )
    assert no_base.diagnostics[0].code == "alembic_base_input_missing"

    (root / "alembic/versions/real.py").write_text("changed\n", encoding="utf-8")
    dirty = RepositoryAlembicProvider(root, expected_head_revision=revision).observe(
        head_paths=("alembic/versions/real.py",)
    )
    assert dirty.diagnostics[0].code == "alembic_dirty_checkout"
    assert dirty.facts == ()
