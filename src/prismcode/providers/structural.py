from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from prismcode.model.contracts import Diagnostic, SourceRef
from prismcode.changes.hunks import ChangedHunk

IndexState = Literal["available", "partial", "missing", "stale", "invalid", "error"]
StructuralRevision = Literal["head", "base"]
PathClassification = Literal["runtime", "test", "mixed"]
TraversalDirection = Literal["outgoing", "incoming"]
TraversalCoverageState = Literal["complete", "truncated"]
OwnershipCoverageState = Literal["complete", "truncated", "unavailable"]
CounterpartCoverageState = Literal["complete", "unavailable"]
OwnershipLimit = Literal["depth_budget", "relation_budget"]
TraversalLimit = Literal[
    "seed_node_budget",
    "seed_path_budget",
    "review_node_budget",
    "review_path_budget",
]


@dataclass(frozen=True)
class StructuralTraversalPolicy:
    """Deterministic safety budget for provider-owned graph expansion."""

    max_depth: int = 3
    max_nodes_per_seed: int = 80
    max_paths_per_seed: int = 120
    max_total_nodes: int = 80
    max_total_paths: int = 120
    relation_allowlist: tuple[str, ...] = (
        "calls",
        "imports",
        "instantiates",
        "references",
        "extends",
    )


@dataclass(frozen=True)
class StructuralOwnershipPolicy:
    """Deterministic ancestry boundary for non-executable ownership facts."""

    max_depth: int = 8
    max_relations: int = 240


@dataclass(frozen=True)
class StructuralGraphIndexStatus:
    state: IndexState
    provider: str
    revision_side: StructuralRevision = "head"
    revision: str = ""
    database_path: str = ""
    indexed_files: int = 0
    requested_files: int = 0
    diagnostics: tuple[Diagnostic, ...] = ()
    schema_version: str = "structural_graph_index_status.v2"

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
class StructuralSymbolIdentity:
    file_path: str
    qualified_name: str
    kind: str


@dataclass(frozen=True)
class StructuralCounterpartCoverage:
    state: CounterpartCoverageState
    requested_identities: tuple[StructuralSymbolIdentity, ...]

    def __post_init__(self) -> None:
        if not self.requested_identities:
            raise ValueError("counterpart coverage requires requested identities")
        if len(set(self.requested_identities)) != len(self.requested_identities):
            raise ValueError("counterpart coverage contains duplicate identities")


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
class StructuralOwnershipRelation:
    """One provider-owned parent-to-child `contains` relation."""

    parent: GraphSymbol
    child: GraphSymbol
    sources: tuple[SourceRef, ...] = ()


@dataclass(frozen=True)
class StructuralOwnershipCoverage:
    """Provider coverage for ancestry rooted at observed structural symbols."""

    state: OwnershipCoverageState
    observed_symbol_ids: tuple[str, ...]
    relation_count: int
    limiting_dimensions: tuple[OwnershipLimit, ...] = ()

    def __post_init__(self) -> None:
        if self.state == "complete" and self.limiting_dimensions:
            raise ValueError("complete ownership coverage cannot carry limits")
        if self.state == "truncated" and not self.limiting_dimensions:
            raise ValueError("truncated ownership coverage requires a limit")
        if self.state == "unavailable" and self.relation_count:
            raise ValueError("unavailable ownership coverage cannot contain relations")


@dataclass(frozen=True)
class StructuralSeedCoverage:
    """Provider-owned traversal coverage for one exact changed-symbol seed."""

    seed_symbol_id: str
    state: TraversalCoverageState
    node_count: int
    path_count: int
    limiting_dimensions: tuple[TraversalLimit, ...] = ()
    sources: tuple[SourceRef, ...] = ()


