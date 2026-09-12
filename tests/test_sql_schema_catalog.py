from __future__ import annotations

import pytest

from repodelta.changes.hunks import parse_changed_files
from repodelta.facts.catalog import build_evidence_catalog
from repodelta.model.contracts import (
    ChangedFile,
    ReviewSourcePacket,
    SqlSchemaFileCoverage,
    SqlSchemaResult,
    SqlSchemaStatement,
)


def _packet(**overrides) -> ReviewSourcePacket:
    values = dict(
        repository="acme/widget",
        pull_request=1,
        title="add users table",
        source_records=(),
        changed_files=(
            ChangedFile(base_path=None, head_path="migrations/001.sql", status="added"),
        ),
        head_sha="head123",
    )
    values.update(overrides)
    return ReviewSourcePacket(**values).with_revision()


def test_sql_schema_statement_becomes_a_typed_evidence_item() -> None:
    packet = _packet()
    statement = SqlSchemaStatement(
        revision_side="head",
        path="migrations/001.sql",
        line_start=1,
        line_end=4,
        kind="create_table",
        table="users",
        normalized_text="CREATE TABLE users ( id bigint )",
    )
    sql_schema_result = SqlSchemaResult(
        capabilities=("create_table",),
        statements=(statement,),
        coverage=(
            SqlSchemaFileCoverage(
                revision_side="head",
                path="migrations/001.sql",
                state="observed",
                statement_count=1,
            ),
        ),
    )
    sql_schema_result.validate_consistency()

    catalog = build_evidence_catalog(
        packet,
        parse_changed_files(packet.changed_files),
        sql_schema_result=sql_schema_result,
    )
    catalog.validate_consistency()

    items = [item for item in catalog.items if item.kind == "sql_schema_statement"]
    assert len(items) == 1
    item = items[0]
    assert item.authority == "sql_schema_provider"
    assert item.profile == "schema"
    assert item.role == "revision_fact"
    assert item.revision_side == "head"
    assert item.changed is False
    assert item.sql_schema_statement == statement
    assert catalog.sql_schema_capabilities == ("create_table",)
    assert item.sources[0].path == "migrations/001.sql"
    assert item.sources[0].line_start == 1
    assert catalog.sql_schema_coverage == sql_schema_result.coverage


def test_sql_schema_gap_diagnostics_flow_into_catalog_diagnostics() -> None:
    from repodelta.model.contracts import Diagnostic, SqlSchemaGap

    packet = _packet()
    coverage = SqlSchemaFileCoverage(
        revision_side="head",
        path="migrations/001.sql",
        state="partial",
        statement_count=0,
        gaps=(SqlSchemaGap(line=1, reason="unsupported_statement", excerpt="DO $$ ... $$"),),
    )
    sql_schema_result = SqlSchemaResult(
        coverage=(coverage,),
        diagnostics=(
            Diagnostic(code="sql_schema_dirty_checkout", message="dirty checkout"),
        ),
    )
    sql_schema_result.validate_consistency()

    catalog = build_evidence_catalog(
        packet,
        parse_changed_files(packet.changed_files),
        sql_schema_result=sql_schema_result,
    )
    catalog.validate_consistency()

    assert catalog.sql_schema_coverage == (coverage,)
    assert any(
        diagnostic.code == "sql_schema_dirty_checkout"
        for diagnostic in catalog.diagnostics
    )


def test_no_sql_schema_result_leaves_catalog_unaffected() -> None:
    packet = _packet()

    catalog = build_evidence_catalog(
        packet, parse_changed_files(packet.changed_files)
    )
    catalog.validate_consistency()

    assert not any(item.kind == "sql_schema_statement" for item in catalog.items)
    assert catalog.sql_schema_coverage == ()


def test_ingestion_validates_the_result_even_if_the_provider_did_not() -> None:
    # A hand-built SqlSchemaResult that never went through its own
    # validate_consistency() -- standing in for a third-party
    # SqlSchemaProvider implementation that skipped it. The capability/fact
    # invariant belongs to the ingestion boundary, not just to
    # RepositorySqlSchemaProvider's own call site.
    packet = _packet()
    statement = SqlSchemaStatement(
        revision_side="head",
        path="migrations/001.sql",
        line_start=1,
        line_end=1,
        kind="create_table",
        table="users",
    )
    untrustworthy_result = SqlSchemaResult(
        capabilities=("alter_table_add_column",),  # does not include create_table
        statements=(statement,),
        coverage=(
            SqlSchemaFileCoverage(
                revision_side="head",
                path="migrations/001.sql",
                state="observed",
                statement_count=1,
            ),
        ),
    )

    with pytest.raises(ValueError, match="outside its declared capabilities"):
        build_evidence_catalog(
            packet,
            parse_changed_files(packet.changed_files),
            sql_schema_result=untrustworthy_result,
        )
