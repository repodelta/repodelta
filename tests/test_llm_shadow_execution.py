from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from prismcode.llm import (
    ShadowProviderResponse,
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
    assert first.read_bytes() == second.read_bytes()
    artifact = json.loads(first.read_text(encoding="utf-8"))
    assert "assessment" not in json.dumps(artifact)


def test_shadow_execution_does_not_mutate_formal_assessment() -> None:
    brief = _brief()
    before = asdict(brief.transformation_assessment)

    execute_shadow_admissions(_admit(brief), BaselineProvider())

    assert asdict(brief.transformation_assessment) == before


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
