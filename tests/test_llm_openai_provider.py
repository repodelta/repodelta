from __future__ import annotations

import json
from urllib.error import HTTPError, URLError

import pytest

from prismcode.cli import _openai_shadow_provider_from_env
from prismcode.llm import (
    OpenAIShadowConfig,
    OpenAIShadowProvider,
    ShadowEvidenceCandidate,
    ShadowEvidenceRequest,
    ShadowProviderFailure,
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
                path="src/analyzer.py",
                symbol_kind="function",
                qualified_name="Analyzer",
                added_code="def Analyzer(): ...",
                structural_context=("entry →[calls] Analyzer",),
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
        "rejected_evidence_ids": [],
        "insufficient_evidence_ids": [],
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
    assert "enable_thinking" not in captured["payload"]
    assert "thinking_budget" not in captured["payload"]
    assert captured["payload"]["response_format"]["json_schema"]["strict"] is True
    assert captured["payload"]["response_format"]["json_schema"]["schema"][
        "additionalProperties"
    ] is False
    evidence_schema = captured["payload"]["response_format"]["json_schema"][
        "schema"
    ]["properties"]["selections"]["items"]["properties"]["evidence_id"]
    assert evidence_schema["enum"] == ["symbol:analyzer"]
    request_payload = json.loads(captured["payload"]["messages"][1]["content"])
    assert request_payload["candidates"][0]["added_code"] == "def Analyzer(): ..."
    assert request_payload["candidates"][0]["structural_context"] == [
        "entry →[calls] Analyzer"
    ]
    required = captured["payload"]["response_format"]["json_schema"]["schema"][
        "required"
    ]
    assert "rejected_evidence_ids" in required
    assert "insufficient_evidence_ids" in required
    system_prompt = captured["payload"]["messages"][0]["content"]
    assert "Partition every admitted evidence ID exactly once" in system_prompt
    assert "Prefer insufficient over rejection when uncertain" in system_prompt
    assert "secret-test-key" not in json.dumps(captured["payload"])
    assert response.output["request_id"] == request.request_id
    assert response.input_tokens == 120
    assert response.output_tokens == 40


def test_openai_provider_records_and_sends_explicit_execution_policy() -> None:
    captured = {}
    request = _request()

    def transport(url, headers, payload, timeout):
        captured.update(payload=payload, timeout=timeout)
        return _api_response(request)

    provider = OpenAIShadowProvider(
        OpenAIShadowConfig(
            api_key="secret-test-key",
            model="configured-model",
            base_url="https://models.example/v1",
            timeout_seconds=45.0,
            max_output_tokens=4_096,
            api_profile="siliconflow",
            thinking_mode="enabled",
            thinking_budget=1_024,
        ),
        transport=transport,
    )

    provider.select(request)

    assert captured["timeout"] == 45.0
    assert captured["payload"]["max_completion_tokens"] == 4_096
    assert captured["payload"]["enable_thinking"] is True
    assert captured["payload"]["thinking_budget"] == 1_024
    assert provider.execution_policy.identity.startswith("shadow-policy:")
    assert "secret-test-key" not in json.dumps(
        provider.execution_policy.__dict__
    )


def test_deepseek_profile_maps_neutral_policy_to_provider_payload() -> None:
    captured = {}
    request = _request()

    def transport(url, headers, payload, timeout):
        captured.update(payload=payload)
        return _api_response(request)

    provider = OpenAIShadowProvider(
        OpenAIShadowConfig(
            api_key="secret-test-key",
            model="deepseek-v4-flash",
            base_url="https://api.deepseek.com/v1",
            max_output_tokens=4_096,
            api_profile="deepseek",
            thinking_mode="disabled",
            reasoning_effort="high",
        ),
        transport=transport,
    )

    provider.select(request)

    assert captured["payload"]["max_tokens"] == 4_096
    assert "max_completion_tokens" not in captured["payload"]
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert captured["payload"]["thinking"] == {"type": "disabled"}
    assert captured["payload"]["reasoning_effort"] == "high"
    assert "enable_thinking" not in captured["payload"]
    assert "thinking_budget" not in captured["payload"]
    assert "JSON object" in captured["payload"]["messages"][0]["content"]
    user_content = json.loads(captured["payload"]["messages"][1]["content"])
    assert user_content["request"]["request_id"] == request.request_id
    assert user_content["required_response_json_schema"]["properties"][
        "request_id"
    ]["type"] == "string"
    assert user_content["required_response_json_schema"]["properties"][
        "selections"
    ]["items"]["additionalProperties"] is False


def test_openai_provider_rejects_incomplete_or_missing_output() -> None:
    request = _request()
    provider = OpenAIShadowProvider(
        OpenAIShadowConfig(api_key="key", model="model"),
        transport=lambda *_: {"choices": []},
    )

    with pytest.raises(ShadowProviderFailure) as exc_info:
        provider.select(request)

    assert exc_info.value.kind == "structured_output_missing"


def test_openai_provider_classifies_structured_message_decode_failure() -> None:
    provider = OpenAIShadowProvider(
        OpenAIShadowConfig(api_key="key", model="model"),
        transport=lambda *_: {
            "choices": [{"message": {"content": "{truncated-json"}}]
        },
    )

    with pytest.raises(ShadowProviderFailure) as exc_info:
        provider.select(_request())

    assert exc_info.value.kind == "structured_output_decode_failure"


@pytest.mark.parametrize(
    ("status_code", "expected_kind"),
    (
        (408, "timeout"),
        (413, "request_rejected"),
        (429, "rate_limited"),
        (503, "server_failure"),
    ),
)
def test_openai_transport_classifies_http_failures_without_response_text(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    expected_kind: str,
) -> None:
    def fail(*_args, **_kwargs):
        raise HTTPError(
            "https://models.example/v1/chat/completions",
            status_code,
            "secret provider response text",
            None,
            None,
        )

    monkeypatch.setattr("prismcode.llm.openai.urlopen", fail)
    provider = OpenAIShadowProvider(
        OpenAIShadowConfig(api_key="secret-key", model="model")
    )

    with pytest.raises(ShadowProviderFailure) as exc_info:
        provider.select(_request())

    assert exc_info.value.kind == expected_kind
    assert "secret provider response text" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("reason", "expected_kind"),
    (
        (TimeoutError("secret timeout"), "timeout"),
        (OSError("secret dns"), "network_failure"),
    ),
)
def test_openai_transport_classifies_url_failures_without_reason_text(
    monkeypatch: pytest.MonkeyPatch,
    reason: BaseException,
    expected_kind: str,
) -> None:
    def fail(*_args, **_kwargs):
        raise URLError(reason)

    monkeypatch.setattr("prismcode.llm.openai.urlopen", fail)
    provider = OpenAIShadowProvider(
        OpenAIShadowConfig(api_key="secret-key", model="model")
    )

    with pytest.raises(ShadowProviderFailure) as exc_info:
        provider.select(_request())

    assert exc_info.value.kind == expected_kind
    assert "secret" not in str(exc_info.value)


