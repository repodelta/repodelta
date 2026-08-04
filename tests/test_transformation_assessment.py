from __future__ import annotations

from dataclasses import replace

import pytest

from prismcode.assessment.transformation import assess_transformation
from prismcode.model.contracts import (
    AnalysisInput,
    AssociationReason,
    AssociationSignature,
    ChangedFile,
    ClosureScanPlanSet,
    EvidenceCatalog,
    EvidenceItem,
    ReviewSourcePacket,
    SourceRecord,
    SourceRef,
    StructuralChangeIdentity,
    TransformationAssessment,
    TransformationEvidenceBinding,
    TransformationSubjectMatch,
    TransformationSubjectSelection,
    VerificationIdentity,
    VerificationObservation,
)
from prismcode.convergence.transformation import (
    TransformationClosurePolicy,
    converge_transformation_closure,
)
from prismcode.facts.transformation import reconstruct_observed_transformation
from prismcode.pipeline import DeterministicAnalyzer
from prismcode.routing.transformation import build_transformation_alignment
from prismcode.routing.transformation_subjects import select_transformation_subjects
from prismcode.semantics.criteria import extract_review_semantics


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
    assert assessed[claims["after_topology"].id].status == "partial"
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
    assert brief.transformation_assessment.by_claim_id()[claim.id].status == "partial"
    assert tuple(item.status for item in predicates.values()) == (
        "partial",
        "unverified",
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

    assert assessments[predicates[0].id].status == "partial"
    assert assessments[predicates[0].id].supporting_binding_ids
    assert assessments[predicates[1].id].status == "unverified"
    assert assessments[predicates[1].id].supporting_binding_ids == ()
    assert brief.transformation_assessment.by_claim_id()[claim.id].status == (
        "partial"
    )


@pytest.mark.parametrize(
    ("body", "kind"),
    (
        (
            "## Selected region\n- `new_call` is the complete region.\n",
            "selected_region",
        ),
        (
            "## Selected region\n### Inputs\n- `new_call` is the input boundary.\n",
            "input_boundary",
        ),
        (
            "## Selected region\n### Outputs\n- `new_call` is the output boundary.\n",
            "output_boundary",
        ),
        (
            "## Selected region\n### Boundaries\n- `new_call` is external.\n",
            "boundary",
        ),
        (
            "## Before topology\n- `old_call` is the canonical entry.\n",
            "before_topology",
        ),
        ("## After topology\n- `new_call` is the canonical entry.\n", "after_topology"),
        ("## Authority\n- `new_call` is the sole authority.\n", "authority"),
        ("## Production path\n- `new_call` controls production.\n", "production_path"),
        ("## Migration\n- Migrate production to `new_call`.\n", "migration"),
        (
            "## Migration\n### Producers\n- Migrate producers to `new_call`.\n",
            "producer_migration",
        ),
        (
            "## Migration\n### Consumers\n- Migrate consumers to `new_call`.\n",
            "consumer_migration",
        ),
    ),
)
def test_exact_surface_cannot_demonstrate_role_or_closure_semantics(
    body: str,
    kind: str,
) -> None:
    packet = _packet()
    record = packet.source_records[0]
    packet = replace(
        packet,
        source_records=(replace(record, body=body),),
        verification_observations=(),
    ).with_revision()

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    claim = brief.transformation_contract.by_kind(kind)[0]
    assessment = brief.transformation_assessment.by_claim_id()[claim.id]

    assert assessment.status == "partial"
    assert assessment.predicate_assessments[0].status == "partial"
    assert assessment.reasons[0].kind == "association_only"


def test_uncertainty_preserves_typed_predicates_without_assessing_them() -> None:
    packet = _packet()
    record = packet.source_records[0]
    packet = replace(
        packet,
        source_records=(
            replace(
                record,
                body="## Uncertainty\n- `new_call` ownership remains unknown.\n",
            ),
        ),
        verification_observations=(),
    ).with_revision()

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    claim = brief.transformation_contract.by_kind("uncertainty")[0]
    assessment = brief.transformation_assessment.by_claim_id()[claim.id]

    assert assessment.status == "unverified"
    assert len(assessment.predicate_assessments) == 1
    assert assessment.predicate_assessments[0].status == "unverified"
    assert assessment.reasons[0].kind == "uncertainty_context"


@pytest.mark.parametrize(
    ("body", "kind", "expected_status"),
    (
        ("## Change\n- Replace old_call with new_call.\n", "change", "demonstrated"),
        ("## Authority\n- new_call is the sole authority.\n", "authority", "partial"),
        ("## Migration\n- Migrate production to new_call.\n", "migration", "partial"),
    ),
)
def test_selector_free_claims_share_the_claim_aware_proof_boundary(
    body: str,
    kind: str,
    expected_status: str,
) -> None:
    packet = _packet()
    record = packet.source_records[0]
    packet = replace(
        packet,
        source_records=(replace(record, body=body),),
        verification_observations=(),
    ).with_revision()

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    claim = brief.transformation_contract.by_kind(kind)[0]

    assert brief.transformation_contract.predicates.predicates == ()
    assert brief.transformation_assessment.by_claim_id()[claim.id].status == (
        expected_status
    )


@pytest.mark.parametrize(
    ("section", "selector", "classification", "profile", "expected_kind", "status"),
    (
        (
            "Change",
            "src/service.py",
            "code",
            "production",
            "change",
            "demonstrated",
        ),
        (
            "Selected region",
            "src/service.py",
            "code",
            "production",
            "selected_region",
            "partial",
        ),
        (
            "After topology",
            "src/service.py",
            "code",
            "production",
            "after_topology",
            "partial",
        ),
        (
            "Before topology",
            "src/service.py",
            "code",
            "production",
            "before_topology",
            "partial",
        ),
        (
            "Migration\n### Tests",
            "test_call",
            "test",
            "test",
            "test_migration",
            "partial",
        ),
    ),
)
def test_selected_scalar_structural_facts_reach_claim_aware_assessment(
    section: str,
    selector: str,
    classification: str,
    profile: str,
    expected_kind: str,
    status: str,
) -> None:
    contract, selection, alignment, assessment = _scalar_structural_fixture(
        section,
        selector,
        classification=classification,
        profile=profile,
    )
    claim = contract.by_kind(expected_kind)[0]

    assert selection.matches
    assert alignment.by_claim_id()[claim.id][0].association == (
        "provided_association"
    )
    assert assessment.by_claim_id()[claim.id].status == status


def test_unmatched_repository_path_fails_closed() -> None:
    contract, selection, alignment, assessment = _scalar_structural_fixture(
        "Authority",
        "src/missing.py",
        classification="code",
        profile="production",
    )
    claim = contract.by_kind("authority")[0]

    assert selection.matches == ()
    assert selection.diagnostics[0].state == "no_structural_match"
    assert alignment.by_claim_id().get(claim.id, ()) == ()
    assert assessment.by_claim_id()[claim.id].status == "unverified"


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


def _verification_name_assessment(selector: str, observation_name: str):
    packet = _packet()
    record = packet.source_records[0]
    check = packet.verification_observations[0]
    packet = replace(
        packet,
        source_records=(
            replace(
                record,
                body=(
                    "## Completion conditions\n"
                    f"- The `{selector}` check succeeds.\n"
                ),
            ),
        ),
        verification_observations=(
            replace(check, id="check:canonical", name=observation_name),
        ),
    ).with_revision()
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    claim = brief.transformation_contract.by_kind("completion_condition")[0]
    return brief.transformation_assessment.by_claim_id()[claim.id]


def test_lowercase_check_name_uses_exact_predicate_match() -> None:
    assessment = _verification_name_assessment("test", "test")

    assert assessment.status == "demonstrated"
    assert assessment.predicate_assessments[0].status == "demonstrated"


@pytest.mark.parametrize(
    ("selector", "observation_name"),
    (
        ("Unit Tests", "  UNIT   TESTS  "),
        ("Unit Tests", "Ｕｎｉｔ Tests"),
        ("ci/test", "CI/TEST"),
        ("build-and-test", "BUILD-AND-TEST"),
        ("test_suite", "TEST_SUITE"),
    ),
)
def test_verification_predicate_preserves_canonical_name_equivalence(
    selector: str,
    observation_name: str,
) -> None:
    assessment = _verification_name_assessment(selector, observation_name)

    assert assessment.status == "demonstrated"
    assert assessment.reasons[0].kind == "current_verification_success"


@pytest.mark.parametrize(
    ("selector", "observation_name"),
    (
        ("ci/test", "ci test"),
        ("build-and-test", "build and test"),
        ("suite", "test suite"),
        ("test_suite", "test suite"),
    ),
)
def test_verification_predicate_does_not_collapse_distinct_punctuation(
    selector: str,
    observation_name: str,
) -> None:
    assessment = _verification_name_assessment(selector, observation_name)

    assert assessment.status != "demonstrated"
    assert all(
        reason.kind != "current_verification_success"
        for reason in assessment.reasons
    )


def test_verification_predicate_cannot_borrow_a_shared_name_suffix() -> None:
    packet = _packet()
    record = packet.source_records[0]
    successful = packet.verification_observations[0]
    packet = replace(
        packet,
        source_records=(
            replace(
                record,
                body=(
                    "## Completion conditions\n"
                    "- The `stale_suite` check succeeds.\n"
                ),
            ),
        ),
        verification_observations=(
            replace(successful, id="check:test_suite", name="test_suite"),
            replace(
                successful,
                id="check:stale_suite",
                name="stale_suite",
                head_sha="previous-head",
            ),
        ),
    ).with_revision()

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    claim = brief.transformation_contract.by_kind("completion_condition")[0]
    assessment = brief.transformation_assessment.by_claim_id()[claim.id]

    assert assessment.status == "partial"
    assert assessment.reasons[0].kind == "stale_verification"
    assert len(assessment.supporting_binding_ids) == 1
    binding = next(
        item
        for item in brief.transformation_alignment.bindings
        if item.id == assessment.supporting_binding_ids[0]
    )
    evidence = brief.evidence_catalog.by_id()[binding.evidence_id]
    assert evidence.verification_identity is not None
    assert evidence.verification_identity.name == "stale_suite"


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


def test_related_names_cannot_demonstrate_an_ordered_path() -> None:
    packet = _packet()
    record = packet.source_records[0]
    packet = replace(
        packet,
        source_records=(
            replace(
                record,
                body="## After topology\n- `old_call` → `new_call`.\n",
            ),
        ),
        verification_observations=(),
    ).with_revision()

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    claim = brief.transformation_contract.by_kind("after_topology")[0]
    predicate = brief.transformation_contract.predicates.by_claim_id()[claim.id][0]
    assessment = brief.transformation_assessment.by_claim_id()[claim.id]

    assert predicate.selector_kind == "ordered_path"
    assert assessment.status == "unverified"
    assert assessment.predicate_assessments[0].status == "unverified"
    assert assessment.predicate_assessments[0].supporting_binding_ids == ()


def test_canonical_ordered_path_demonstrates_present_head_predicate() -> None:
    contract, observed, selection, closure, alignment, catalog = (
        _ordered_path_fixture(("Adapter", "Service"))
    )

    assessment = assess_transformation(
        contract,
        alignment,
        catalog,
        closure_scan_plans=ClosureScanPlanSet(),
        head_sha="head123",
        subject_selection=selection,
        structural_closure=closure,
    ).by_claim_id()["T1"]

    assert observed.structural_path_evidence_ids == ("E:path:ordered",)
    assert assessment.status == "demonstrated"
    assert assessment.predicate_assessments[0].status == "demonstrated"
    assert assessment.predicate_assessments[0].supporting_binding_ids == (
        "TAB:T1:E:path:ordered",
    )


def test_canonical_ordered_path_uses_base_revision_for_before_topology() -> None:
    contract, _, selection, closure, alignment, catalog = _ordered_path_fixture(
        ("Adapter", "Service"),
        section="Before topology",
        revision="base",
    )

    assessment = assess_transformation(
        contract,
        alignment,
        catalog,
        closure_scan_plans=ClosureScanPlanSet(),
        head_sha="head123",
        subject_selection=selection,
        structural_closure=closure,
    ).by_claim_id()["T1"]

    assert assessment.status == "demonstrated"
    assert assessment.predicate_assessments[0].expectation == "present_base"


def test_reversed_structural_path_cannot_demonstrate_authored_order() -> None:
    contract, _, selection, closure, alignment, catalog = _ordered_path_fixture(
        ("Service", "Adapter")
    )

    assessment = assess_transformation(
        contract,
        alignment,
        catalog,
        closure_scan_plans=ClosureScanPlanSet(),
        head_sha="head123",
        subject_selection=selection,
        structural_closure=closure,
    ).by_claim_id()["T1"]

    assert assessment.status == "unverified"
    assert assessment.predicate_assessments[0].supporting_binding_ids == ()


def test_verified_ordered_path_requires_current_head_verification() -> None:
    contract, _, selection, closure, alignment, catalog = _ordered_path_fixture(
        ("Adapter", "Service"),
        section="Completion conditions",
    )
    without_verification = assess_transformation(
        contract,
        alignment,
        catalog,
        closure_scan_plans=ClosureScanPlanSet(),
        head_sha="head123",
        subject_selection=selection,
        structural_closure=closure,
    ).by_claim_id()["CC1"]

    assert without_verification.status == "partial"
    assert {item.kind for item in without_verification.reasons} == {
        "exact_fact_observed",
        "verification_incomplete",
    }

    contract, _, selection, closure, alignment, catalog = _ordered_path_fixture(
        ("Adapter", "Service"),
        section="Completion conditions",
        include_verification=True,
    )
    alignment = replace(
        alignment,
        bindings=(
            *alignment.bindings,
            TransformationEvidenceBinding(
                id="TAB:CC1:E:verification:adapter",
                claim_id="CC1",
                evidence_id="E:verification:adapter",
                evidence_role="verification",
                association="provided_association",
                reasons=(
                    AssociationReason(
                        kind="provided_association",
                        detail="Fixture provides exact predicate verification.",
                    ),
                ),
            ),
        ),
    )
    with_verification = assess_transformation(
        contract,
        alignment,
        catalog,
        closure_scan_plans=ClosureScanPlanSet(),
        head_sha="head123",
        subject_selection=selection,
        structural_closure=closure,
    ).by_claim_id()["CC1"]

    assert with_verification.status == "demonstrated"
    assert any(
        item.kind == "current_verification_success"
        for item in with_verification.reasons
    )


def test_deferred_ordered_path_reports_incomplete_coverage() -> None:
    contract, _, selection, _, _, catalog = _ordered_path_fixture(
        ("Adapter", "Service")
    )
    closure = converge_transformation_closure(
        contract,
        selection,
        catalog,
        policy=TransformationClosurePolicy(max_path_identities=0),
    )
    observed = reconstruct_observed_transformation(catalog)
    alignment = build_transformation_alignment(
        contract,
        observed,
        catalog,
        closure,
    )

    assessment = assess_transformation(
        contract,
        alignment,
        catalog,
        closure_scan_plans=ClosureScanPlanSet(),
        head_sha="head123",
        subject_selection=selection,
        structural_closure=closure,
    ).by_claim_id()["T1"]

    assert assessment.status == "partial"
    assert assessment.predicate_assessments[0].reasons[0].kind == (
        "coverage_incomplete"
    )


def test_authority_requires_an_executable_path_to_a_downstream_consumer() -> None:
    contract, selection, closure, alignment, catalog = _authority_fixture()

    assessment = assess_transformation(
        contract,
        alignment,
        catalog,
        ClosureScanPlanSet(),
        head_sha="head123",
        subject_selection=selection,
        structural_closure=closure,
    ).by_claim_id()["T1"]

    assert assessment.status == "demonstrated"
    assert assessment.reasons[0].kind == "authority_path_observed"
    assert assessment.supporting_binding_ids == ("TAB:T1:E:path:authority",)


def test_observed_shared_sink_bypass_contradicts_authority() -> None:
    contract, selection, closure, alignment, catalog = _authority_fixture(
        include_bypass=True,
    )

    assessment = assess_transformation(
        contract,
        alignment,
        catalog,
        ClosureScanPlanSet(),
        head_sha="head123",
        subject_selection=selection,
        structural_closure=closure,
    ).by_claim_id()["T1"]

    assert assessment.status == "contradicted"
    assert assessment.reasons[0].kind == "authority_bypass_observed"
    assert assessment.contradicting_binding_ids == (
        "TAB:T1:E:path:bypass",
    )


def test_non_executable_relation_cannot_demonstrate_authority() -> None:
    contract, selection, closure, alignment, catalog = _authority_fixture(
        relation="imports",
    )

    assessment = assess_transformation(
        contract,
        alignment,
        catalog,
        ClosureScanPlanSet(),
        head_sha="head123",
        subject_selection=selection,
        structural_closure=closure,
    ).by_claim_id()["T1"]

    assert assessment.status == "partial"
    assert assessment.reasons[0].kind == "association_only"


def test_incoming_path_cannot_demonstrate_authority_control() -> None:
    contract, selection, closure, alignment, catalog = _authority_fixture(
        direction="incoming",
    )

    assessment = assess_transformation(
        contract,
        alignment,
        catalog,
        ClosureScanPlanSet(),
        head_sha="head123",
        subject_selection=selection,
        structural_closure=closure,
    ).by_claim_id()["T1"]

    assert assessment.status == "partial"
    assert assessment.reasons[0].kind == "association_only"


def test_deferred_authority_path_preserves_incomplete_coverage() -> None:
    contract, selection, _, _, catalog = _authority_fixture()
    closure = converge_transformation_closure(
        contract,
        selection,
        catalog,
        policy=TransformationClosurePolicy(max_path_identities=0),
    )
    alignment = build_transformation_alignment(
        contract,
        reconstruct_observed_transformation(catalog),
        catalog,
        closure,
    )

    assessment = assess_transformation(
        contract,
        alignment,
        catalog,
        ClosureScanPlanSet(),
        head_sha="head123",
        subject_selection=selection,
        structural_closure=closure,
    ).by_claim_id()["T1"]

    assert assessment.status == "partial"
    assert assessment.reasons[0].kind == "coverage_incomplete"


def test_provider_truncated_authority_path_preserves_incomplete_coverage() -> None:
    contract, selection, closure, alignment, catalog = _authority_fixture(
        traversal_coverage="truncated",
    )

    assessment = assess_transformation(
        contract,
        alignment,
        catalog,
        ClosureScanPlanSet(),
        head_sha="head123",
        subject_selection=selection,
        structural_closure=closure,
    ).by_claim_id()["T1"]

    assert assessment.status == "partial"
    assert {item.kind for item in assessment.reasons} == {
        "authority_path_observed",
        "coverage_incomplete",
    }


def test_authored_uncertainty_for_same_subject_keeps_authority_partial() -> None:
    contract, selection, closure, alignment, catalog = _authority_fixture(
        include_uncertainty=True,
    )

    assessment = assess_transformation(
        contract,
        alignment,
        catalog,
        ClosureScanPlanSet(),
        head_sha="head123",
        subject_selection=selection,
        structural_closure=closure,
    ).by_claim_id()["T1"]

    assert assessment.status == "partial"
    assert {item.kind for item in assessment.reasons} == {
        "authority_path_observed",
        "uncertainty_context",
    }


def _authority_fixture(
    *,
    include_bypass: bool = False,
    relation: str = "calls",
    direction: str = "outgoing",
    traversal_coverage: str = "complete",
    include_uncertainty: bool = False,
):
    contract = extract_review_semantics(
        issue_body=None,
        issue_source=None,
        pr_body=(
            "## Canonical authority\n- `Adapter` is the sole authority.\n"
            + (
                "\n## Uncertainty\n- External behavior around `Adapter` is unknown.\n"
                if include_uncertainty
                else ""
            )
        ),
        pr_source=SourceRef(label="PR #1"),
        pr_title="Prove canonical authority",
    ).transformation_contract
    adapter = _ordered_symbol("adapter", "Adapter", revision="head")
    service = _ordered_symbol("service", "Service", revision="head")
    legacy = _ordered_symbol("legacy", "Legacy", revision="head")
    controlling = _path_item(
        "E:path:authority",
        adapter,
        service,
        relation=relation,
        direction=direction,
        traversal_coverage=traversal_coverage,
    )
    bypass = _bypass_path_item(
        adapter,
        service,
        legacy,
    )
    changed = EvidenceItem(
        id="E:change:adapter",
        summary="Modified Adapter",
        kind="structural_change",
        classification="code",
        profile="production",
        authority="structural_provider",
        revision_side="review",
        operation="modified",
        role="changed_anchor",
        changed=True,
        head_signature=AssociationSignature(identifiers=("adapter",)),
        structural_path_ids=(
            controlling.id,
            *((bypass.id,) if include_bypass else ()),
        ),
        structural_change=StructuralChangeIdentity(review_symbol_id="adapter"),
    )
    catalog = EvidenceCatalog(
        items=(
            changed,
            adapter,
            service,
            controlling,
            *((legacy, bypass) if include_bypass else ()),
        )
    )
    observed = reconstruct_observed_transformation(catalog)
    selection = select_transformation_subjects(contract, observed, catalog)
    closure = converge_transformation_closure(contract, selection, catalog)
    alignment = build_transformation_alignment(
        contract,
        observed,
        catalog,
        closure,
    )
    return contract, selection, closure, alignment, catalog


def _path_item(
    identity: str,
    source: EvidenceItem,
    target: EvidenceItem,
    *,
    relation: str,
    direction: str = "outgoing",
    traversal_coverage: str = "complete",
) -> EvidenceItem:
    return EvidenceItem(
        id=identity,
        summary=f"{source.summary} to {target.summary}",
        kind="structural_path",
        classification="runtime",
        profile="structural_path",
        authority="structural_provider",
        revision_side="head",
        operation="observed",
        role="structural_path",
        structural_path_ids=(identity,),
        structural_traversal_coverage=traversal_coverage,
        metadata={
            "depth": 1,
            "steps": (
                {
                    "source_evidence_id": source.id,
                    "target_evidence_id": target.id,
                    "relation": relation,
                    "direction": direction,
                },
            ),
        },
    )


def _bypass_path_item(
    authority: EvidenceItem,
    sink: EvidenceItem,
    competing_caller: EvidenceItem,
) -> EvidenceItem:
    return EvidenceItem(
        id="E:path:bypass",
        summary="Authority sink reached by a competing caller",
        kind="structural_path",
        classification="runtime",
        profile="structural_path",
        authority="structural_provider",
        revision_side="head",
        operation="observed",
        role="structural_path",
        structural_path_ids=("E:path:bypass",),
        structural_traversal_coverage="complete",
        metadata={
            "depth": 2,
            "steps": (
                {
                    "source_evidence_id": authority.id,
                    "target_evidence_id": sink.id,
                    "relation": "calls",
                    "direction": "outgoing",
                },
                {
                    "source_evidence_id": sink.id,
                    "target_evidence_id": competing_caller.id,
                    "relation": "calls",
                    "direction": "incoming",
                },
            ),
        },
    )


def _ordered_path_fixture(
    path_names: tuple[str, str],
    *,
    section: str = "After topology",
    include_verification: bool = False,
    revision: str = "head",
):
    contract = extract_review_semantics(
        issue_body=None,
        issue_source=None,
        pr_body=f"## {section}\n- `Adapter` → `Service`.\n",
        pr_source=SourceRef(label="PR #1"),
        pr_title="Observe ordered topology",
    ).transformation_contract
    adapter = _ordered_symbol("adapter", "Adapter", revision=revision)
    service = _ordered_symbol("service", "Service", revision=revision)
    symbols = {"Adapter": adapter, "Service": service}
    path = EvidenceItem(
        id="E:path:ordered",
        summary="ordered path",
        kind="structural_path",
        classification="code",
        profile="structural_path",
        authority="structural_provider",
        revision_side=revision,
        operation="observed",
        role="structural_path",
        structural_path_ids=("E:path:ordered",),
        metadata={
            "depth": 1,
            "steps": (
                {
                    "source_evidence_id": symbols[path_names[0]].id,
                    "target_evidence_id": symbols[path_names[1]].id,
                    "relation": "calls",
                    "direction": "outgoing",
                },
            ),
        },
    )
    changed = EvidenceItem(
        id="E:change:adapter",
        summary="Modified Adapter",
        kind="structural_change",
        classification="code",
        profile="production",
        authority="structural_provider",
        revision_side="review",
        operation="modified",
        role="changed_anchor",
        changed=True,
        head_signature=(
            AssociationSignature(identifiers=("adapter",))
            if revision == "head"
            else AssociationSignature()
        ),
        base_signature=(
            AssociationSignature(identifiers=("adapter",))
            if revision == "base"
            else AssociationSignature()
        ),
        structural_path_ids=(path.id,),
        structural_change=StructuralChangeIdentity(review_symbol_id="adapter"),
    )
    verification = EvidenceItem(
        id="E:verification:adapter",
        summary="Adapter: completed/success",
        kind="check_run",
        classification="ci",
        profile="verification",
        authority="verification_provider",
        revision_side="review",
        operation="observed",
        role="verification",
        observed_head_sha="head123",
        verification_identity=VerificationIdentity(
            provider="fixture",
            kind="check_run",
            name="adapter",
        ),
        verification_status="completed",
        verification_conclusion="success",
        head_signature=AssociationSignature(identifiers=("adapter",)),
    )
    catalog = EvidenceCatalog(
        items=(
            changed,
            adapter,
            service,
            path,
            *((verification,) if include_verification else ()),
        )
    )
    observed = reconstruct_observed_transformation(catalog)
    selection = select_transformation_subjects(contract, observed, catalog)
    closure = converge_transformation_closure(contract, selection, catalog)
    alignment = build_transformation_alignment(
        contract,
        observed,
        catalog,
        closure,
    )
    return contract, observed, selection, closure, alignment, catalog


def _scalar_structural_fixture(
    section: str,
    selector: str,
    *,
    classification: str,
    profile: str,
):
    contract = extract_review_semantics(
        issue_body=None,
        issue_source=None,
        pr_body=f"## {section}\n- `{selector}` is changed.\n",
        pr_source=SourceRef(label="PR #1"),
        pr_title="Assess one selected structural fact",
    ).transformation_contract
    normalized_selector = selector.replace("_", "").casefold()
    changed = EvidenceItem(
        id="E:change:selected",
        summary=f"Modified {selector}",
        kind="structural_change",
        classification=classification,
        profile=profile,
        authority="structural_provider",
        revision_side="review",
        operation="modified",
        role="changed_anchor",
        changed=True,
        base_signature=AssociationSignature(
            identifiers=(normalized_selector,),
        ),
        head_signature=AssociationSignature(
            identifiers=(normalized_selector,),
        ),
        structural_change=StructuralChangeIdentity(
            review_symbol_id="selected",
        ),
        metadata={
            "path": "src/service.py",
            "base_path": "src/service.py",
            "head_path": "src/service.py",
        },
    )
    catalog = EvidenceCatalog(items=(changed,))
    observed = reconstruct_observed_transformation(catalog)
    selection = select_transformation_subjects(contract, observed, catalog)
    closure = converge_transformation_closure(contract, selection, catalog)
    alignment = build_transformation_alignment(
        contract,
        observed,
        catalog,
        closure,
    )
    assessment = assess_transformation(
        contract,
        alignment,
        catalog,
        ClosureScanPlanSet(),
        head_sha="head123",
        subject_selection=selection,
        structural_closure=closure,
    )
    return contract, selection, alignment, assessment


def _ordered_symbol(identity: str, name: str, *, revision: str) -> EvidenceItem:
    return EvidenceItem(
        id=f"E:symbol:{identity}",
        summary=name,
        kind="symbol",
        classification="code",
        profile="production",
        authority="structural_provider",
        revision_side=revision,
        operation="unchanged",
        role="runtime_context",
        head_signature=(
            AssociationSignature(identifiers=(identity,))
            if revision == "head"
            else AssociationSignature()
        ),
        base_signature=(
            AssociationSignature(identifiers=(identity,))
            if revision == "base"
            else AssociationSignature()
        ),
        metadata={"review_symbol_id": identity},
    )


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
