from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Status = Literal["verified", "partial", "unresolved", "not_implemented"]


@dataclass(frozen=True)
class SourceRef:
    label: str
    url: str | None = None
    path: str | None = None
    line_start: int | None = None
    line_end: int | None = None


@dataclass(frozen=True)
class Evidence:
    summary: str
    kind: str
    sources: tuple[SourceRef, ...] = ()


@dataclass(frozen=True)
class Requirement:
    id: str
    text: str
    implemented: tuple[Evidence, ...] = ()
    verification: tuple[Evidence, ...] = ()
    gaps: tuple[str, ...] = ()
    status: Status = "unresolved"


@dataclass(frozen=True)
class ReviewInput:
    repository: str
    pull_request: int | None
    title: str
    intent: str
    requirements: tuple[Requirement, ...]
    changed_files: tuple[str, ...] = ()
    source_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReviewBrief:
    review: ReviewInput
    generated_by: str = "prismcode-open-core"
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
