from __future__ import annotations

from dataclasses import replace

import pytest

from repodelta.changes.hunks import parse_changed_files
from repodelta.facts.catalog import build_evidence_catalog
from repodelta.model.contracts import (
    AnalysisInput,
    ChangedFile,
    FileSelector,
    ProviderContribution,
    ProviderDescriptor,
    ProviderFact,
    ProviderFileCoverage,
    ProviderGap,
    ProviderObservation,
    ReviewSourcePacket,
)
from repodelta.pipeline import DeterministicAnalyzer
from repodelta.providers.planning import plan_providers, run_providers


def _descriptor(name: str, *selectors: FileSelector, capabilities=("column_state",)):
    return ProviderDescriptor(
        provider=name,
        capabilities=tuple(capabilities),
        selectors=selectors or (FileSelector("suffix", ".sql"),),
    )


def _fact(
    provider: str,
    *,
    value: str = "false",
    attribute: str = "nullable",
    subject: str = "column:users.email",
    path: str = "migrations/001.sql",
    line: int = 1,
    side: str = "head",
    capability: str = "column_state",
) -> ProviderFact:
    return ProviderFact(
        provider=provider,
        capability=capability,
        subject=subject,
        attribute=attribute,
        value=value,
        revision_side=side,  # type: ignore[arg-type]
        path=path,
        line_start=line,
        line_end=line,
    )


def _observation(provider: str, *facts: ProviderFact) -> ProviderObservation:
    counted: dict[tuple[str, str], int] = {}
    for fact in facts:
        key = (fact.revision_side, fact.path)
        counted[key] = counted.get(key, 0) + 1
    return ProviderObservation(
        provider=provider,
        facts=facts,
        coverage=tuple(
            ProviderFileCoverage(
                revision_side=side, path=path, state="observed", fact_count=count
            )
            for (side, path), count in sorted(counted.items())
        ),
    )


class _Provider:
    def __init__(self, descriptor: ProviderDescriptor, observe) -> None:
        self._descriptor = descriptor
        self._observe = observe

    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    def observe(self, *, head_paths=(), base_paths=()) -> ProviderObservation:
        return self._observe(head_paths, base_paths)


def _packet(*files: ChangedFile) -> ReviewSourcePacket:
    return ReviewSourcePacket(
        repository="acme/widget",
        pull_request=1,
        title="schema change",
        source_records=(),
        changed_files=files
        or (ChangedFile(base_path=None, head_path="migrations/001.sql", status="added"),),
        head_sha="head123",
    ).with_revision()


def _catalog(packet: ReviewSourcePacket, providers):
    plan = plan_providers(
        packet.changed_files, (provider.descriptor() for provider in providers)
    )
    return build_evidence_catalog(
        packet,
        parse_changed_files(packet.changed_files),
        provider_plan=plan,
        provider_contributions=run_providers(providers, plan),
    )


def _fixed(name: str, *facts: ProviderFact, selectors=()):
    return _Provider(
        _descriptor(name, *selectors), lambda head, base: _observation(name, *facts)
    )


# 1. routing is non-exclusive and total -------------------------------------


def test_file_claimed_by_two_providers_goes_to_both_and_unmatched_is_explicit() -> None:
    files = (
        ChangedFile(base_path=None, head_path="migrations/001.sql", status="added"),
        ChangedFile(base_path=None, head_path="docs/readme.md", status="added"),
    )
    plan = plan_providers(
        files,
        (
            _descriptor("beta", FileSelector("suffix", ".sql")),
            _descriptor("alpha", FileSelector("path_glob", "migrations/*")),
        ),
    )

    assert [entry.provider for entry in plan.entries] == ["alpha", "beta"]
    assert all(entry.head_paths == ("migrations/001.sql",) for entry in plan.entries)
    assert plan.unclaimed_files == ("docs/readme.md",)
    assert plan.changed_files == ("docs/readme.md", "migrations/001.sql")


