from __future__ import annotations

from dataclasses import replace

from repodelta.llm import ShadowAdmissionPolicy, admit_shadow_candidates
from repodelta.model.contracts import (
    AnalysisInput,
    ChangedFile,
    ReviewSourcePacket,
    SourceRecord,
    VerificationObservation,
)
from repodelta.pipeline import DeterministicAnalyzer
from repodelta.routing.transformation import eligible_transformation_evidence


def _brief(body: str | None = None):
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=12,
        title="Admit shadow candidates",
        source_records=(
            SourceRecord(
                id="pr:12",
                kind="pull_request",
                repository="acme/widget",
                title="Admit shadow candidates",
                body=body
                or (
                    "## Change\n- Replace `old_call` with `new_call`.\n\n"
                    "## After topology\n- `new_call` is canonical.\n\n"
                    "## Removal\n- Remove `old_call`.\n\n"
                    "## Completion conditions\n- `test_suite` succeeds.\n\n"
                    "## Uncertainty\n- External deployment is unknown.\n"
                ),
            ),
        ),
        changed_files=(
            ChangedFile(
                base_path="src/service.py",
                head_path="src/service.py",
                patch="@@ -1 +1 @@\n-old_call()\n+new_call()\n",
            ),
            ChangedFile(
                base_path="src/unrelated.py",
                head_path="src/unrelated.py",
                patch="@@ -1 +1 @@\n-old_extra()\n+new_extra()\n",
            ),
        ),
        verification_observations=(
            VerificationObservation(
                id="check:test_suite",
                name="test_suite",
                kind="check_run",
                status="completed",
                conclusion="success",
                head_sha="head123",
                provider="github",
            ),
        ),
        head_sha="head123",
    ).with_revision()
    return DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))


def _admit(brief, *, policy=ShadowAdmissionPolicy()):
    return admit_shadow_candidates(
        brief.transformation_contract,
        brief.observed_transformation,
        brief.evidence_catalog,
        brief.transformation_alignment,
        brief.transformation_assessment,
        policy=policy,
    )


def test_admission_is_stable_and_excludes_unrelated_changed_anchors() -> None:
    brief = _brief()

    first = _admit(brief)
    second = _admit(brief)
    claim = brief.transformation_contract.by_kind("change")[0]
    admission = first.by_claim_id()[claim.id]

    assert first == second
    assert admission.state == "ready"
    assert admission.request is not None
    candidate_ids = tuple(item.evidence_id for item in admission.request.candidates)
    assert set(admission.deterministic_evidence_ids) <= set(candidate_ids)
    assert admission.deterministic_evidence_ids == ()
    assert admission.request.request_id.startswith(f"shadow:{claim.id}:")
    changed = next(
        item
        for item in admission.request.candidates
        if item.kind == "change_relation"
    )
    assert changed.admission_tier == "identifier"
    assert changed.association == "exact_identifier"
    assert changed.path == "src/service.py"
    assert changed.classification == "code"
    assert changed.profile == "production"
    assert changed.authority == "github_diff"
    assert changed.added_code == "new_call()"
    assert changed.removed_code == "old_call()"


def test_completion_admission_includes_typed_verification_baseline() -> None:
    brief = _brief()
    claim = brief.transformation_contract.by_kind("completion_condition")[0]
    admission = _admit(brief).by_claim_id()[claim.id]
    evidence = brief.evidence_catalog.by_id()

    assert admission.request is not None
    selected = tuple(
        evidence[item.evidence_id] for item in admission.request.candidates
    )
    assert any(item.role == "verification" for item in selected)
    assert set(admission.deterministic_evidence_ids) <= {
        item.id for item in selected
    }


def test_uncertainty_does_not_create_a_model_request() -> None:
    brief = _brief()
    claim = brief.transformation_contract.by_kind("uncertainty")[0]
    admission = _admit(brief).by_claim_id()[claim.id]

    assert admission.state == "empty"
    assert admission.request is None
    assert admission.diagnostics[0].code == "shadow_admission_not_applicable"


def test_generic_transition_states_enter_only_shadow_evidence_selection() -> None:
    brief = _brief(
        "## Before\n- `old_call` controlled the result.\n\n"
        "## After\n- `new_call` controls the result.\n"
    )
    admissions = _admit(brief).by_claim_id()

    assert set(admissions) == {"T1", "T2"}
    assert all(item.state == "ready" for item in admissions.values())
    assert all(item.request is not None for item in admissions.values())
    assert all(not item.deterministic_evidence_ids for item in admissions.values())
    assert all(item.request.candidates for item in admissions.values())

    evidence = brief.evidence_catalog.by_id()
    for claim in brief.transformation_contract.claims:
        assert all(
            not eligible_transformation_evidence(
                claim,
                evidence[candidate.evidence_id],
            )
            for candidate in admissions[claim.id].request.candidates
        )


def test_admission_truncates_only_after_preserving_baseline() -> None:
    brief = _brief("## Change\n- Update service behavior.\n")
    claim = brief.transformation_contract.by_kind("change")[0]
    admission = _admit(
        brief, policy=ShadowAdmissionPolicy(max_candidates=1)
    ).by_claim_id()[claim.id]

    assert admission.state == "ready_truncated"
    assert admission.request is not None
    assert admission.deterministic_evidence_ids == ()
    assert len(admission.request.candidates) == 1
    assert admission.request.candidates[0].admission_tier == "fallback"
    assert admission.request.coverage_limits


def test_multiple_lexical_anchors_remain_shadow_candidates_without_direct_proof() -> None:
    brief = _brief("## Change\n- Update `old_call` and `old_extra`.\n")
    claim = brief.transformation_contract.by_kind("change")[0]

    admission = _admit(brief).by_claim_id()[claim.id]

    assert admission.request is not None
    assert len(admission.request.candidates) == 2
    assert admission.deterministic_evidence_ids == ()


def test_admission_canonicalizes_baseline_to_request_candidate_order() -> None:
    brief = _brief("## Change\n- Update `old_call` and `old_extra`.\n")
    claim = brief.transformation_contract.by_kind("change")[0]
    assessment = brief.transformation_assessment.by_claim_id()[claim.id]
    assert assessment.supporting_binding_ids == ()
    reversed_assessment = replace(
        brief.transformation_assessment,
        claims=tuple(
            replace(
                item,
                supporting_binding_ids=tuple(
                    reversed(item.supporting_binding_ids)
                ),
            )
            if item.claim_id == claim.id
            else item
            for item in brief.transformation_assessment.claims
        ),
    )
    brief = replace(
        brief,
        transformation_assessment=reversed_assessment,
    )

    admission = _admit(brief).by_claim_id()[claim.id]

    assert admission.request is not None
    assert admission.deterministic_evidence_ids == ()


def test_admission_blocks_when_baseline_itself_exceeds_budget() -> None:
    brief = _brief("## Change\n- Update `old_call` and `old_extra`.\n")
    claim = brief.transformation_contract.by_kind("change")[0]
    admission = _admit(
        brief, policy=ShadowAdmissionPolicy(max_candidates=1)
    ).by_claim_id()[claim.id]

    assert admission.deterministic_evidence_ids == ()
    assert admission.state == "ready_truncated"
    assert admission.request is not None
    assert len(admission.request.candidates) == 1
