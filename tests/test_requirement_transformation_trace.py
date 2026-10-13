from __future__ import annotations

from dataclasses import replace

import pytest

from repodelta.model.contracts import (
    AnalysisInput,
    ReviewSourcePacket,
    SourceRecord,
    VerificationObservation,
)
from repodelta.pipeline import DeterministicAnalyzer
from repodelta.presentation.html import render_html


def _packet(*, reference: str = "R1") -> ReviewSourcePacket:
    return ReviewSourcePacket(
        repository="acme/widget",
        pull_request=41,
        title="Trace requirement transformation evidence",
        source_records=(
            SourceRecord(
                id="issue:40",
                kind="linked_issue",
                repository="acme/widget",
                title="Migrate resolver responsibility",
                body=(
                    "## Requirements\n"
                    "- All production consumers use the canonical resolver.\n"
                ),
            ),
            SourceRecord(
                id="pr:41",
                kind="pull_request",
                repository="acme/widget",
                title="Trace requirement transformation evidence",
                body=(
                    "## Change\n"
                    f"- Add the canonical resolver for {reference}.\n\n"
                    "## Completion conditions\n"
                    f"- The `resolver_suite` check succeeds for {reference}.\n"
                ),
            ),
        ),
        verification_observations=(
            VerificationObservation(
                id="check:resolver_suite",
                name="resolver_suite",
                kind="check_run",
                status="completed",
                conclusion="success",
                head_sha="head41",
                provider="github",
            ),
        ),
        head_sha="head41",
    ).with_revision()


def test_pipeline_preserves_explicit_rg_to_tcc_trace_without_assessing_rg() -> None:
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=_packet()))
    trace = brief.requirement_transformation_trace
    completion = brief.transformation_contract.by_kind("completion_condition")[0]

    assert tuple(item.focus_statement_id for item in trace.groups) == ("R1",)
    assert trace.groups[0].coverage_state == "associated"
    assert tuple(
        item.transformation_claim_id for item in trace.associations
    ) == tuple(item.id for item in brief.transformation_contract.claims)
    assert tuple(item.id for item in trace.evidence_slices) == tuple(
        f"TES:{item.id}" for item in brief.transformation_contract.claims
    )
    completion_slice = next(
        item for item in trace.evidence_slices if item.claim_id == completion.id
    )
    assert completion_slice.assessment_id == f"TAS:{completion.id}"
    assert completion_slice.transformation_binding_ids
    assert brief.transformation_assessment.by_claim_id()[completion.id].status == (
        "demonstrated"
    )
    workspace = brief.projection.verification_workspace
    assert workspace.requirement_transformation_trace == trace
    assert workspace.by_subject_id()["R1"].status == "not_assessed"
    html = render_html(brief)
    assert "Explicit transformation trace" in html
    assert "Association only; requirement satisfaction is not assessed." in html


def test_missing_explicit_reference_remains_coverage_not_lexical_inference() -> None:
    packet = _packet(reference="the requirement")
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    trace = brief.requirement_transformation_trace

    assert trace.associations == ()
    assert trace.evidence_slices == ()
    assert trace.groups[0].coverage_state == "no_explicit_association"


def test_unknown_authored_focus_reference_is_not_admitted() -> None:
    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(packet=_packet(reference="R99"))
    )
    trace = brief.requirement_transformation_trace

    assert trace.associations == ()
    assert trace.groups[0].coverage_state == "no_explicit_association"
    assert tuple(item.referenced_focus_statement_id for item in trace.diagnostics) == (
        "R99",
        "R99",
    )
    assert all(item.state == "unknown_focus_reference" for item in trace.diagnostics)


def test_cross_claim_slice_reference_fails_closed() -> None:
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=_packet()))
    trace = brief.requirement_transformation_trace
    first, second = trace.evidence_slices
    tampered = replace(
        trace,
        evidence_slices=(
            replace(first, assessment_id=second.assessment_id),
            *trace.evidence_slices[1:],
        ),
    )

    with pytest.raises(ValueError, match="invalid assessment"):
        tampered.validate_consistency(
            (*brief.requirements, *brief.guardrails),
            brief.transformation_contract,
            brief.transformation_subject_selection,
            brief.transformation_structural_closure,
            brief.transformation_alignment,
            brief.transformation_assessment,
        )


def test_slice_cannot_omit_canonical_binding_references() -> None:
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=_packet()))
    trace = brief.requirement_transformation_trace
    binding_slice = next(
        item
        for item in trace.evidence_slices
        if item.transformation_binding_ids
    )
    tampered_slice = replace(binding_slice, transformation_binding_ids=())
    tampered = replace(
        trace,
        evidence_slices=tuple(
            tampered_slice if item.id == binding_slice.id else item
            for item in trace.evidence_slices
        ),
    )

    with pytest.raises(ValueError, match="changed transformation alignment"):
        tampered.validate_consistency(
            (*brief.requirements, *brief.guardrails),
            brief.transformation_contract,
            brief.transformation_subject_selection,
            brief.transformation_structural_closure,
            brief.transformation_alignment,
            brief.transformation_assessment,
        )