def test_planning_is_independent_of_input_order() -> None:
    files = tuple(
        ChangedFile(base_path=None, head_path=path, status="added")
        for path in ("b.sql", "a.sql", "c.txt")
    )
    descriptors = (_descriptor("one"), _descriptor("two", FileSelector("exact", "c.txt")))

    assert plan_providers(files, descriptors) == plan_providers(
        tuple(reversed(files)), tuple(reversed(descriptors))
    )


# 2. each side is routed by its own path ------------------------------------


def test_deleted_renamed_and_added_files_are_routed_by_their_own_side() -> None:
    files = (
        ChangedFile(base_path="old/gone.sql", head_path=None, status="removed"),
        ChangedFile(base_path="old/a.sql", head_path="new/a.txt", status="renamed"),
        ChangedFile(base_path=None, head_path="new/b.sql", status="added"),
    )

    plan = plan_providers(files, (_descriptor("sql"),))

    (entry,) = plan.entries
    assert entry.base_paths == ("old/a.sql", "old/gone.sql")
    assert entry.head_paths == ("new/b.sql",)
    # A rename whose head side is unclaimed is still claimed through its base.
    assert plan.unclaimed_files == ()


# 3. selectors do not escape -------------------------------------------------


@pytest.mark.parametrize(
    "path", ["../outside/x.sql", "/abs/x.sql", "a/../../x.sql", "", "..", "."]
)
def test_selectors_never_claim_paths_outside_the_repository(path: str) -> None:
    for selector in (
        FileSelector("suffix", ".sql"),
        FileSelector("path_glob", "*"),
        FileSelector("exact", "x.sql"),
    ):
        assert selector.matches(path) is False


def test_selectors_match_casefolded_posix_paths() -> None:
    assert FileSelector("suffix", ".SQL").matches("Migrations\\001.sql")
    assert FileSelector("exact", "Makefile").matches("./makefile")
    assert FileSelector("path_glob", "*/versions/*.py").matches("alembic/versions/1.py")
    assert not FileSelector("path_glob", "*/versions/*.py").matches("versions/1.py")


@pytest.mark.parametrize(
    "selector",
    [
        ("suffix", ""),
        ("suffix", "dir/.sql"),
        ("exact", "../x"),
        ("path_glob", "/abs/*"),
    ],
)
def test_malformed_selectors_are_rejected_at_declaration(selector) -> None:
    with pytest.raises(ValueError):
        FileSelector(*selector)


def test_descriptor_requires_concrete_identity_capabilities_and_selectors() -> None:
    selector = (FileSelector("suffix", ".sql"),)
    for kwargs in (
        dict(provider="", capabilities=("a",), selectors=selector),
        dict(provider="has space", capabilities=("a",), selectors=selector),
        dict(provider="p", capabilities=(), selectors=selector),
        dict(provider="p", capabilities=("a", "a"), selectors=selector),
        dict(provider="p", capabilities=("a",), selectors=()),
    ):
        with pytest.raises(ValueError):
            ProviderDescriptor(**kwargs)


# 4/5. ingestion trusts nothing ----------------------------------------------


def test_fact_outside_declared_capabilities_is_rejected_at_ingestion() -> None:
    provider = _fixed("liar", _fact("liar", capability="undeclared"))

    with pytest.raises(ValueError, match="outside its declared capabilities"):
        _catalog(_packet(), (provider,))


def test_fact_for_a_path_outside_the_dispatch_is_rejected() -> None:
    provider = _fixed("wanderer", _fact("wanderer", path="secrets/other.sql"))

    with pytest.raises(ValueError, match="outside its dispatch"):
        _catalog(_packet(), (provider,))


def test_fact_attributed_to_another_provider_is_rejected() -> None:
    provider = _Provider(
        _descriptor("honest"),
        lambda head, base: replace(
            _observation("honest", _fact("honest")),
            facts=(_fact("someone-else"),),
        ),
    )

    with pytest.raises(ValueError, match="attributed to"):
        _catalog(_packet(), (provider,))


