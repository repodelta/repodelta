from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import ChangedFile, Diagnostic, Evidence, Requirement, ReviewInput, SourceRef


def _source(value: dict[str, Any]) -> SourceRef:
    return SourceRef(**value)


def _evidence(value: dict[str, Any]) -> Evidence:
    return Evidence(
        summary=value["summary"],
        kind=value["kind"],
        sources=tuple(_source(item) for item in value.get("sources", [])),
    )


def _changed_file(value: str | dict[str, Any]) -> ChangedFile:
    if isinstance(value, str):
        return ChangedFile(path=value)
    return ChangedFile(**value)


def _diagnostic(value: dict[str, Any]) -> Diagnostic:
    return Diagnostic(
        code=value["code"],
        message=value["message"],
        severity=value.get("severity", "warning"),
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
                sources=tuple(_source(x) for x in item.get("sources", [])),
            )
        )
    return ReviewInput(
        repository=raw["repository"],
        pull_request=raw.get("pull_request"),
        title=raw["title"],
        intent=raw["intent"],
        requirements=tuple(requirements),
        changed_files=tuple(_changed_file(item) for item in raw.get("changed_files", [])),
        source_url=raw.get("source_url"),
        diagnostics=tuple(_diagnostic(item) for item in raw.get("diagnostics", [])),
        metadata=raw.get("metadata", {}),
    )
