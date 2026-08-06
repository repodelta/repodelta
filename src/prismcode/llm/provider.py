from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from prismcode.llm.contracts import ShadowEvidenceRequest


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

    def select(self, request: ShadowEvidenceRequest) -> ShadowProviderResponse: ...
