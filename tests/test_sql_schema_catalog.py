from __future__ import annotations

import pytest

from repodelta.changes.hunks import parse_changed_files
from repodelta.facts.catalog import build_evidence_catalog
from repodelta.model.contracts import (
    ChangedFile,
    Diagnostic,
    ReviewSourcePacket,
    SqlSchemaFileCoverage,
    SqlSchemaGap,
    SqlSchemaResult,
    SqlSchemaStatement,
)
from repodelta.providers.planning import plan_providers, run_providers
from repodelta.providers.sql_schema import SqlSchemaEvidenceProvider


class _StubSqlProvider:
    def __init__(self, result: SqlSchemaResult) -> None:
        self.result = result

    def observe(self, *, head_paths=(), base_paths=()) -> SqlSchemaResult:
        return self.result


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


def _catalog(packet: ReviewSourcePacket, result: SqlSchemaResult):
    providers = (SqlSchemaEvidenceProvider(_StubSqlProvider(result)),)
    plan = plan_providers(
        packet.changed_files, (provider.descriptor() for provider in providers)
    )
    return build_evidence_catalog(
        packet,
        parse_changed_files(packet.changed_files),
        provider_plan=plan,
        provider_contributions=run_providers(providers, plan),
    )


def test_sql_schema_statement_becomes_a_provider_attributed_schema_fact() -> None:
    packet = _packet()
    result = SqlSchemaResult(
        capabilities=("create_table",),
        statements=(
            SqlSchemaStatement(
                revision_side="head",
                path="migrations/001.sql",
                line_start=1,
                line_end=4,
                kind="create_table",
                table="Users",
                normalized_text="CREATE TABLE Users ( id bigint )",
            ),
        ),
        coverage=(
            SqlSchemaFileCoverage(
                revision_side="head",
                path="migrations/001.sql",
                state="observed",
                statement_count=1,
            ),
        ),
    )

    catalog = _catalog(packet, result)
    catalog.validate_consistency()

    items = [item for item in catalog.items if item.kind == "schema_fact"]
    assert len(items) == 1
    item = items[0]
    assert item.authority == "evidence_provider"
    assert item.providers == ("sql-schema",)
    assert item.profile == "schema"
    assert item.role == "revision_fact"
    assert item.revision_side == "head"
    assert item.changed is False
    assert item.schema_fact is not None
    assert (item.schema_fact.subject, item.schema_fact.attribute) == (
        "table:users",
        "exists",
    )
    assert item.schema_fact.value == "true"
    assert item.sources[0].path == "migrations/001.sql"
    assert item.sources[0].line_start == 1
    (coverage,) = catalog.provider_coverage
    assert coverage.provider == "sql-schema"
    assert coverage.state == "observed"
    assert coverage.fact_count == 1
    # The provider's capability vocabulary is its statement kinds.
    assert "create_table" in coverage.capabilities


def test_sql_schema_gap_and_diagnostics_flow_into_provider_coverage() -> None:
    packet = _packet()
    result = SqlSchemaResult(
        coverage=(
            SqlSchemaFileCoverage(
                revision_side="head",
                path="migrations/001.sql",
                state="partial",
                statement_count=0,
                gaps=(
                    SqlSchemaGap(
                        line=1, reason="unsupported_statement", excerpt="DO $$ ... $$"
                    ),
                ),
            ),
        ),
        diagnostics=(
            Diagnostic(code="sql_schema_dirty_checkout", message="dirty checkout"),
        ),
    )

    catalog = _catalog(packet, result)
    catalog.validate_consistency()

    (coverage,) = catalog.provider_coverage
    assert coverage.state == "partial"
    (file_coverage,) = coverage.files
    assert file_coverage.gaps[0].reason == "unsupported_statement"
    assert any(
        diagnostic.code == "sql_schema_dirty_checkout"
        for diagnostic in catalog.diagnostics
    )


def test_no_providers_leaves_catalog_unaffected() -> None:
    packet = _packet()

    catalog = build_evidence_catalog(
        packet, parse_changed_files(packet.changed_files)
    )
    catalog.validate_consistency()

    assert not any(item.kind == "schema_fact" for item in catalog.items)
    assert catalog.provider_coverage == ()
    assert catalog.provider_plan.unclaimed_files == ()


def test_sql_result_is_validated_at_the_adapter_even_if_the_provider_did_not() -> None:
    # A hand-built SqlSchemaResult that never went through its own
    # validate_consistency() -- standing in for a third-party
    # SqlSchemaProvider implementation that skipped it. The capability/fact
    # invariant belongs to the ingestion boundary, not just to
    # RepositorySqlSchemaProvider's own call site.
    packet = _packet()
    untrustworthy_result = SqlSchemaResult(
        capabilities=("alter_table_add_column",),  # does not include create_table
        statements=(
            SqlSchemaStatement(
                revision_side="head",
                path="migrations/001.sql",
                line_start=1,
                line_end=1,
                kind="create_table",
                table="users",
            ),
        ),
        coverage=(
            SqlSchemaFileCoverage(
                revision_side="head",
                path="migrations/001.sql",
                state="observed",
                statement_count=1,
            ),
        ),
    )
    providers = (SqlSchemaEvidenceProvider(_StubSqlProvider(untrustworthy_result)),)
    plan = plan_providers(
        packet.changed_files, (provider.descriptor() for provider in providers)
    )

    # A provider that raises is failed closed: unavailable coverage, never silence.
    (contribution,) = run_providers(providers, plan)
    assert contribution.observation.facts == ()
    assert contribution.observation.coverage[0].state == "unavailable"
    assert (
        contribution.observation.diagnostics[0].code == "evidence_provider_failed"
    )
    with pytest.raises(ValueError, match="outside its declared capabilities"):
        providers[0].observe(head_paths=("migrations/001.sql",))
