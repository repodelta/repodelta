from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from .contracts import Diagnostic, SourceRef
from .diff_hunks import ChangedHunk

IndexState = Literal["available", "partial", "missing", "stale", "invalid", "error"]


@dataclass(frozen=True)
class StructuralGraphIndexStatus:
    state: IndexState
    provider: str
    revision: str = ""
    database_path: str = ""
    indexed_files: int = 0
    requested_files: int = 0
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def usable(self) -> bool:
        return self.state in {"available", "partial"}


@dataclass(frozen=True)
class GraphSymbol:
    id: str
    kind: str
    name: str
    qualified_name: str
    file_path: str
    language: str
    start_line: int
    end_line: int
    sources: tuple[SourceRef, ...] = ()


@dataclass(frozen=True)
class HunkSymbolOverlap:
    hunk_id: str
    symbol: GraphSymbol
    changed_lines: tuple[int, ...]
    sources: tuple[SourceRef, ...] = ()


@dataclass(frozen=True)
class StructuralGraphResult:
    index: StructuralGraphIndexStatus
    overlaps: tuple[HunkSymbolOverlap, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()


@runtime_checkable
class StructuralGraphProvider(Protocol):
    """Read-only structural facts. Providers never produce review conclusions."""

    def inspect_index(
        self, *, requested_files: tuple[str, ...] = ()
    ) -> StructuralGraphIndexStatus: ...

    def symbols_overlapping(
        self, hunks: tuple[ChangedHunk, ...]
    ) -> StructuralGraphResult: ...
