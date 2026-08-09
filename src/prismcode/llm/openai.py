from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from prismcode.llm.contracts import (
    MAX_CANDIDATES,
    MAX_SELECTIONS,
    MAX_TEXT_LENGTH,
    MAX_UNRESOLVED_SURFACES,
    SHADOW_SCHEMA_VERSION,
    ShadowEvidenceRequest,
)
from prismcode.llm.provider import (
    ShadowProviderExecutionPolicy,
    ShadowProviderResponse,
)


DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_TIMEOUT_SECONDS = 180.0
DEFAULT_MAX_OUTPUT_TOKENS = 1_200

SHADOW_SELECTION_SYSTEM_PROMPT = """\
Map the authored statement to the admitted repository evidence packet. Treat
candidate admission_tier and association as provenance, not as proof of
relevance or correctness. added_code and removed_code are directional diff
facts; structural_context is bounded reachability context, not proof that a
flow executes or that repository coverage is complete.

Partition every admitted evidence ID exactly once:
- selections: directly relevant evidence. Classify its relationship as
  supporting, contradicting, or context and its semantic role. These roles
  describe evidence-to-claim relation only; they never assess acceptance,
  completion, or mergeability.
- rejected_evidence_ids: evidence demonstrably unrelated to the authored
  statement within the supplied packet.
- insufficient_evidence_ids: evidence whose relevance cannot be determined
  safely because content, identity, direction, or coverage is incomplete or
  ambiguous. Prefer insufficient over rejection when uncertain.

Use only supplied evidence IDs. Do not invent repository facts, infer absence
from missing evidence, or claim coverage beyond coverage_limits. Record missing
dynamic or external surfaces in unresolved_surfaces.

Return exactly one JSON object matching the requested response contract.
"""

JsonTransport = Callable[
    [str, Mapping[str, str], Mapping[str, Any], float], Mapping[str, Any]
]


@dataclass(frozen=True)
class OpenAIShadowConfig:
    api_key: str
    model: str
    base_url: str = DEFAULT_OPENAI_BASE_URL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    api_profile: str = "openai"
    thinking_mode: str = "default"
    reasoning_effort: str = "default"
    thinking_budget: int | None = None

    def __post_init__(self) -> None:
        if not self.api_key.strip() or not self.model.strip():
            raise ValueError("OpenAI shadow api_key and model must be non-empty")
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("OpenAI shadow base_url must be an absolute HTTPS URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError(
                "OpenAI shadow base_url must not contain credentials or query data"
            )
        self.execution_policy

    @property
    def chat_completions_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    @property
    def execution_policy(self) -> ShadowProviderExecutionPolicy:
        return ShadowProviderExecutionPolicy(
            adapter_id="openai-chat-completions",
            model_id=self.model,
            endpoint=self.chat_completions_url,
            timeout_seconds=self.timeout_seconds,
            max_output_tokens=self.max_output_tokens,
            api_profile=self.api_profile,
            thinking_mode=self.thinking_mode,
            reasoning_effort=self.reasoning_effort,
            thinking_budget=self.thinking_budget,
        )


