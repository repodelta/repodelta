from __future__ import annotations

import pytest

from prismcode.guardrails.planning import compile_guardrail_scan_plans
from prismcode.model.contracts import (
    AnalysisInput,
    GuardrailScanPlanSet,
    Requirement,
    ReviewSourcePacket,
    SourceRef,
)
from prismcode.pipeline import DeterministicAnalyzer
from prismcode.presentation.html import render_html


def _guardrail(identifier: str, text: str) -> Requirement:
    return Requirement(
        id=identifier,
        text=text,
        role="obligation",
        purpose="guardrail",
        authority="issue",
        kind="guardrail",
        sources=(
            SourceRef(
                label="Issue #1 · Out of scope",
                url="https://github.com/acme/widget/issues/1",
            ),
        ),
    )


def test_guardrail_plans_are_one_to_one_stable_and_conclusion_free() -> None:
    guardrails = (
        _guardrail("G1", "No compatibility modules remain."),
        _guardrail("G2", "Do not add feature flags or dual writes."),
    )

    first = compile_guardrail_scan_plans(guardrails)
    second = compile_guardrail_scan_plans(guardrails)

    assert first == second
    assert [item.id for item in first.plans] == ["GSP:G1", "GSP:G2"]
    assert [item.guardrail_id for item in first.plans] == ["G1", "G2"]
    assert all(item.revision_side == "head" for item in first.plans)
    assert all(item.scope == "repository" for item in first.plans)
    assert all(item.root_paths == (".",) for item in first.plans)
    assert all(
        item.surfaces == ("paths", "file_content", "symbol_names")
        for item in first.plans
    )
    assert [item.value for item in first.plans[0].selectors] == [
        "compatibility modules"
    ]
    assert [item.value for item in first.plans[1].selectors] == [
        "feature flags",
        "dual writes",
    ]
    assert [item.query_text for item in first.plans] == [
        item.text for item in guardrails
    ]
    assert all(
        item.sources == guardrails[index].sources
        for index, item in enumerate(first.plans)
    )
    assert not hasattr(first.plans[0], "status")
    assert not hasattr(first.plans[0], "result")


def test_plan_validation_rejects_missing_or_non_guardrail_ownership() -> None:
    guardrail = _guardrail("G1", "No legacy path remains.")
    plans = compile_guardrail_scan_plans((guardrail,))
    requirement = Requirement(id="R1", text="Add the canonical path.")

    with pytest.raises(ValueError, match="one-to-one"):
        plans.validate_consistency((guardrail, _guardrail("G2", "No fallback.")))
    with pytest.raises(ValueError, match="one-to-one"):
        plans.validate_consistency((requirement,))
    GuardrailScanPlanSet().validate_consistency(())


def test_pipeline_projects_plan_only_for_g_and_keeps_absence_unproven() -> None:
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=1,
        title="Plan guardrail scans",
        source_records=(),
        source_url="https://github.com/acme/widget/pull/1",
    ).with_revision()
    requirements = (
        Requirement(id="R1", text="Add the canonical path."),
        _guardrail("G1", "No compatibility modules remain."),
        _guardrail("G2", "Do not add feature flags or dual writes."),
    )

    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(packet=packet, requirements=requirements)
    )

    assert brief.guardrail_scan_plans.schema_version == "guardrail_scan_plan_set.v2"
    assert len(brief.guardrail_scan_plans.plans) == 2
    slices = {
        item.focus_statement_id: item for item in brief.projection.slices
    }
    assert slices["R1"].guardrail_scan_plan_id is None
    assert slices["G1"].guardrail_scan_plan_id == "GSP:G1"
    assert slices["G2"].guardrail_scan_plan_id == "GSP:G2"
    boundary = [
        item
        for item in brief.projection_candidates.diagnostics
        if item.slot == "boundary_fact" and item.focus_statement_id == "G1"
    ]
    assert boundary[0].state == "provider_unavailable"
    assert boundary[0].affected_ids == ("GSP:G1",)
    assert "No bounded repository scan provider was configured." in (
        boundary[0].message
    )

    serialized = brief.to_dict()
    assert serialized["guardrail_scan_plans"]["plans"][0]["id"] == "GSP:G1"
    html = render_html(brief)
    assert html.count(
        '<span class="block-title">Guardrail scan plan</span>'
    ) == 2
    assert (
        "repository paths / file_content / symbol_names · head revision"
        in html
    )
    assert "No bounded repository scan provider was configured." in html
    assert "No compatibility modules remain." in html
    assert "guardrail satisfied" not in html.casefold()
