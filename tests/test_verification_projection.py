from __future__ import annotations

from prismcode.model.contracts import (
    AnalysisInput,
    AssociationReason,
    EvidenceCatalog,
    EvidenceItem,
    ProjectionCandidateSet,
    ObservedTransformation,
    ReviewSourcePacket,
    ReviewStructuralGraph,
    SourceRecord,
    SourceRef,
    StructuralFocusNode,
    StructuralGraphNode,
    TransformationAlignment,
    TransformationAssessment,
    TransformationAssessmentReason,
    TransformationClaim,
    TransformationClaimAssessment,
    TransformationContract,
    TransformationEvidenceBinding,
)
from prismcode.pipeline import DeterministicAnalyzer
from prismcode.projection.verification import project_verification_workspace


def _mixed_packet() -> ReviewSourcePacket:
    return ReviewSourcePacket(
        repository="acme/widget",
        pull_request=12,
        title="Unify verification projection",
        source_records=(
            SourceRecord(
                id="issue:11",
                kind="linked_issue",
                repository="acme/widget",
                title="Review contract",
                body="## Acceptance criteria\n- Emit one verification workspace.\n",
                url="https://example.test/issues/11",
            ),
            SourceRecord(
                id="pr:12",
                kind="pull_request",
                repository="acme/widget",
                title="Unify verification projection",
                body=(
                    "## Change\n- Add `VerificationWorkspace`.\n\n"
                    "## Completion conditions\n"
                    "- `VerificationWorkspace` is serialized once.\n"
                ),
                url="https://example.test/pulls/12",
            ),
        ),
    ).with_revision()


def test_pipeline_projects_rg_and_transformation_claims_once() -> None:
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=_mixed_packet()))
    workspace = brief.projection.verification_workspace
    expected_ids = (
        *(item.id for item in brief.requirements),
        *(item.id for item in brief.guardrails),
        *(item.id for item in brief.transformation_contract.claims),
    )

    assert tuple(item.subject_id for item in workspace.matrix) == expected_ids
    assert tuple(item.subject_id for item in workspace.inspections) == expected_ids
    assert len(workspace.by_subject_id()) == len(expected_ids)
    assert len(workspace.inspections_by_subject_id()) == len(expected_ids)
    requirement = workspace.by_subject_id()[brief.requirements[0].id]
    assert requirement.subject_kind == "requirement"
    assert requirement.status == "not_assessed"
    for claim in brief.transformation_contract.claims:
        entry = workspace.by_subject_id()[claim.id]
        assessed = brief.transformation_assessment.by_claim_id()[claim.id]
        assert entry.status == assessed.status
        assert entry.inspector_id == f"VEI:{claim.id}"


def test_transformation_binding_projects_to_shared_graph_overlay() -> None:
    source = SourceRef(label="PR #12")
    claim = TransformationClaim(
        id="T1",
        kind="change",
        text="Add `VerificationWorkspace`.",
        sources=(source,),
    )
    contract = TransformationContract(
        claims=(claim,),
        change_claim_ids=(claim.id,),
        source_state="available",
    )
    fact = EvidenceItem(
        id="E:workspace",
        summary="VerificationWorkspace added",
        kind="changed_hunk",
        classification="code",
        profile="production",
        authority="github_diff",
        revision_side="head",
        operation="added",
        role="changed_anchor",
        changed=True,
        sources=(source,),
    )
    reason = AssociationReason(
        kind="exact_identifier",
        detail="Exact VerificationWorkspace identifier.",
        matched_terms=("verificationworkspace",),
    )
    binding = TransformationEvidenceBinding(
        id="TAB:T1:E:workspace",
        claim_id="T1",
        evidence_id=fact.id,
        evidence_role="change",
        association="exact_identifier",
        reasons=(reason,),
    )
    alignment = TransformationAlignment(bindings=(binding,))
    assessment = TransformationAssessment(
        claims=(
            TransformationClaimAssessment(
                id="TAS:T1",
                claim_id="T1",
                status="demonstrated",
                supporting_binding_ids=(binding.id,),
                reasons=(
                    TransformationAssessmentReason(
                        kind="exact_fact_observed",
                        detail="Exact fact observed.",
                        binding_ids=(binding.id,),
                        evidence_ids=(fact.id,),
                    ),
                ),
            ),
        )
    )
    graph = ReviewStructuralGraph(
        nodes=(
            StructuralGraphNode(
                id="SGN:workspace",
                review_symbol_id="workspace",
                delta="added",
                evidence_ids=(fact.id,),
                display_evidence_id=fact.id,
            ),
        )
    )

    workspace = project_verification_workspace(
        (),
        contract,
        ObservedTransformation(
            fallback_change_evidence_ids=(fact.id,),
        ),
        alignment,
        assessment,
        EvidenceCatalog(items=(fact,)),
        ProjectionCandidateSet(),
        (),
        graph,
    )
    inspection = workspace.inspections_by_subject_id()[claim.id]

    assert inspection.observed_evidence_ids == (fact.id,)
    assert inspection.supporting_evidence_ids == (fact.id,)
    assert inspection.structural_overlay.nodes == (
        StructuralFocusNode(node_id="SGN:workspace", role="changed_anchor"),
    )


def test_verification_workspace_is_serialized_for_renderer_consumption() -> None:
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=_mixed_packet()))
    serialized = brief.to_dict()["projection"]

    assert serialized["schema_version"] == "review_projection.v22"
    assert serialized["verification_workspace"]["schema_version"] == (
        "verification_workspace.v1"
    )
    assert serialized["verification_workspace"]["matrix"]
    summary = brief.projection.verification_workspace.transformation_summary
    assert summary.claim_ids == tuple(
        item.id for item in brief.transformation_contract.claims
    )
    assert sum(item.count for item in summary.status_counts) == len(
        brief.transformation_contract.claims
    )
