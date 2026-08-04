from dataclasses import replace

import pytest

from prismcode.assessment.migration import close_migration_assessments
from prismcode.model.contracts import (
    TransformationAssessmentReason,
    TransformationClaimAssessment,
    TransformationContract,
    TransformationMigration,
)


def _assessment(claim_id: str, status: str = "demonstrated"):
    return TransformationClaimAssessment(
        id=f"TAS:{claim_id}",
        claim_id=claim_id,
        status=status,
        supporting_binding_ids=(f"TAB:{claim_id}",) if status != "unverified" else (),
        contradicting_binding_ids=(f"TAB:{claim_id}:conflict",)
        if status == "contradicted"
        else (),
        reasons=(
            TransformationAssessmentReason(
                kind=(
                    "authority_bypass_observed"
                    if status == "contradicted"
                    else "coverage_incomplete"
                    if status == "partial"
                    else "no_binding"
                    if status == "unverified"
                    else "exact_fact_observed"
                ),
                detail=status,
            ),
        ),
    )


def _fixture(*, parent_ids=("T1",)):
    contract = TransformationContract(
        authority_claim_ids=("T2",),
        migration=TransformationMigration(
            general_claim_ids=parent_ids,
            consumer_claim_ids=("T3",),
            test_claim_ids=("T4",),
        ),
        removal_claim_ids=("T5",),
        completion_condition_claim_ids=("CC1",),
    )
    assessments = tuple(
        _assessment(claim_id)
        for claim_id in (*parent_ids, "T2", "T3", "T4", "T5", "CC1")
    )
    return contract, assessments


def _parent(contract, assessments):
    result = close_migration_assessments(contract, assessments)
    return {item.claim_id: item for item in result}[contract.migration.general_claim_ids[0]]


def test_complete_components_demonstrate_migration_closure() -> None:
    contract, assessments = _fixture()

    result = _parent(contract, assessments)

    assert result.status == "demonstrated"
    assert result.reasons[0].kind == "migration_closure_observed"
    assert result.component_claim_ids == ("T2", "T3", "T4", "T5", "CC1")
    assert result.supporting_binding_ids == tuple(
        f"TAB:{item}" for item in result.component_claim_ids
    )


@pytest.mark.parametrize("status", ("partial", "unverified"))
def test_incomplete_component_cannot_demonstrate_migration(status: str) -> None:
    contract, assessments = _fixture()
    assessments = tuple(
        _assessment(item.claim_id, status) if item.claim_id == "T4" else item
        for item in assessments
    )

    result = _parent(contract, assessments)

    assert result.status == "partial"
    assert result.reasons[0].kind == "migration_component_incomplete"


def test_contradicted_component_contradicts_migration() -> None:
    contract, assessments = _fixture()
    assessments = tuple(
        _assessment(item.claim_id, "contradicted")
        if item.claim_id == "T2"
        else item
        for item in assessments
    )

    result = _parent(contract, assessments)

    assert result.status == "contradicted"
    assert result.reasons[0].kind == "migration_component_conflict"
    assert result.contradicting_binding_ids == ("TAB:T2:conflict",)


def test_missing_required_component_fails_closed() -> None:
    contract, assessments = _fixture()
    contract = replace(contract, removal_claim_ids=())

    result = _parent(contract, assessments)

    assert result.status == "partial"
    assert "missing legacy removal" in result.reasons[0].detail


def test_multiple_migration_parents_remain_unverified() -> None:
    contract, assessments = _fixture(parent_ids=("T1", "T6"))

    result = _parent(contract, assessments)

    assert result.status == "unverified"
    assert result.reasons[0].kind == "migration_scope_ambiguous"
