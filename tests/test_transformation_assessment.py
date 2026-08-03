from __future__ import annotations

from dataclasses import replace

import pytest

from prismcode.assessment.transformation import assess_transformation
from prismcode.model.contracts import (
    AnalysisInput,
    ChangedFile,
    ReviewSourcePacket,
    SourceRecord,
    TransformationAssessment,
    TransformationSubjectMatch,
    TransformationSubjectSelection,
    VerificationObservation,
)
from prismcode.pipeline import DeterministicAnalyzer


def _packet(
    *, conclusion: str = "success", head_sha: str = "head123"
) -> ReviewSourcePacket:
    return ReviewSourcePacket(
        repository="acme/widget",
        pull_request=9,
        title="Assess transformation claims",
        source_records=(
            SourceRecord(
                id="pr:9",
                kind="pull_request",
                repository="acme/widget",
                title="Assess transformation claims",
                body=(
                    "## Change\n- Replace `old_call` with `new_call`.\n\n"
                    "## Selected region\n- `service.py` is the complete region.\n\n"
                    "## After topology\n- `new_call` is the canonical entry point.\n\n"
                    "## Removal\n- Remove `old_call`.\n\n"
                    "## Completion conditions\n- The `test_suite` check succeeds.\n\n"
                    "## Uncertainty\n- External deployment behavior is unknown.\n"
                ),
            ),
        ),
        changed_files=(
            ChangedFile(
                base_path="src/service.py",
                head_path="src/service.py",
                patch="@@ -1 +1 @@\n-old_call()\n+new_call()\n",
            ),
        ),
        verification_observations=(
            VerificationObservation(
                id="check:test_suite",
                name="test_suite",
                kind="check_run",
                status="completed",
                conclusion=conclusion,
                head_sha=head_sha,
                provider="github",
            ),
        ),
        head_sha="head123",
    ).with_revision()


def test_pipeline_assesses_claims_conservatively_from_typed_authorities() -> None:
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=_packet()))
    claims = {item.kind: item for item in brief.transformation_contract.claims}
    assessed = brief.transformation_assessment.by_claim_id()

    assert assessed[claims["change"].id].status == "demonstrated"
    assert assessed[claims["after_topology"].id].status == "demonstrated"
    assert assessed[claims["selected_region"].id].status == "unverified"
    assert assessed[claims["removal"].id].status == "partial"
    assert assessed[claims["completion_condition"].id].status == "demonstrated"
    assert assessed[claims["uncertainty"].id].status == "unverified"


def test_current_head_failure_contradicts_aligned_completion_condition() -> None:
    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(packet=_packet(conclusion="failure"))
    )
    claim = brief.transformation_contract.by_kind("completion_condition")[0]
    assessment = brief.transformation_assessment.by_claim_id()[claim.id]

    assert assessment.status == "contradicted"
    assert assessment.contradicting_binding_ids
    assert assessment.reasons[0].kind == "current_verification_failure"


def test_mixed_completion_preserves_each_predicate_polarity() -> None:
    packet = _packet()
    record = packet.source_records[0]
    packet = replace(
        packet,
        source_records=(
            replace(
                record,
                body=record.body.replace(
                    "## Completion conditions\n- The `test_suite` check succeeds.",
                    "## Completion conditions\n"
                    "- `new_call` is active and no `legacy_writer` remains.",
                ),
            ),
        ),
    ).with_revision()
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    claim = brief.transformation_contract.by_kind("completion_condition")[0]
    predicates = {
        item.predicate_id: item
        for item in brief.transformation_assessment.by_claim_id()[claim.id]
        .predicate_assessments
    }

    assert [
        item.expectation
        for item in brief.transformation_contract.predicates.predicates
        if item.claim_id == claim.id
    ] == ["verified_head", "absent_head"]
    assert [item.expectation for item in predicates.values()] == [
        "verified_head",
        "absent_head",
    ]
    assert brief.transformation_assessment.by_claim_id()[claim.id].status != (
        "contradicted"
    )


def test_multi_predicate_claim_cannot_borrow_another_predicates_binding() -> None:
    packet = _packet()
    record = packet.source_records[0]
    packet = replace(
        packet,
        source_records=(
            replace(
                record,
                body=(
                    "## After topology\n"
                    "- `new_call` and `missing_call` are canonical.\n"
                ),
            ),
        ),
        verification_observations=(),
    ).with_revision()
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    claim = brief.transformation_contract.by_kind("after_topology")[0]
    predicates = brief.transformation_contract.predicates.by_claim_id()[claim.id]
    assessments = {
        item.predicate_id: item
        for item in brief.transformation_assessment.by_claim_id()[claim.id]
        .predicate_assessments
    }

    assert assessments[predicates[0].id].status == "demonstrated"
    assert assessments[predicates[0].id].supporting_binding_ids
    assert assessments[predicates[1].id].status == "unverified"
    assert assessments[predicates[1].id].supporting_binding_ids == ()
    assert brief.transformation_assessment.by_claim_id()[claim.id].status == (
        "partial"
    )


