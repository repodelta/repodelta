from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from repodelta.llm import (
    ShadowEvidenceRequest,
    ShadowProviderExecutionPolicy,
    ShadowProviderFailure,
    ShadowProviderResponse,
    ShadowRunner,
    load_shadow_replay,
)


FIXTURE = "fixtures/llm-shadow/evidence-selection.json"


@dataclass
class ReplayProvider:
    output: dict

    @property
    def execution_policy(self) -> ShadowProviderExecutionPolicy:
        return _test_policy()

    def select(self, request: ShadowEvidenceRequest) -> ShadowProviderResponse:
        return ShadowProviderResponse(
            provider_id="replay",
            model_id="fixture-v1",
            output=self.output,
            input_tokens=120,
            output_tokens=40,
        )


class FailingProvider:
    @property
    def execution_policy(self) -> ShadowProviderExecutionPolicy:
        return _test_policy()

    def select(self, request: ShadowEvidenceRequest) -> ShadowProviderResponse:
        raise RuntimeError("credential and response details remain private")


@dataclass
class ClassifiedFailingProvider:
    kind: str

    @property
    def execution_policy(self) -> ShadowProviderExecutionPolicy:
        return _test_policy()

    def select(self, request: ShadowEvidenceRequest) -> ShadowProviderResponse:
        raise ShadowProviderFailure(self.kind)


def test_runner_measures_deterministic_shadow_divergence() -> None:
    request, output = _fixture_pair()
    clock = iter((10.0, 10.025)).__next__

    record = ShadowRunner(ReplayProvider(output), clock=clock).measure_selection(
        request, deterministic_evidence_ids=("symbol:analyzer",)
    )

    assert record.state == "accepted"
    assert record.provider_id == "replay"
    assert record.model_id == "fixture-v1"
    assert record.input_tokens == 120
    assert record.output_tokens == 40
    assert record.duration_ms == pytest.approx(25)
    assert record.execution_policy.identity.startswith("shadow-policy:")
    assert record.comparison is not None
    assert record.comparison.shared_ids == ("symbol:analyzer",)
    assert record.comparison.deterministic_only_ids == ()
    assert record.comparison.shadow_only_ids == ("symbol:adapter",)


def test_runner_rejects_model_output_without_changing_deterministic_ids() -> None:
    request, raw = _fixture_pair()
    raw["selections"][0]["evidence_id"] = "invented:model-fact"

    record = ShadowRunner(ReplayProvider(raw)).measure_selection(
        request, deterministic_evidence_ids=("symbol:analyzer",)
    )

    assert record.state == "invalid_output"
    assert record.selection is None
    assert record.comparison is None
    assert "unknown_evidence_id" in {item.code for item in record.diagnostics}


def test_runner_isolates_provider_failure_and_sensitive_error_text() -> None:
    request, _ = load_shadow_replay(FIXTURE)

    record = ShadowRunner(FailingProvider()).measure_selection(
        request, deterministic_evidence_ids=("symbol:analyzer",)
    )

    assert record.state == "provider_error"
    assert record.selection is None
    assert record.comparison is None
    assert record.provider_id is None
    assert "credential" not in record.diagnostics[0].message


@pytest.mark.parametrize(
    "kind",
    (
        "timeout",
        "network_failure",
        "rate_limited",
        "request_rejected",
        "server_failure",
        "transport_response_decode_failure",
        "structured_output_decode_failure",
        "structured_output_missing",
    ),
)
def test_runner_persists_only_sanitized_provider_failure_category(
    kind: str,
) -> None:
    request, _ = load_shadow_replay(FIXTURE)

    record = ShadowRunner(ClassifiedFailingProvider(kind)).measure_selection(
        request, deterministic_evidence_ids=("symbol:analyzer",)
    )

    assert record.state == "provider_error"
    assert record.diagnostics[0].code == f"shadow_provider_{kind}"
    assert "secret" not in record.diagnostics[0].message.lower()


def test_provider_failure_rejects_unknown_persisted_category() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        ShadowProviderFailure("provider_secret_detail")


def test_deterministic_baseline_must_use_admitted_identity() -> None:
    request, output = _fixture_pair()

    with pytest.raises(ValueError, match="admitted"):
        ShadowRunner(ReplayProvider(output)).measure_selection(
            request, deterministic_evidence_ids=("invented:baseline",)
        )


def test_run_record_has_no_formal_assessment_or_pipeline_authority() -> None:
    request, output = _fixture_pair()

    record = ShadowRunner(ReplayProvider(output)).measure_selection(
        request, deterministic_evidence_ids=()
    )

    assert not hasattr(record, "assessment")
    assert not hasattr(record, "status")


def _fixture_pair() -> tuple[ShadowEvidenceRequest, dict]:
    request, validation = load_shadow_replay(FIXTURE)
    assert validation.accepted
    raw = json.loads(Path(FIXTURE).read_text(encoding="utf-8"))
    return request, raw["response"]


def _test_policy() -> ShadowProviderExecutionPolicy:
    return ShadowProviderExecutionPolicy(
        adapter_id="test-replay",
        model_id="fixture-v1",
        endpoint="test:local",
        timeout_seconds=1.0,
        max_output_tokens=1,
    )
