from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from .contracts import Diagnostic, SourceRef
from .diff_hunks import ChangedHunk

IndexState = Literal["available", "partial", "missing", "stale", "invalid", "error"]
PathClassification = Literal["runtime", "test", "mixed"]
TraversalDirection = Literal["outgoing", "incoming"]


@dataclass(frozen=True)
class StructuralTraversalPolicy:
    """Deterministic safety budget for provider-owned graph expansion."""

    max_depth: int = 3
    max_nodes: int = 80
    max_paths: int = 120
    relation_allowlist: tuple[str, ...] = (
        "calls",
        "imports",
        "instantiates",
        "references",
        "extends",
    )


@dataclass(frozen=True)
class StructuralGraphIndexStatus:
    state: IndexState
    provider: str
    revision: str = ""
    database_path: str = ""
    indexed_files: int = 0
    requested_files: int = 0
    diagnostics: tuple[Diagnostic, ...] = ()
    schema_version: str = "structural_graph_index_status.v1"

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
class GraphPathStep:
    source: GraphSymbol
    target: GraphSymbol
    relation: str
    direction: TraversalDirection


@dataclass(frozen=True)
class StructuralPath:
    seed_symbol_id: str
    steps: tuple[GraphPathStep, ...]
    classification: PathClassification
    sources: tuple[SourceRef, ...] = ()

    @property
    def depth(self) -> int:
        return len(self.steps)


@dataclass(frozen=True)
class StructuralGraphResult:
    index: StructuralGraphIndexStatus
    hunk_count: int = 0
    overlaps: tuple[HunkSymbolOverlap, ...] = ()
    paths: tuple[StructuralPath, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    schema_version: str = "structural_graph_result.v2"

    @property
    def mapped_hunk_count(self) -> int:
        return len({overlap.hunk_id for overlap in self.overlaps})


@runtime_checkable
class StructuralGraphProvider(Protocol):
    """Read-only structural facts. Providers never produce review conclusions."""

    def inspect_index(
        self, *, requested_files: tuple[str, ...] = ()
    ) -> StructuralGraphIndexStatus: ...

    def symbols_overlapping(
        self, hunks: tuple[ChangedHunk, ...]
    ) -> StructuralGraphResult: ...

    def expand_paths(
        self,
        result: StructuralGraphResult,
        *,
        policy: StructuralTraversalPolicy = StructuralTraversalPolicy(),
    ) -> StructuralGraphResult: ...
