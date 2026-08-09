from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from prismcode.llm.contracts import ShadowEvidenceRequest


@dataclass(frozen=True)
class ShadowProviderExecutionPolicy:
    """Non-secret transport settings that make one observation reproducible."""

    adapter_id: str
    model_id: str
    endpoint: str
    timeout_seconds: float
    max_output_tokens: int
    api_profile: str = "openai"
    thinking_mode: str = "default"
    reasoning_effort: str = "default"
    thinking_budget: int | None = None
    identity: str = ""

    def __post_init__(self) -> None:
        for name in ("adapter_id", "model_id", "endpoint"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"shadow execution policy {name} must be non-empty")
        if not 0 < self.timeout_seconds <= 3_600:
            raise ValueError(
                "shadow execution policy timeout_seconds must be between 0 and 3600"
            )
        if not 1 <= self.max_output_tokens <= 100_000:
            raise ValueError(
                "shadow execution policy max_output_tokens must be between 1 and 100000"
            )
        if self.api_profile not in {"openai", "siliconflow", "deepseek"}:
            raise ValueError(
                "shadow execution policy api_profile must be openai, "
                "siliconflow, or deepseek"
            )
        if self.thinking_mode not in {"default", "enabled", "disabled"}:
            raise ValueError(
                "shadow execution policy thinking_mode must be default, "
                "enabled, or disabled"
            )
        if self.reasoning_effort not in {"default", "high", "max"}:
            raise ValueError(
                "shadow execution policy reasoning_effort must be default, "
                "high, or max"
            )
        if self.thinking_budget is not None:
            if self.api_profile != "siliconflow":
                raise ValueError(
                    "shadow execution policy thinking_budget requires "
                    "api_profile=siliconflow"
                )
            if self.thinking_mode != "enabled":
                raise ValueError(
                    "shadow execution policy thinking_budget requires "
                    "thinking_mode=enabled"
                )
            if not 128 <= self.thinking_budget <= 32_768:
                raise ValueError(
                    "shadow execution policy thinking_budget must be between 128 and 32768"
                )
        expected = self.derived_identity()
        if self.identity and self.identity != expected:
            raise ValueError(
                "shadow execution policy identity must derive from settings"
            )
        object.__setattr__(self, "identity", expected)

    def derived_identity(self) -> str:
        payload = {
            "adapter_id": self.adapter_id,
            "model_id": self.model_id,
            "endpoint": self.endpoint,
            "timeout_seconds": self.timeout_seconds,
            "max_output_tokens": self.max_output_tokens,
            "api_profile": self.api_profile,
            "thinking_mode": self.thinking_mode,
            "reasoning_effort": self.reasoning_effort,
            "thinking_budget": self.thinking_budget,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return f"shadow-policy:{digest[:20]}"


@dataclass(frozen=True)
class ShadowProviderResponse:
    """Untrusted model-shaped output plus non-semantic usage metadata."""

    provider_id: str
    model_id: str
    output: Mapping[str, Any]
    input_tokens: int | None = None
    output_tokens: int | None = None

    def __post_init__(self) -> None:
        if not self.provider_id.strip() or not self.model_id.strip():
            raise ValueError("provider_id and model_id must be non-empty")
        for name in ("input_tokens", "output_tokens"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")


class ShadowEvidenceProvider(Protocol):
    """Port for a model invocation; implementations own transport only."""

    @property
    def execution_policy(self) -> ShadowProviderExecutionPolicy: ...

    def select(self, request: ShadowEvidenceRequest) -> ShadowProviderResponse: ...
