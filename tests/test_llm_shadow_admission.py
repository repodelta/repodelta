from __future__ import annotations

from prismcode.llm import ShadowAdmissionPolicy, admit_shadow_candidates
from prismcode.model.contracts import (
    AnalysisInput,
    ChangedFile,
    ReviewSourcePacket,
    SourceRecord,
    VerificationObservation,
)
from prismcode.pipeline import DeterministicAnalyzer


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


def test_admission_is_stable_and_wider_than_deterministic_association() -> None:
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
    assert len(candidate_ids) > len(admission.deterministic_evidence_ids)
    assert admission.request.request_id.startswith(f"shadow:{claim.id}:")


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


def test_admission_truncates_only_after_preserving_baseline() -> None:
    brief = _brief()
    claim = brief.transformation_contract.by_kind("change")[0]
    admission = _admit(
        brief, policy=ShadowAdmissionPolicy(max_candidates=1)
    ).by_claim_id()[claim.id]

    assert admission.state == "ready_truncated"
    assert admission.request is not None
    assert tuple(
        item.evidence_id for item in admission.request.candidates
    ) == admission.deterministic_evidence_ids
    assert admission.request.coverage_limits


def test_admission_blocks_when_baseline_itself_exceeds_budget() -> None:
    brief = _brief("## Change\n- Update `old_call` and `old_extra`.\n")
    claim = brief.transformation_contract.by_kind("change")[0]
    admission = _admit(
        brief, policy=ShadowAdmissionPolicy(max_candidates=1)
    ).by_claim_id()[claim.id]

    assert len(admission.deterministic_evidence_ids) > 1
    assert admission.state == "blocked"
    assert admission.request is None
    assert admission.diagnostics[0].code == "shadow_admission_baseline_over_budget"
