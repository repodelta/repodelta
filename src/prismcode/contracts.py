from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Status = Literal["verified", "partial", "unresolved", "not_implemented"]
DiagnosticSeverity = Literal["info", "warning", "error"]


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
    sources: tuple[SourceRef, ...] = ()


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str = "modified"
    additions: int | None = None
    deletions: int | None = None
    changes: int | None = None
    source_url: str | None = None
    patch: str | None = None


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    severity: DiagnosticSeverity = "warning"
    sources: tuple[SourceRef, ...] = ()


@dataclass(frozen=True)
class ReviewInput:
    repository: str
    pull_request: int | None
    title: str
    intent: str
    requirements: tuple[Requirement, ...]
    changed_files: tuple[ChangedFile, ...] = ()
    source_url: str | None = None
    diagnostics: tuple[Diagnostic, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReviewBrief:
    review: ReviewInput
    generated_by: str = "prismcode-open-core"
    schema_version: str = "1.1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