class OpenAIShadowProvider:
    """OpenAI-compatible Chat Completions transport without assessment authority."""

    def __init__(
        self,
        config: OpenAIShadowConfig,
        *,
        transport: JsonTransport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport or _post_json

    @property
    def execution_policy(self) -> ShadowProviderExecutionPolicy:
        return self._config.execution_policy

    def select(self, request: ShadowEvidenceRequest) -> ShadowProviderResponse:
        response = self._transport(
            self._config.chat_completions_url,
            {
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
            },
            _response_payload(request, self._config),
            self._config.timeout_seconds,
        )
        output = _structured_output(response)
        usage = response.get("usage")
        usage = usage if isinstance(usage, Mapping) else {}
        return ShadowProviderResponse(
            provider_id="openai-chat-completions",
            model_id=str(response.get("model") or self._config.model),
            output=output,
            input_tokens=_optional_non_negative_int(usage.get("prompt_tokens")),
            output_tokens=_optional_non_negative_int(usage.get("completion_tokens")),
        )


def _response_payload(
    request: ShadowEvidenceRequest,
    config: OpenAIShadowConfig,
) -> dict[str, Any]:
    payload = {
        "model": config.model,
        "store": False,
        _max_tokens_field(config): config.max_output_tokens,
        "messages": [
            {
                "role": "system",
                "content": SHADOW_SELECTION_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": _user_content(request, config),
            },
        ],
        "response_format": _response_format(request, config),
    }
    if config.api_profile == "siliconflow" and config.thinking_mode != "default":
        payload["enable_thinking"] = config.thinking_mode == "enabled"
    if config.api_profile == "deepseek" and config.thinking_mode != "default":
        payload["thinking"] = {"type": config.thinking_mode}
    if config.reasoning_effort != "default":
        payload["reasoning_effort"] = config.reasoning_effort
    if config.thinking_budget is not None:
        payload["thinking_budget"] = config.thinking_budget
    return payload


def _user_content(
    request: ShadowEvidenceRequest,
    config: OpenAIShadowConfig,
) -> str:
    content: dict[str, Any] = request.to_dict()
    if config.api_profile == "deepseek":
        content = {
            "request": content,
            "required_response_json_schema": _selection_schema(request),
        }
    return json.dumps(content, ensure_ascii=False, separators=(",", ":"))


def _max_tokens_field(config: OpenAIShadowConfig) -> str:
    return (
        "max_tokens"
        if config.api_profile == "deepseek"
        else "max_completion_tokens"
    )


def _response_format(
    request: ShadowEvidenceRequest,
    config: OpenAIShadowConfig,
) -> dict[str, Any]:
    if config.api_profile == "deepseek":
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "prismcode_shadow_evidence_selection",
            "strict": True,
            "schema": _selection_schema(request),
        },
    }


def _selection_schema(request: ShadowEvidenceRequest) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema_version": {
                "type": "string",
                "enum": [SHADOW_SCHEMA_VERSION],
            },
            "request_id": {"type": "string"},
            "subject_id": {"type": "string"},
            "selections": {
                "type": "array",
                "maxItems": MAX_SELECTIONS,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "evidence_id": {
                            "type": "string",
                            "enum": [
                                item.evidence_id for item in request.candidates
                            ],
                        },
                        "role": {
                            "type": "string",
                            "enum": ["supporting", "contradicting", "context"],
                        },
                        "semantic_role": {
                            "type": "string",
                            "enum": [
                                "authority",
                                "producer",
                                "consumer",
                                "path",
                                "test",
                                "removal",
                                "boundary",
                                "documentation",
                                "unknown",
                            ],
                        },
                        "rationale": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": MAX_TEXT_LENGTH,
                        },
                    },
                    "required": [
                        "evidence_id",
                        "role",
                        "semantic_role",
                        "rationale",
                    ],
                },
            },
            "rejected_evidence_ids": _identity_array_schema(request),
            "insufficient_evidence_ids": _identity_array_schema(request),
            "unresolved_surfaces": {
                "type": "array",
                "maxItems": MAX_UNRESOLVED_SURFACES,
                "items": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": MAX_TEXT_LENGTH,
                },
            },
        },
        "required": [
            "schema_version",
            "request_id",
            "subject_id",
            "selections",
            "rejected_evidence_ids",
            "insufficient_evidence_ids",
            "unresolved_surfaces",
        ],
    }


def _identity_array_schema(request: ShadowEvidenceRequest) -> dict[str, Any]:
    return {
        "type": "array",
        "maxItems": MAX_CANDIDATES,
        "uniqueItems": True,
        "items": {
            "type": "string",
            "enum": [item.evidence_id for item in request.candidates],
        },
    }


def _structured_output(response: Mapping[str, Any]) -> Mapping[str, Any]:
    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0]
        message = choice.get("message") if isinstance(choice, Mapping) else None
        if isinstance(message, Mapping):
            if message.get("refusal"):
                raise ValueError("OpenAI shadow response was refused")
            text = message.get("content")
            if isinstance(text, str):
                parsed = json.loads(text)
                if not isinstance(parsed, Mapping):
                    raise ValueError(
                        "OpenAI shadow structured output must be an object"
                    )
                return parsed
    raise ValueError("OpenAI shadow response contained no structured output")


def _optional_non_negative_int(value: object) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


def _post_json(
    url: str,
    headers: Mapping[str, str],
    payload: Mapping[str, Any],
    timeout_seconds: float,
) -> Mapping[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=dict(headers),
        method="POST",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    if not isinstance(parsed, Mapping):
        raise ValueError("OpenAI shadow API response must be an object")
    return parsed