class _Drifting(_Provider):
    """Declares one descriptor for planning and another when it runs."""

    def __init__(self, planned, running, observe) -> None:
        super().__init__(planned, observe)
        self._running = running
        self._calls = 0

    def descriptor(self) -> ProviderDescriptor:
        self._calls += 1
        return self._descriptor if self._calls == 1 else self._running


def test_contribution_whose_declaration_drifted_after_planning_is_rejected() -> None:
    planned = _descriptor("drifter")
    widened = _descriptor("drifter", capabilities=("column_state", "table_drop"))
    provider = _Drifting(
        planned,
        widened,
        lambda head, base: _observation(
            "drifter", _fact("drifter", capability="table_drop")
        ),
    )

    with pytest.raises(ValueError, match="differs from its planned declaration"):
        _catalog(_packet(), (provider,))


def test_contribution_from_an_unplanned_provider_is_rejected() -> None:
    packet = _packet()
    plan = plan_providers(packet.changed_files, (_descriptor("sql"),))
    intruder = _descriptor(
        "intruder", FileSelector("exact", "never.txt"), capabilities=("anything",)
    )

    with pytest.raises(ValueError, match="not in the provider plan"):
        build_evidence_catalog(
            packet,
            parse_changed_files(packet.changed_files),
            provider_plan=plan,
            provider_contributions=(
                ProviderContribution(_descriptor("sql"), ProviderObservation("sql")),
                ProviderContribution(intruder, ProviderObservation("intruder")),
            ),
        )


def test_planned_provider_with_nothing_dispatched_must_still_contribute() -> None:
    packet = _packet()
    plan = plan_providers(
        packet.changed_files,
        (_descriptor("sql"), _descriptor("idle", FileSelector("exact", "never.txt"))),
    )

    with pytest.raises(ValueError, match="returned nothing"):
        build_evidence_catalog(
            packet,
            parse_changed_files(packet.changed_files),
            provider_plan=plan,
            provider_contributions=(
                ProviderContribution(_descriptor("sql"), ProviderObservation("sql")),
            ),
        )


# 6/7. agreement -------------------------------------------------------------


def test_one_provider_repeating_a_fact_does_not_agree_with_itself() -> None:
    provider = _fixed(
        "solo", _fact("solo", line=1), _fact("solo", line=9)
    )

    catalog = _catalog(_packet(), (provider,))

    (item,) = [item for item in catalog.items if item.kind == "schema_fact"]
    assert item.providers == ("solo",)
    assert [source.line_start for source in item.sources] == [1, 9]
    assert catalog.provider_divergences == ()


def test_two_providers_asserting_the_same_value_share_one_item() -> None:
    packet = _packet(
        ChangedFile(base_path=None, head_path="migrations/001.sql", status="added"),
        ChangedFile(base_path=None, head_path="alembic/versions/1.py", status="added"),
    )
    sql = _fixed("sql", _fact("sql", path="migrations/001.sql", line=2))
    alembic = _fixed(
        "alembic",
        _fact("alembic", path="alembic/versions/1.py", line=14),
        selectors=(FileSelector("suffix", ".py"),),
    )

    catalog = _catalog(packet, (sql, alembic))
    catalog.validate_consistency()

    (item,) = [item for item in catalog.items if item.kind == "schema_fact"]
    assert item.providers == ("alembic", "sql")
    assert {source.path for source in item.sources} == {
        "migrations/001.sql",
        "alembic/versions/1.py",
    }
    assert catalog.provider_divergences == ()


# 8/9. divergence ------------------------------------------------------------


def _two_provider_packet() -> ReviewSourcePacket:
    return _packet(
        ChangedFile(base_path=None, head_path="migrations/001.sql", status="added"),
        ChangedFile(base_path=None, head_path="alembic/versions/1.py", status="added"),
    )


