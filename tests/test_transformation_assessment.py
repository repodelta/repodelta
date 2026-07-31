from __future__ import annotations

from dataclasses import replace

import pytest

from prismcode.model.contracts import (
    AnalysisInput,
    ChangedFile,
    ReviewSourcePacket,
    SourceRecord,
    TransformationAssessment,
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
        "transformation_assessment.v1"
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
