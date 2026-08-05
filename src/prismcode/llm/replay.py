from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from prismcode.llm.contracts import (
    ShadowEvidenceCandidate,
    ShadowEvidenceRequest,
    ShadowSelectionValidation,
    parse_shadow_selection,
)


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
            ShadowEvidenceCandidate(
                evidence_id=candidate.get("evidence_id", ""),
                summary=candidate.get("summary", ""),
                kind=candidate.get("kind", ""),
                revision_side=candidate.get("revision_side", "none"),
                operation=candidate.get("operation", "context"),
            )
            for candidate in raw.get("candidates", ())
        ),
        coverage_limits=tuple(raw.get("coverage_limits", ())),
    )