def test_differing_assertions_from_two_providers_are_retained_and_typed() -> None:
    sql = _fixed("sql", _fact("sql", value="false", path="migrations/001.sql"))
    alembic = _fixed(
        "alembic",
        _fact("alembic", value="true", path="alembic/versions/1.py"),
        selectors=(FileSelector("suffix", ".py"),),
    )

    catalog = _catalog(_two_provider_packet(), (sql, alembic))
    catalog.validate_consistency()

    facts = [item for item in catalog.items if item.kind == "schema_fact"]
    assert sorted(item.schema_fact.value for item in facts) == ["false", "true"]
    (divergence,) = catalog.provider_divergences
    assert (divergence.subject, divergence.attribute) == ("column:users.email", "nullable")
    assert [(side.value, side.providers) for side in divergence.sides] == [
        ("false", ("sql",)),
        ("true", ("alembic",)),
    ]
    assert {side.evidence_id for side in divergence.sides} == {item.id for item in facts}


def test_one_provider_differing_from_itself_is_not_a_provider_divergence() -> None:
    provider = _fixed(
        "solo", _fact("solo", value="false", line=1), _fact("solo", value="true", line=2)
    )

    catalog = _catalog(_packet(), (provider,))

    assert len([i for i in catalog.items if i.kind == "schema_fact"]) == 2
    assert catalog.provider_divergences == ()


def test_divergence_is_scoped_to_one_revision_side() -> None:
    # One modified file, dispatched to both providers on both sides. The
    # providers disagree only across sides, which is not a divergence.
    packet = _packet(
        ChangedFile(
            base_path="migrations/001.sql",
            head_path="migrations/001.sql",
            status="modified",
        )
    )

    def observing(name: str, side: str, value: str):
        fact = _fact(name, value=value, side=side)
        return _Provider(
            _descriptor(name),
            lambda head, base: ProviderObservation(
                provider=name,
                facts=(fact,),
                coverage=(
                    ProviderFileCoverage(side, fact.path, "observed", 1),  # type: ignore[arg-type]
                ),
            ),
        )

    across_sides = _catalog(
        packet, (observing("a", "head", "false"), observing("b", "base", "true"))
    )
    within_side = _catalog(
        packet, (observing("a", "head", "false"), observing("b", "head", "true"))
    )

    assert across_sides.provider_divergences == ()
    assert [c.revision_side for c in within_side.provider_divergences] == ["head"]


# 10. tampering ---------------------------------------------------------------


def _diverging_catalog():
    sql = _fixed("sql", _fact("sql", value="false", path="migrations/001.sql"))
    alembic = _fixed(
        "alembic",
        _fact("alembic", value="true", path="alembic/versions/1.py"),
        selectors=(FileSelector("suffix", ".py"),),
    )
    return _catalog(_two_provider_packet(), (sql, alembic))


def test_tampered_provider_identity_fails_validation() -> None:
    catalog = _diverging_catalog()
    target = next(item for item in catalog.items if item.kind == "schema_fact")
    tampered = replace(
        catalog,
        items=tuple(
            replace(item, providers=()) if item.id == target.id else item
            for item in catalog.items
        ),
    )

    with pytest.raises(ValueError, match="provider identities"):
        tampered.validate_consistency()


def test_a_non_provider_fact_cannot_claim_a_provider() -> None:
    catalog = _diverging_catalog()
    target = next(item for item in catalog.items if item.authority == "github_diff")
    tampered = replace(
        catalog,
        items=tuple(
            replace(item, providers=("sql",)) if item.id == target.id else item
            for item in catalog.items
        ),
    )

    with pytest.raises(ValueError, match="has no provider"):
        tampered.validate_consistency()


def test_provider_without_coverage_fails_validation() -> None:
    catalog = _diverging_catalog()
    tampered = replace(
        catalog,
        provider_coverage=tuple(
            row for row in catalog.provider_coverage if row.provider != "sql"
        ),
    )

    with pytest.raises(ValueError, match="without coverage"):
        tampered.validate_consistency()


def test_persisted_coverage_capabilities_are_held_to_the_plan() -> None:
    catalog = _diverging_catalog()
    widened = tuple(
        replace(row, capabilities=(*row.capabilities, "table_drop"))
        if row.provider == "sql"
        else row
        for row in catalog.provider_coverage
    )

    with pytest.raises(ValueError, match="planned declaration"):
        replace(catalog, provider_coverage=widened).validate_consistency()


