from __future__ import annotations

import json

import pytest

from prismcode.cli import _openai_shadow_provider_from_env
from prismcode.llm import (
    OpenAIShadowConfig,
    OpenAIShadowProvider,
    ShadowEvidenceCandidate,
    ShadowEvidenceRequest,
)


def _request() -> ShadowEvidenceRequest:
    return ShadowEvidenceRequest(
        request_id="shadow:T1:abc",
        subject_id="T1",
        subject_kind="change",
        authored_statement="Move authority to Analyzer.",
        candidates=(
            ShadowEvidenceCandidate(
                evidence_id="symbol:analyzer",
                summary="Changed function Analyzer",
                kind="changed_symbol",
                revision_side="head",
                operation="added",
            ),
        ),
    )


def _api_response(request: ShadowEvidenceRequest) -> dict:
    output = {
        "schema_version": request.schema_version,
        "request_id": request.request_id,
        "subject_id": request.subject_id,
        "selections": [
            {
                "evidence_id": "symbol:analyzer",
                "role": "supporting",
                "semantic_role": "authority",
                "rationale": "The changed authority symbol is relevant.",
            }
        ],
        "unresolved_surfaces": [],
    }
    return {
        "model": "configured-model",
        "choices": [
            {
                "message": {"content": json.dumps(output)},
            }
        ],
        "usage": {"prompt_tokens": 120, "completion_tokens": 40},
    }


def test_openai_provider_uses_bounded_strict_responses_contract() -> None:
    captured = {}
    request = _request()

    def transport(url, headers, payload, timeout):
        captured.update(
            url=url,
            headers=headers,
            payload=payload,
            timeout=timeout,
        )
        return _api_response(request)

    provider = OpenAIShadowProvider(
        OpenAIShadowConfig(
            api_key="secret-test-key",
            model="configured-model",
            base_url="https://models.example/v1",
        ),
        transport=transport,
    )

    response = provider.select(request)

    assert captured["url"] == "https://models.example/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer secret-test-key"
    assert captured["payload"]["store"] is False
    assert captured["payload"]["response_format"]["json_schema"]["strict"] is True
    assert captured["payload"]["response_format"]["json_schema"]["schema"][
        "additionalProperties"
    ] is False
    evidence_schema = captured["payload"]["response_format"]["json_schema"][
        "schema"
    ]["properties"]["selections"]["items"]["properties"]["evidence_id"]
    assert evidence_schema["enum"] == ["symbol:analyzer"]
    assert "secret-test-key" not in json.dumps(captured["payload"])
    assert response.output["request_id"] == request.request_id
    assert response.input_tokens == 120
    assert response.output_tokens == 40


def test_openai_provider_rejects_incomplete_or_missing_output() -> None:
    request = _request()
    provider = OpenAIShadowProvider(
        OpenAIShadowConfig(api_key="key", model="model"),
        transport=lambda *_: {"choices": []},
    )

    with pytest.raises(ValueError, match="no structured output"):
        provider.select(request)


def test_openai_config_rejects_unsafe_base_url() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        OpenAIShadowConfig(
            api_key="key",
            model="model",
            base_url="http://models.example/v1",
        )


def test_cli_config_requires_explicit_key_and_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("PRISMCODE_LLM_MODEL", "configured-model")
    assert _openai_shadow_provider_from_env() is None

    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    assert _openai_shadow_provider_from_env() is not None