@dataclass(frozen=True)
class StructuralGraphResult:
    index: StructuralGraphIndexStatus
    revision_side: StructuralRevision = "head"
    hunk_count: int = 0
    overlaps: tuple[HunkSymbolOverlap, ...] = ()
    counterpart_symbols: tuple[GraphSymbol, ...] = ()
    counterpart_coverage: StructuralCounterpartCoverage | None = None
    paths: tuple[StructuralPath, ...] = ()
    ownership_relations: tuple[StructuralOwnershipRelation, ...] = ()
    ownership_coverage: StructuralOwnershipCoverage | None = None
    traversal_coverage: tuple[StructuralSeedCoverage, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    schema_version: str = "structural_graph_result.v7"

    @property
    def mapped_hunk_count(self) -> int:
        return len({overlap.hunk_id for overlap in self.overlaps})


@dataclass(frozen=True)
class StructuralGraphCollection:
    revisions: tuple[StructuralGraphResult, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    schema_version: str = "structural_graph_collection.v1"

    def for_revision(
        self, revision_side: StructuralRevision
    ) -> StructuralGraphResult | None:
        return next(
            (
                result
                for result in self.revisions
                if result.revision_side == revision_side
            ),
            None,
        )

    def validate_consistency(self) -> None:
        sides = tuple(item.revision_side for item in self.revisions)
        if len(set(sides)) != len(sides):
            raise ValueError("structural graph contains duplicate revision results")
        for result in self.revisions:
            if result.index.revision_side != result.revision_side:
                raise ValueError(
                    "structural revision result and index side must agree"
                )
            ownership_ids = tuple(
                (relation.parent.id, relation.child.id)
                for relation in result.ownership_relations
            )
            if len(set(ownership_ids)) != len(ownership_ids):
                raise ValueError(
                    "structural graph contains duplicate ownership relations"
                )
            if any(parent_id == child_id for parent_id, child_id in ownership_ids):
                raise ValueError("structural ownership relation cannot contain itself")
            counterpart_ids = tuple(
                symbol.id for symbol in result.counterpart_symbols
            )
            if len(set(counterpart_ids)) != len(counterpart_ids):
                raise ValueError(
                    "structural graph contains duplicate counterpart symbols"
                )
            if set(counterpart_ids) & {
                overlap.symbol.id for overlap in result.overlaps
            }:
                raise ValueError(
                    "structural counterpart duplicates a changed overlap"
                )
            counterpart_coverage = result.counterpart_coverage
            if (
                result.counterpart_symbols
                and (
                    counterpart_coverage is None
                    or counterpart_coverage.state != "complete"
                )
            ):
                raise ValueError(
                    "structural counterparts require complete typed coverage"
                )
            if counterpart_coverage is not None and any(
                StructuralSymbolIdentity(
                    file_path=symbol.file_path,
                    qualified_name=symbol.qualified_name,
                    kind=symbol.kind,
                )
                not in counterpart_coverage.requested_identities
                for symbol in result.counterpart_symbols
            ):
                raise ValueError(
                    "structural counterpart falls outside requested coverage"
                )
            coverage = result.ownership_coverage
            if result.ownership_relations and coverage is None:
                raise ValueError(
                    "structural ownership relations require typed coverage"
                )
            if coverage is not None:
                if len(set(coverage.observed_symbol_ids)) != len(
                    coverage.observed_symbol_ids
                ):
                    raise ValueError(
                        "structural ownership coverage contains duplicate symbols"
                    )
                if coverage.relation_count != len(result.ownership_relations):
                    raise ValueError(
                        "structural ownership coverage relation count mismatch"
                    )


@runtime_checkable
class StructuralGraphProvider(Protocol):
    """Read-only structural facts. Providers never produce review conclusions."""

    def inspect_index(
        self, *, requested_files: tuple[str, ...] = ()
    ) -> StructuralGraphIndexStatus: ...

    def symbols_overlapping(
        self, hunks: tuple[ChangedHunk, ...]
    ) -> StructuralGraphResult: ...

    def complete_counterparts(
        self,
        result: StructuralGraphResult,
        candidates: tuple[GraphSymbol, ...],
    ) -> StructuralGraphResult: ...

    def expand_structure(
        self,
        result: StructuralGraphResult,
        *,
        policy: StructuralTraversalPolicy = StructuralTraversalPolicy(),
        ownership_policy: StructuralOwnershipPolicy = StructuralOwnershipPolicy(),
    ) -> StructuralGraphResult: ...