def test_persisted_plan_cannot_dispatch_a_path_its_descriptor_never_claimed() -> None:
    catalog = _diverging_catalog()
    plan = catalog.provider_plan
    entries = tuple(
        replace(entry, head_paths=tuple(sorted((*entry.head_paths, "alembic/versions/1.py"))))
        if entry.provider == "sql"
        else entry
        for entry in plan.entries
    )

    with pytest.raises(ValueError, match="never claimed"):
        replace(catalog, provider_plan=replace(plan, entries=entries)).validate_consistency()


def test_persisted_divergence_is_recomputed_not_trusted() -> None:
    catalog = _diverging_catalog()

    with pytest.raises(ValueError, match="do not match"):
        replace(catalog, provider_divergences=()).validate_consistency()
    forged = replace(
        catalog.provider_divergences[0],
        sides=tuple(
            replace(side, value="maybe") for side in catalog.provider_divergences[0].sides
        ),
    )
    with pytest.raises(ValueError):
        replace(catalog, provider_divergences=(forged,)).validate_consistency()


def test_coverage_cannot_be_rewritten_away_from_the_planned_dispatch() -> None:
    catalog = _diverging_catalog()
    emptied = tuple(
        replace(row, state="not_requested", files=(), fact_count=0)
        if row.provider == "sql"
        else row
        for row in catalog.provider_coverage
    )

    with pytest.raises(ValueError, match="planned dispatch"):
        replace(catalog, provider_coverage=emptied).validate_consistency()


def test_coverage_must_agree_with_the_facts_it_covers() -> None:
    catalog = _diverging_catalog()

    def rewrite(**changes):
        rows = tuple(
            replace(
                row,
                files=tuple(replace(f, **changes) for f in row.files),
                fact_count=changes.get("fact_count", row.fact_count),
                state=changes.get("state", row.state),
            )
            if row.provider == "sql"
            else row
            for row in catalog.provider_coverage
        )
        return replace(catalog, provider_coverage=rows)

    with pytest.raises(ValueError, match="does not match its facts"):
        rewrite(fact_count=0).validate_consistency()
    with pytest.raises(ValueError, match="does not match its facts"):
        rewrite(state="unavailable", fact_count=0).validate_consistency()
    stripped = replace(
        catalog,
        items=tuple(
            replace(item, sources=()) if item.kind == "schema_fact" else item
            for item in catalog.items
        ),
    )
    with pytest.raises(ValueError, match="does not match its facts"):
        stripped.validate_consistency()


def test_coverage_state_is_recomputed_from_its_files() -> None:
    catalog = _diverging_catalog()
    row = replace(catalog.provider_coverage[0], state="unavailable")

    with pytest.raises(ValueError, match="does not match files"):
        replace(catalog, provider_coverage=(row, *catalog.provider_coverage[1:])).validate_consistency()


def test_plan_that_does_not_describe_the_packet_is_rejected() -> None:
    packet = _packet()
    plan = plan_providers(
        (ChangedFile(base_path=None, head_path="other.sql", status="added"),),
        (_descriptor("sql"),),
    )

    with pytest.raises(ValueError, match="does not match"):
        build_evidence_catalog(
            packet,
            parse_changed_files(packet.changed_files),
            provider_plan=plan,
            provider_contributions=(
                ProviderContribution(_descriptor("sql"), ProviderObservation("sql")),
            ),
        )


# 11. failure is never silence ------------------------------------------------


def test_provider_that_raises_yields_unavailable_coverage_and_a_diagnostic() -> None:
    def boom(head, base):
        raise RuntimeError("index corrupt")

    catalog = _catalog(_packet(), (_Provider(_descriptor("fragile"), boom),))

    (row,) = catalog.provider_coverage
    assert row.state == "unavailable"
    assert [item.state for item in row.files] == ["unavailable"]
    assert any(item.code == "evidence_provider_failed" for item in catalog.diagnostics)


