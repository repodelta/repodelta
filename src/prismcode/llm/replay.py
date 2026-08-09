from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from prismcode.llm.contracts import (
    ShadowEvidenceRequest,
    ShadowSelectionValidation,
    parse_shadow_selection,
    shadow_candidate_from_mapping,
)
from prismcode.llm.provider import (
    ShadowProviderExecutionPolicy,
    ShadowProviderResponse,
)


@dataclass(frozen=True)
class ReplayShadowProvider:
    """Exact-request replay transport for deterministic orchestration tests."""

    request: ShadowEvidenceRequest
    output: Mapping[str, Any]

    @property
    def execution_policy(self) -> ShadowProviderExecutionPolicy:
        return ShadowProviderExecutionPolicy(
            adapter_id="replay",
            model_id="recorded",
            endpoint="replay:exact-request",
            timeout_seconds=1.0,
            max_output_tokens=1,
        )

    def select(self, request: ShadowEvidenceRequest) -> ShadowProviderResponse:
        if request != self.request:
            raise ValueError("shadow replay request does not match current admission")
        return ShadowProviderResponse(
            provider_id="replay",
            model_id="recorded",
            output=self.output,
        )


def load_shadow_replay_provider(path: str | Path) -> ReplayShadowProvider:
    request, _ = load_shadow_replay(path)
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return ReplayShadowProvider(request=request, output=raw["response"])


def load_shadow_replay(
    path: str | Path,
) -> tuple[ShadowEvidenceRequest, ShadowSelectionValidation]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    request = _parse_request(raw["request"])
    return request, parse_shadow_selection(raw["response"], request)


def serialize_shadow_replay(
    request: ShadowEvidenceRequest, response: Mapping[str, Any]
) -> str:
    return json.dumps(
        {"request": request.to_dict(), "response": response},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _parse_request(raw: Mapping[str, Any]) -> ShadowEvidenceRequest:
    return ShadowEvidenceRequest(
        schema_version=raw.get("schema_version", ""),
        request_id=raw.get("request_id", ""),
        subject_id=raw.get("subject_id", ""),
        subject_kind=raw.get("subject_kind", ""),
        authored_statement=raw.get("authored_statement", ""),
        candidates=tuple(
            shadow_candidate_from_mapping(candidate)
            for candidate in raw.get("candidates", ())
        ),
        coverage_limits=tuple(raw.get("coverage_limits", ())),
    )