def test_typed_predicate_rejects_unrelated_single_claim_binding() -> None:
    packet = _packet()
    record = packet.source_records[0]
    packet = replace(
        packet,
        source_records=(
            replace(
                record,
                body=(
                    "## After topology\n"
                    "- new_call remains available while `missing_call` is canonical.\n"
                ),
            ),
        ),
        verification_observations=(),
    ).with_revision()
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    claim = brief.transformation_contract.by_kind("after_topology")[0]
    binding = brief.transformation_alignment.by_claim_id()[claim.id][0]
    assessment = brief.transformation_assessment.by_claim_id()[claim.id]

    assert binding.association == "exact_identifier"
    assert assessment.status == "unverified"
    assert assessment.predicate_assessments[0].supporting_binding_ids == ()


def test_lowercase_check_name_uses_exact_predicate_match() -> None:
    packet = _packet()
    record = packet.source_records[0]
    check = packet.verification_observations[0]
    packet = replace(
        packet,
        source_records=(
            replace(
                record,
                body="## Completion conditions\n- The `test` check succeeds.\n",
            ),
        ),
        verification_observations=(replace(check, id="check:test", name="test"),),
    ).with_revision()
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    claim = brief.transformation_contract.by_kind("completion_condition")[0]
    assessment = brief.transformation_assessment.by_claim_id()[claim.id]

    assert assessment.status == "demonstrated"
    assert assessment.predicate_assessments[0].status == "demonstrated"


def test_changed_subject_does_not_hide_current_head_verification() -> None:
    packet = _packet()
    changed = packet.changed_files[0]
    packet = replace(
        packet,
        changed_files=(
            replace(
                changed,
                patch="@@ -1 +1 @@\n-old_call()\n+test_suite = new_call()\n",
            ),
        ),
    ).with_revision()
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    claim = brief.transformation_contract.by_kind("completion_condition")[0]
    predicate = brief.transformation_contract.predicates.by_claim_id()[claim.id][0]
    bindings = brief.transformation_alignment.by_claim_id()[claim.id]
    changed_binding = next(
        item for item in bindings if item.evidence_role != "verification"
    )
    verification_binding = next(
        item for item in bindings if item.evidence_role == "verification"
    )
    assessment = assess_transformation(
        brief.transformation_contract,
        brief.transformation_alignment,
        brief.evidence_catalog,
        brief.closure_scan_plans,
        head_sha=packet.head_sha,
        subject_selection=TransformationSubjectSelection(
            matches=(
                TransformationSubjectMatch(
                    id=f"TSM:{predicate.id}:1:{changed_binding.evidence_id}",
                    claim_id=claim.id,
                    predicate_id=predicate.id,
                    selector_index=1,
                    selector_value=predicate.values[0],
                    evidence_id=changed_binding.evidence_id,
                ),
            ),
        ),
    ).by_claim_id()[claim.id]

    assert assessment.status == "demonstrated"
    assert verification_binding.id in assessment.supporting_binding_ids


def test_stale_verification_never_demonstrates_current_completion() -> None:
    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(packet=_packet(head_sha="previous-head"))
    )
    claim = brief.transformation_contract.by_kind("completion_condition")[0]
    assessment = brief.transformation_assessment.by_claim_id()[claim.id]

    assert assessment.status == "partial"
    assert assessment.reasons[0].kind == "stale_verification"


def test_assessment_serializes_separately_from_alignment() -> None:
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=_packet()))
    serialized = brief.to_dict()

    assert serialized["transformation_assessment"]["schema_version"] == (
        "transformation_assessment.v2"
    )
    assert "status" not in serialized["transformation_alignment"]["bindings"][0]


def test_assessment_validation_rejects_unknown_binding_truth() -> None:
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=_packet()))
    assessment = brief.transformation_assessment
    first = assessment.claims[0]

    with pytest.raises(ValueError, match="unknown binding"):
        TransformationAssessment(
            claims=(
                replace(first, supporting_binding_ids=("TAB:missing",)),
                *assessment.claims[1:],
            )
        ).validate_consistency(
            brief.transformation_contract,
            brief.transformation_alignment,
            brief.evidence_catalog,
        )


def test_pipeline_builds_transformation_assessment_once(monkeypatch) -> None:
    import prismcode.pipeline as pipeline

    calls = 0
    real_assess = pipeline.assess_transformation

    def counting_assess(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_assess(*args, **kwargs)

    monkeypatch.setattr(pipeline, "assess_transformation", counting_assess)

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=_packet()))

    assert calls == 1
    assert isinstance(brief.transformation_assessment, TransformationAssessment)
