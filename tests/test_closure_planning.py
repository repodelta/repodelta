from __future__ import annotations

import pytest

from prismcode.closure.planning import compile_closure_scan_plans
from prismcode.model.contracts import (
    AnalysisInput,
    ClosureScanPlanSet,
    Requirement,
    ReviewSourcePacket,
    SourceRef,
    TransformationClaim,
    TransformationContract,
    TransformationPredicate,
    TransformationPredicateSet,
)
from prismcode.pipeline import DeterministicAnalyzer
from prismcode.presentation.html import render_html
from prismcode.semantics.criteria import extract_review_semantics


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

    first = compile_closure_scan_plans(guardrails)
    second = compile_closure_scan_plans(guardrails)

    assert first == second
    assert [item.id for item in first.plans] == ["CSP:G1", "CSP:G2"]
    assert [item.statement_id for item in first.plans] == ["G1", "G2"]
    assert all(item.revision_sides == ("head",) for item in first.plans)
    assert all(item.scope == "repository" for item in first.plans)
    assert all(item.root_paths == (".",) for item in first.plans)
    assert all(
        item.surfaces == ("paths", "file_content", "symbol_names")
        for item in first.plans
    )
    assert [item.target.value for item in first.plans[0].predicates] == [
        "compatibility modules"
    ]
    assert [item.target.value for item in first.plans[1].predicates] == [
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
    plans = compile_closure_scan_plans((guardrail,))
    requirement = Requirement(id="R1", text="Add the canonical path.")

    with pytest.raises(ValueError, match="one-to-one"):
        plans.validate_consistency((guardrail, _guardrail("G2", "No fallback.")))
    with pytest.raises(ValueError, match="one-to-one"):
        plans.validate_consistency((requirement,))
    ClosureScanPlanSet().validate_consistency(())


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

    assert brief.closure_scan_plans.schema_version == "closure_scan_plan_set.v3"
    assert len(brief.closure_scan_plans.plans) == 2
    slices = {
        item.change_map.focus_statement_id: item
        for item in brief.projection.slices
    }
    assert slices["R1"].closure_scan_plan_id is None
    assert slices["G1"].closure_scan_plan_id == "CSP:G1"
    assert slices["G2"].closure_scan_plan_id == "CSP:G2"
    boundary = [
        item
        for item in brief.projection_candidates.diagnostics
        if item.slot == "closure_fact" and item.focus_statement_id == "G1"
    ]
    assert boundary[0].state == "provider_unavailable"
    assert boundary[0].affected_ids == ("CSP:G1",)
    assert "No bounded repository scan provider was configured." in (
        boundary[0].message
    )

    serialized = brief.to_dict()
    assert serialized["closure_scan_plans"]["plans"][0]["id"] == "CSP:G1"
    html = render_html(brief)
    assert 'data-verification-subject="G1"' in html
    assert 'data-verification-subject="G2"' in html
    assert "No bounded repository scan provider was configured." in html
    assert "No compatibility modules remain." in html
    assert "guardrail satisfied" not in html.casefold()


def test_planning_includes_removal_and_only_executable_negative_completion() -> None:
    source = (SourceRef(label="PR #1", url="https://example.test/pr/1"),)
    removal = TransformationClaim(
        id="T1",
        kind="removal",
        text="Remove `Requirement.status`.",
        sources=source,
    )
    negative = TransformationClaim(
        id="CC1",
        kind="completion_condition",
        text="No `legacy_writer` remains.",
        sources=source,
    )
    positive = TransformationClaim(
        id="CC2",
        kind="completion_condition",
        text="All tests pass.",
        sources=source,
    )
    contract = TransformationContract(
        claims=(removal, negative, positive),
        predicates=TransformationPredicateSet(
            predicates=(
                TransformationPredicate(
                    id="TP:T1:1",
                    claim_id="T1",
                    selector_kind="symbol",
                    values=("Requirement.status",),
                    expectation="absent_head",
                    sources=source,
                ),
                TransformationPredicate(
                    id="TP:CC1:1",
                    claim_id="CC1",
                    selector_kind="symbol",
                    values=("legacy_writer",),
                    expectation="verified_head",
                    sources=source,
                ),
            ),
        ),
        removal_claim_ids=("T1",),
        completion_condition_claim_ids=("CC1", "CC2"),
        source_state="available",
    )
    contract.validate_consistency()

    plans = compile_closure_scan_plans((), contract)

    assert [item.statement_id for item in plans.plans] == ["T1", "CC1"]
    assert plans.plans[0].expectation == "transition"
    assert plans.plans[0].revision_sides == ("base", "head")
    assert [item.target.value for item in plans.plans[0].predicates] == [
        "Requirement.status"
    ]
    assert plans.plans[1].expectation == "absence"
    assert plans.plans[1].revision_sides == ("head",)


def test_unmarked_removal_does_not_reconstruct_executable_targets() -> None:
    claim = TransformationClaim(
        id="T1",
        kind="removal",
        text=(
            "Removed src/prismcode/guardrails, GuardrailScan, "
            "guardrail_scan_provider, and GSP/GSR/GSM identities."
        ),
        sources=(SourceRef(label="PR #1"),),
    )
    contract = TransformationContract(
        claims=(claim,),
        removal_claim_ids=("T1",),
        source_state="available",
    )

    plan = compile_closure_scan_plans((), contract).plans[0]

    assert plan.predicates == ()


def test_planning_conjoins_exact_target_with_path_scope() -> None:
    contract = extract_review_semantics(
        issue_body=None,
        issue_source=None,
        pr_body=(
            "## Removed legacy paths\n"
            "- Removed `_review_symbol_id` from "
            "`src/prismcode/convergence/structural.py`.\n"
            "- Removed the private identity implementation from "
            "`src/prismcode/projection/build.py`.\n"
        ),
        pr_source=SourceRef(label="PR #1"),
        pr_title="Scope negative evidence",
    ).transformation_contract

    plans = compile_closure_scan_plans((), contract).plans

    predicate = plans[0].predicates[0]
    assert predicate.target.kind == "identifier"
    assert predicate.target.value == "_review_symbol_id"
    assert tuple(item.value for item in predicate.path_scopes) == (
        "src/prismcode/convergence/structural.py",
    )
    assert plans[1].predicates == ()