def test_dispatched_file_a_provider_silently_omits_becomes_unavailable() -> None:
    silent = _Provider(_descriptor("silent"), lambda head, base: ProviderObservation("silent"))

    catalog = _catalog(_packet(), (silent,))

    (row,) = catalog.provider_coverage
    assert row.state == "unavailable"
    assert any(
        item.code == "evidence_provider_omitted_dispatch"
        for item in catalog.diagnostics
    )


def test_provider_with_nothing_dispatched_still_reports_its_capabilities() -> None:
    idle = _fixed("idle", selectors=(FileSelector("exact", "never.txt"),))

    catalog = _catalog(_packet(), (idle,))

    (row,) = catalog.provider_coverage
    assert (row.state, row.files, row.capabilities) == (
        "not_requested",
        (),
        ("column_state",),
    )


def test_declined_and_uninterpreted_files_are_distinguished() -> None:
    def observe(head, base):
        return ProviderObservation(
            provider="partial",
            coverage=(
                ProviderFileCoverage("head", "migrations/001.sql", "partial", 0,
                                     (ProviderGap(3, "unsupported_statement"),)),
                ProviderFileCoverage("head", "migrations/002.sql", "unavailable"),
            ),
        )

    packet = _packet(
        ChangedFile(base_path=None, head_path="migrations/001.sql", status="added"),
        ChangedFile(base_path=None, head_path="migrations/002.sql", status="added"),
    )
    catalog = _catalog(packet, (_Provider(_descriptor("partial"), observe),))

    (row,) = catalog.provider_coverage
    assert row.state == "partial"
    assert {item.path: item.state for item in row.files} == {
        "migrations/001.sql": "partial",
        "migrations/002.sql": "unavailable",
    }


# sinks: the overview consumes the catalog's result ----------------------------


def test_overview_reports_provider_coverage_unclaimed_files_and_divergences() -> None:
    packet = _packet(
        ChangedFile(base_path=None, head_path="migrations/001.sql", status="added"),
        ChangedFile(base_path=None, head_path="alembic/versions/1.py", status="added"),
        ChangedFile(base_path=None, head_path="notes/todo.md", status="added"),
    )
    sql = _fixed("sql", _fact("sql", value="false", path="migrations/001.sql"))
    alembic = _fixed(
        "alembic",
        _fact("alembic", value="true", path="alembic/versions/1.py"),
        selectors=(FileSelector("suffix", ".py"),),
    )

    brief = DeterministicAnalyzer(evidence_providers=(sql, alembic)).analyze(
        AnalysisInput(packet=packet)
    )

    overview = brief.overview
    assert [row.provider for row in overview.provider_coverage] == ["alembic", "sql"]
    assert overview.unclaimed_changed_files == ("notes/todo.md",)
    assert overview.provider_divergences == brief.evidence_catalog.provider_divergences
    (attention,) = [
        item for item in overview.attention if item.label == "Provider assertions differ"
    ]
    # The projection must not present a divergence as a proven contradiction.
    assert "effective database state is not established" in attention.message
    assert "contradict" not in attention.message.casefold()


def test_without_providers_every_changed_file_is_unclaimed_not_silent() -> None:
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=_packet()))

    assert brief.overview.unclaimed_changed_files == ("migrations/001.sql",)
    assert brief.overview.provider_coverage == ()


def test_coverage_limits_count_provider_rows_but_not_authoring_notices() -> None:
    from repodelta.model.contracts import ReviewAttention
    from repodelta.presentation.html import render_html

    sql = _fixed("sql", _fact("sql"))
    brief = DeterministicAnalyzer(evidence_providers=(sql,)).analyze(
        AnalysisInput(packet=_packet())
    )
    notice = ReviewAttention(
        id="authoring", label="Authoring", message="near-miss heading",
        scope="review", provider="authoring_contract",
    )
    brief = replace(brief, overview=replace(brief.overview, attention=(notice,)))

    html = render_html(brief)

    # One provider row; the authoring notice renders in its own section.
    assert "Coverage limits · 1</summary>" in html
    assert "Evidence provider sql: observed" in html