def test_openai_transport_classifies_response_decode_without_body_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class InvalidResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"secret non-json provider body"

    monkeypatch.setattr(
        "prismcode.llm.openai.urlopen", lambda *_args, **_kwargs: InvalidResponse()
    )
    provider = OpenAIShadowProvider(
        OpenAIShadowConfig(api_key="secret-key", model="model")
    )

    with pytest.raises(ShadowProviderFailure) as exc_info:
        provider.select(_request())

    assert exc_info.value.kind == "transport_response_decode_failure"
    assert "secret non-json provider body" not in str(exc_info.value)


def test_openai_config_rejects_unsafe_base_url() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        OpenAIShadowConfig(
            api_key="key",
            model="model",
            base_url="http://models.example/v1",
        )

    with pytest.raises(ValueError, match="requires api_profile=siliconflow"):
        OpenAIShadowConfig(
            api_key="key",
            model="model",
            api_profile="deepseek",
            thinking_mode="enabled",
            thinking_budget=1_024,
        )


def test_cli_config_requires_explicit_key_and_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "PRISMCODE_LLM_TIMEOUT_SECONDS",
        "PRISMCODE_LLM_MAX_OUTPUT_TOKENS",
        "PRISMCODE_LLM_API_PROFILE",
        "PRISMCODE_LLM_THINKING_MODE",
        "PRISMCODE_LLM_REASONING_EFFORT",
        "PRISMCODE_LLM_THINKING_BUDGET",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("PRISMCODE_LLM_MODEL", "configured-model")
    assert _openai_shadow_provider_from_env() is None

    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    assert _openai_shadow_provider_from_env() is not None


def test_cli_config_rejects_invalid_execution_policy_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.setenv("PRISMCODE_LLM_MODEL", "configured-model")
    monkeypatch.setenv("PRISMCODE_LLM_API_PROFILE", "universal")

    with pytest.raises(ValueError, match="must be one of"):
        _openai_shadow_provider_from_env()

    monkeypatch.setenv("PRISMCODE_LLM_API_PROFILE", "deepseek")
    monkeypatch.setenv("PRISMCODE_LLM_THINKING_MODE", "enabled")
    monkeypatch.setenv("PRISMCODE_LLM_THINKING_BUDGET", "1024")
    with pytest.raises(ValueError, match="requires api_profile=siliconflow"):
        _openai_shadow_provider_from_env()

    monkeypatch.delenv("PRISMCODE_LLM_THINKING_BUDGET")
    monkeypatch.setenv("PRISMCODE_LLM_TIMEOUT_SECONDS", "eventually")
    with pytest.raises(ValueError, match="must be numeric"):
        _openai_shadow_provider_from_env()

    monkeypatch.setenv("PRISMCODE_LLM_TIMEOUT_SECONDS", "0")
    with pytest.raises(ValueError, match="between 0 and 3600"):
        _openai_shadow_provider_from_env()

    monkeypatch.setenv("PRISMCODE_LLM_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("PRISMCODE_LLM_MAX_OUTPUT_TOKENS", "1.5")
    with pytest.raises(ValueError, match="must be an integer"):
        _openai_shadow_provider_from_env()
