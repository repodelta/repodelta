from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import Evidence, Requirement, ReviewInput, SourceRef


def _source(value: dict[str, Any]) -> SourceRef:
    return SourceRef(**value)


def _evidence(value: dict[str, Any]) -> Evidence:
    return Evidence(
        summary=value["summary"],
        kind=value["kind"],
        sources=tuple(_source(item) for item in value.get("sources", [])),
    )


def load_fixture(path: str | Path) -> ReviewInput:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    requirements = []
    for item in raw.get("requirements", []):
        requirements.append(
            Requirement(
                id=item["id"],
                text=item["text"],
                implemented=tuple(_evidence(x) for x in item.get("implemented", [])),
                verification=tuple(_evidence(x) for x in item.get("verification", [])),
                gaps=tuple(item.get("gaps", [])),
                status=item.get("status", "unresolved"),
            )
        )
    return ReviewInput(
        repository=raw["repository"],
        pull_request=raw.get("pull_request"),
        title=raw["title"],
        intent=raw["intent"],
        requirements=tuple(requirements),
        changed_files=tuple(raw.get("changed_files", [])),
        source_url=raw.get("source_url"),
        metadata=raw.get("metadata", {}),
    )
