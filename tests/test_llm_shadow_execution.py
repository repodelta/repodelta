from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import pytest

from prismcode.llm import (
    ShadowAdmissionDiagnostic,
    ShadowCandidateAdmission,
    ShadowCandidateAdmissionSet,
    ShadowProviderResponse,
    ShadowExecutionPolicy,
    admit_shadow_candidates,
    execute_shadow_admissions,
    write_shadow_execution,
)
from prismcode.model.contracts import (
    AnalysisInput,
    ChangedFile,
    ReviewSourcePacket,
    SourceRecord,
)
from prismcode.pipeline import DeterministicAnalyzer


@dataclass
class BaselineProvider:
    calls: int = 0

    def select(self, request):
        self.calls += 1
        evidence_id = request.candidates[0].evidence_id
        return ShadowProviderResponse(
            provider_id="test",
            model_id="recorded",
            output={
                "schema_version": request.schema_version,
                "request_id": request.request_id,
                "subject_id": request.subject_id,
                "selections": [
                    {
                        "evidence_id": evidence_id,
                        "role": "supporting",
                        "semantic_role": "unknown",
                        "rationale": "Recorded bounded selection.",
                    }
                ],
                "unresolved_surfaces": [],
            },
        )


class FailingProvider:
    def select(self, request):
        raise RuntimeError("secret provider detail")


def test_execution_runs_ready_admissions_once_and_writes_stable_artifact(
    tmp_path: Path,
) -> None:
    brief = _brief()
    admissions = _admit(brief)
    provider = BaselineProvider()

    bundle = execute_shadow_admissions(admissions, provider)
    first = write_shadow_execution(bundle, tmp_path / "first.json")
    second = write_shadow_execution(bundle, tmp_path / "second.json")

    ready_count = sum(item.request is not None for item in admissions.admissions)
    assert provider.calls == ready_count
    assert bundle.summary.state == "completed"
    assert bundle.summary.admitted_count == ready_count
    assert tuple(item.claim_id for item in bundle.observations) == tuple(
        item.claim_id for item in admissions.admissions
    )
    assert all(item.execution_state == "accepted" for item in bundle.observations)
    assert all(item.request is not None for item in bundle.observations)
    assert all(item.run is not None for item in bundle.observations)
    assert first.read_bytes() == second.read_bytes()
    artifact = json.loads(first.read_text(encoding="utf-8"))
    assert "assessment" not in json.dumps(artifact)
    assert artifact["schema_version"] == "llm_shadow_execution.v2"
    assert artifact["observations"][0]["request"]["candidates"]
    assert artifact["observations"][0]["run"]["comparison"] is not None


def test_shadow_execution_does_not_mutate_formal_assessment() -> None:
    brief = _brief()
    before = asdict(brief.transformation_assessment)

    execute_shadow_admissions(_admit(brief), BaselineProvider())

    assert asdict(brief.transformation_assessment) == before


def test_provider_failure_remains_an_observation_without_sensitive_text() -> None:
    bundle = execute_shadow_admissions(_admit(_brief()), FailingProvider())

    assert bundle.summary.state == "failed"
    assert all(
        item.execution_state == "provider_error" for item in bundle.observations
    )
    assert all(item.run is not None for item in bundle.observations)
    assert "secret" not in json.dumps(bundle.to_dict())


def test_execution_budget_defers_whole_requests_without_silent_loss() -> None:
    brief = _brief()
    admissions = _admit(brief)
    ready_count = sum(item.request is not None for item in admissions.admissions)
    assert ready_count > 1
    provider = BaselineProvider()

    bundle = execute_shadow_admissions(
        admissions,
        provider,
        policy=ShadowExecutionPolicy(max_requests=1),
    )

    assert provider.calls == 1
    assert bundle.summary.state == "partial"
    assert bundle.summary.admitted_count == ready_count
    assert bundle.summary.deferred_count == ready_count - 1
    deferred = tuple(
        item for item in bundle.observations if item.execution_state == "deferred"
    )
    assert len(deferred) == ready_count - 1
    assert all(item.request is not None and item.run is None for item in deferred)
    assert all(
        item.diagnostics[-1].code == "shadow_execution_budget_deferred"
        for item in deferred
    )


def test_blocked_and_empty_admissions_remain_typed_observations() -> None:
    admissions = ShadowCandidateAdmissionSet(
        admissions=(
            ShadowCandidateAdmission(
                claim_id="T1",
                state="blocked",
                eligible_count=101,
                diagnostics=(
                    ShadowAdmissionDiagnostic(
                        code="shadow_admission_baseline_over_budget",
                        message="Baseline exceeds the request budget.",
                    ),
                ),
            ),
            ShadowCandidateAdmission(
                claim_id="T2",
                state="empty",
                eligible_count=0,
                diagnostics=(
                    ShadowAdmissionDiagnostic(
                        code="shadow_admission_no_eligible_fact",
                        message="No eligible fact.",
                    ),
                ),
            ),
        )
    )
    provider = BaselineProvider()

    bundle = execute_shadow_admissions(admissions, provider)

    assert provider.calls == 0
    assert bundle.summary.state == "partial"
    assert tuple(item.execution_state for item in bundle.observations) == (
        "blocked",
        "empty",
    )
    assert all(item.request is None and item.run is None for item in bundle.observations)
    assert tuple(item.diagnostics[0].code for item in bundle.observations) == (
        "shadow_admission_baseline_over_budget",
        "shadow_admission_no_eligible_fact",
    )

    with pytest.raises(ValueError, match="derive from observations"):
        replace(
            bundle,
            summary=replace(bundle.summary, completed_count=1),
        )


def _brief():
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=12,
        title="Run shadow selection",
        source_records=(
            SourceRecord(
                id="pr:12",
                kind="pull_request",
                repository="acme/widget",
                title="Run shadow selection",
                body=(
                    "## Change\n- Replace `old_call` with `new_call`.\n\n"
                    "## Completion conditions\n- `test_suite` succeeds.\n"
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
    ).with_revision()
    return DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))


def _admit(brief):
    return admit_shadow_candidates(
        brief.transformation_contract,
        brief.observed_transformation,
        brief.evidence_catalog,
        brief.transformation_alignment,
        brief.transformation_assessment,
    )
