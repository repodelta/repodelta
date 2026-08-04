from __future__ import annotations

import hashlib
import sqlite3
import pytest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

from prismcode.pipeline import DeterministicAnalyzer
from prismcode.providers.codegraph import CodegraphProvider
from prismcode.model.contracts import (
    AnalysisInput,
    ChangeRelation,
    ChangedFile,
    ChangedLine,
    Requirement,
    ReviewSourcePacket,
    SourceRef,
)
from prismcode.changes.hunks import parse_changed_files, parse_unified_patch
from prismcode.providers.structural import (
    GraphPathStep,
    GraphSymbol,
    HunkSymbolOverlap,
    StructuralGraphCollection,
    StructuralGraphIndexStatus,
    StructuralGraphProvider,
    StructuralGraphResult,
    StructuralOwnershipPolicy,
    StructuralTraversalPolicy,
)
from prismcode.providers.mapping import map_packet_changed_symbols
from prismcode.presentation.html import render_html


def _create_index(
    root: Path,
    *,
    source: str = "class Service:\n    def run(self):\n        return 1\n",
    connect_symbols: bool = False,
    method_id: str = "method:Service.run",
    include_method: bool = True,
    contain_method: bool = False,
) -> Path:
    source_path = root / "src" / "service.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(source, encoding="utf-8")
    database = root / ".codegraph" / "codegraph.db"
    database.parent.mkdir()
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE nodes (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                name TEXT NOT NULL,
                qualified_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                language TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL
            );
            CREATE TABLE edges (
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                kind TEXT NOT NULL
            );
            CREATE TABLE files (
                path TEXT PRIMARY KEY,
                content_hash TEXT NOT NULL
            );
            """
        )
        node_rows = [
            (
                "class:Service",
                "class",
                "Service",
                "src.service.Service",
                "src/service.py",
                "python",
                1,
                3,
            ),
        ]
        if include_method:
            node_rows.append(
                (
                    method_id,
                    "method",
                    "run",
                    "src.service.Service.run",
                    "src/service.py",
                    "python",
                    2,
                    3,
                )
            )
        connection.executemany(
            """
            INSERT INTO nodes
                (id, kind, name, qualified_name, file_path, language,
                 start_line, end_line)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            node_rows,
        )
        connection.execute(
            "INSERT INTO files (path, content_hash) VALUES (?, ?)",
            ("src/service.py", hashlib.sha256(source.encode()).hexdigest()),
        )
        if connect_symbols and include_method:
            connection.execute(
                "INSERT INTO edges VALUES (?, ?, ?)",
                ("class:Service", method_id, "calls"),
            )
        if contain_method and include_method:
            connection.execute(
                "INSERT INTO edges VALUES (?, ?, ?)",
                ("class:Service", method_id, "contains"),
            )
    return database


def _packet(patch: str | None) -> ReviewSourcePacket:
    return ReviewSourcePacket(
        repository="acme/widget",
        pull_request=7,
        title="Change service",
        source_url="https://github.com/acme/widget/pull/7",
        head_sha="head123",
        base_sha="base123",
        source_records=(),
        changed_files=(
            ChangedFile(
                base_path="src/service.py",
                head_path="src/service.py",
                patch=patch,
                source_url="https://github.com/acme/widget/pull/7/files",
            ),
        ),
    ).with_revision()


def _symbol(
    identifier: str,
    qualified_name: str,
    *,
    kind: str = "function",
    start_line: int = 1,
    end_line: int = 1,
) -> GraphSymbol:
    return GraphSymbol(
        id=identifier,
        kind=kind,
        name=qualified_name.rsplit(".", 1)[-1],
        qualified_name=qualified_name,
        file_path="src/service.py",
        language="python",
        start_line=start_line,
        end_line=end_line,
    )


def _revision_result(
    revision_side: str,
    hunk_id: str,
    *symbols: GraphSymbol,
    state: str = "available",
) -> StructuralGraphResult:
    return StructuralGraphResult(
        index=StructuralGraphIndexStatus(
            state=state,
            provider="test",
            revision_side=revision_side,
        ),
        revision_side=revision_side,
        hunk_count=1,
        overlaps=tuple(
            HunkSymbolOverlap(
                hunk_id=hunk_id,
                symbol=symbol,
                changed_lines=(symbol.start_line,),
            )
            for symbol in symbols
        ),
    )


def test_unified_patch_tracks_exact_new_and_old_line_numbers() -> None:
    hunks = parse_unified_patch(
        "src/service.py",
        "@@ -1,3 +1,4 @@\n"
        " class Service:\n"
        "-    def old(self):\n"
        "+    def run(self):\n"
        "+        value = 1\n"
        "         return value\n",
    )

    assert len(hunks) == 1
    assert hunks[0].added_lines == (2, 3)
    assert hunks[0].removed_lines == (2,)
    assert hunks[0].old_snippet == "    def old(self):"
    assert hunks[0].new_snippet == "    def run(self):\n        value = 1"
    assert hunks[0].relations[0].id == "hunk:src/service.py:0:change:0"
    assert hunks[0].relations[0].kind == "replaced"


def test_unified_patch_splits_change_blocks_on_context_lines() -> None:
    hunks = parse_unified_patch(
        "src/service.py",
        "@@ -1,5 +1,5 @@\n"
        "-old_first()\n"
        "+new_first()\n"
        " unchanged()\n"
        "-old_second()\n"
        "+new_second()\n"
        " trailing()\n",
    )

    assert len(hunks) == 1
    assert len(hunks[0].relations) == 2
    assert hunks[0].relations[0].old_snippet == "old_first()"
    assert hunks[0].relations[0].new_snippet == "new_first()"
    assert hunks[0].relations[1].old_snippet == "old_second()"
    assert hunks[0].relations[1].new_snippet == "new_second()"
    assert [item.kind for item in hunks[0].relations] == [
        "replaced",
        "replaced",
    ]


def test_change_relation_model_rejects_invalid_revision_shape() -> None:
    with pytest.raises(ValueError, match="conflicts"):
        ChangeRelation(
            id="change:1",
            hunk_id="hunk:1",
            base_path="src/a.py",
            head_path="src/a.py",
            kind="added",
            removed=(ChangedLine(1, "old"),),
        )


def test_parser_owns_added_and_removed_relation_kinds() -> None:
    added = parse_unified_patch("src/a.py", "@@ -0,0 +1 @@\n+new()\n")
    removed = parse_unified_patch("src/a.py", "@@ -1 +0,0 @@\n-old()\n")

    assert added[0].relations[0].kind == "added"
    assert added[0].relations[0].removed == ()
    assert removed[0].relations[0].kind == "removed"
    assert removed[0].relations[0].added == ()


def test_provider_protocol_and_missing_index_diagnostic(tmp_path: Path) -> None:
    provider = CodegraphProvider(tmp_path)

    assert isinstance(provider, StructuralGraphProvider)
    status = provider.inspect_index(requested_files=("src/service.py",))

    assert status.state == "missing"
    assert status.usable is False
    assert [item.code for item in status.diagnostics] == ["codegraph_index_missing"]


def test_changed_hunk_maps_to_narrowest_exact_symbol(tmp_path: Path) -> None:
    _create_index(
        tmp_path,
        source="class Service:\n    def run(self):\n        return 2\n",
    )
    patch = (
        "@@ -1,3 +1,3 @@\n"
        " class Service:\n"
        "     def run(self):\n"
        "-        return 1\n"
        "+        return 2\n"
    )

    packet = _packet(patch)
    graph = map_packet_changed_symbols(
        packet, parse_changed_files(packet.changed_files), CodegraphProvider(tmp_path)
    )
    result = graph.for_revision("head")
    assert result is not None

    assert result.index.state == "available"
    assert result.hunk_count == 1
    assert result.mapped_hunk_count == 1
    assert len(result.overlaps) == 1
    overlap = result.overlaps[0]
    assert overlap.symbol.qualified_name == "src.service.Service.run"
    assert overlap.symbol.start_line == 2
    assert overlap.symbol.end_line == 3
    assert overlap.changed_lines == (3,)
    assert {source.label for source in overlap.sources} == {
        "diff hunk",
        "Codegraph symbol",
    }


def test_replacement_collects_distinct_head_and_base_symbol_facts(
    tmp_path: Path,
) -> None:
    head_root = tmp_path / "head"
    base_root = tmp_path / "base"
    _create_index(
        head_root,
        source="class Service:\n    def run(self):\n        return 2\n",
        connect_symbols=True,
        method_id="head:method:Service.run:2-3",
    )
    _create_index(
        base_root,
        source="class Service:\n    def run(self):\n        return 1\n",
        connect_symbols=True,
        method_id="base:method:Service.run:2-3",
    )
    packet = _packet(
        "@@ -3 +3 @@\n-        return 1\n+        return 2\n"
    )
    changes = parse_changed_files(packet.changed_files)

    graph = map_packet_changed_symbols(
        packet,
        changes,
        CodegraphProvider(head_root, revision_side="head"),
        base_provider=CodegraphProvider(base_root, revision_side="base"),
    )
    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(
            packet=packet,
            changes=changes,
            structural_graph=graph,
        )
    )

    head = graph.for_revision("head")
    base = graph.for_revision("base")
    assert head is not None and base is not None
    assert head.mapped_hunk_count == base.mapped_hunk_count == 1
    assert head.counterpart_symbols == ()
    assert base.counterpart_symbols == ()
    symbols = tuple(
        sorted(
            (
                item
                for item in brief.evidence_catalog.items
                if item.kind == "symbol" and item.changed
            ),
            key=lambda item: item.revision_side,
        )
    )
    assert [(item.revision_side, item.operation) for item in symbols] == [
        ("base", "replaced"),
        ("head", "replaced"),
    ]
    assert len({item.id for item in symbols}) == 2
    assert symbols[0].metadata["symbol_id"] != symbols[1].metadata["symbol_id"]
    assert (
        symbols[0].metadata["review_symbol_id"]
        == symbols[1].metadata["review_symbol_id"]
    )
    assert "/blob/base123/" in symbols[0].sources[0].url
    assert "/blob/head123/" in symbols[1].sources[0].url
    paths = tuple(
        item for item in brief.evidence_catalog.items if item.kind == "structural_path"
    )
    assert {item.revision_side for item in paths} == {"base", "head"}
    evidence = brief.evidence_catalog.by_id()
    for path in paths:
        for step in path.metadata["steps"]:
            assert evidence[step["source_evidence_id"]].revision_side == path.revision_side
            assert evidence[step["target_evidence_id"]].revision_side == path.revision_side
    changes = tuple(
        item
        for item in brief.evidence_catalog.items
        if item.kind == "structural_change"
    )
    assert len(changes) == 1
    assert changes[0].operation == "modified"
    assert changes[0].structural_change is not None
    assert {
        changes[0].structural_change.base_symbol_evidence_id,
        changes[0].structural_change.head_symbol_evidence_id,
    } == {item.id for item in symbols}


def test_exact_counterpart_ownership_connects_modified_member(
    tmp_path: Path,
) -> None:
    head_root = tmp_path / "head"
    base_root = tmp_path / "base"
    _create_index(
        head_root,
        source=(
            "class Service:\n"
            "    def run(self):\n"
            "        return new_result_value\n"
        ),
        method_id="head:method:Service.run",
        contain_method=True,
    )
    _create_index(
        base_root,
        source=(
            "class Service:\n"
            "    def run(self):\n"
            "        return old_result_value\n"
        ),
        method_id="base:method:Service.run",
        contain_method=True,
    )
    with sqlite3.connect(base_root / ".codegraph" / "codegraph.db") as connection:
        connection.execute(
            "UPDATE nodes SET end_line = 2 WHERE id = ?",
            ("base:method:Service.run",),
        )
    packet = _packet(
        "@@ -3 +3 @@\n"
        "-        return old_result_value\n"
        "+        return new_result_value\n"
    )
    changes = parse_changed_files(packet.changed_files)

    graph = map_packet_changed_symbols(
        packet,
        changes,
        CodegraphProvider(head_root, revision_side="head"),
        base_provider=CodegraphProvider(base_root, revision_side="base"),
    )
    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(
            packet=packet,
            changes=changes,
            structural_graph=graph,
            requirements=(
                Requirement(
                    id="R1",
                    text="Use new_result_value in Service.run",
                ),
            ),
        )
    )

    head = graph.for_revision("head")
    base = graph.for_revision("base")
    assert head is not None and base is not None
    assert [item.symbol.qualified_name for item in head.overlaps] == [
        "src.service.Service.run"
    ]
    assert [item.symbol.qualified_name for item in base.overlaps] == [
        "src.service.Service"
    ]
    assert [item.qualified_name for item in head.counterpart_symbols] == [
        "src.service.Service"
    ]
    assert [item.qualified_name for item in base.counterpart_symbols] == [
        "src.service.Service.run"
    ]
    assert [path.seed_symbol_id for path in head.paths] == []
    assert [path.seed_symbol_id for path in base.paths] == []
    assert [item.seed_symbol_id for item in head.traversal_coverage] == [
        "head:method:Service.run"
    ]
    assert [item.seed_symbol_id for item in base.traversal_coverage] == [
        "class:Service"
    ]
    assert head.ownership_coverage is not None
    assert base.ownership_coverage is not None
    assert set(head.ownership_coverage.observed_symbol_ids) == {
        "class:Service",
        "head:method:Service.run",
    }
    assert set(base.ownership_coverage.observed_symbol_ids) == {
        "class:Service",
        "base:method:Service.run",
    }
    assert [
        (
            relation.parent.qualified_name,
            relation.child.qualified_name,
        )
        for result in (head, base)
        for relation in result.ownership_relations
    ] == [
        ("src.service.Service", "src.service.Service.run"),
        ("src.service.Service", "src.service.Service.run"),
    ]
    ownership = [
        item
        for item in brief.evidence_catalog.items
        if item.kind == "structural_ownership_change"
    ]
    assert len(ownership) == 1
    assert ownership[0].operation == "retained"
    review_graph = brief.projection.review_graph
    assert len(review_graph.backbone_ownership_edge_ids) == 1
    incident_node_ids = {
        node_id
        for edge in review_graph.ownership_edges
        for node_id in (edge.parent_node_id, edge.child_node_id)
    }
    assert set(review_graph.backbone_node_ids) <= incident_node_ids
    assert "0 isolated changed anchors" in render_html(brief)


def test_explicit_rename_maps_each_revision_path_and_converges_symbol(
    tmp_path: Path,
) -> None:
    head_root = tmp_path / "head"
    base_root = tmp_path / "base"
    _create_index(head_root, method_id="head:run")
    _create_index(base_root, method_id="base:run")

    for root, renamed_path in (
        (head_root, "src/new_service.py"),
        (base_root, "src/old_service.py"),
    ):
        original = root / "src" / "service.py"
        renamed = root / renamed_path
        original.rename(renamed)
        with sqlite3.connect(root / ".codegraph" / "codegraph.db") as connection:
            connection.execute(
                "UPDATE nodes SET file_path = ?",
                (renamed_path,),
            )
            module_name = (
                "src.new_service"
                if root == head_root
                else "src.old_service"
            )
            connection.execute(
                """
                UPDATE nodes
                SET qualified_name = REPLACE(
                    qualified_name,
                    'src.service',
                    ?
                )
                """,
                (module_name,),
            )
            connection.execute(
                "UPDATE files SET path = ?",
                (renamed_path,),
            )

    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=7,
        title="Rename service",
        source_records=(),
        changed_files=(
            ChangedFile(
                base_path="src/old_service.py",
                head_path="src/new_service.py",
                status="renamed",
                patch="@@ -2 +2 @@\n-    def run(self):\n+    def run(self):\n",
            ),
        ),
        head_sha="head123",
        base_sha="base123",
    ).with_revision()
    changes = parse_changed_files(packet.changed_files)

    graph = map_packet_changed_symbols(
        packet,
        changes,
        CodegraphProvider(head_root, revision_side="head"),
        base_provider=CodegraphProvider(base_root, revision_side="base"),
    )
    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(
            packet=packet,
            changes=changes,
            structural_graph=graph,
        )
    )

    assert graph.for_revision("head").index.indexed_files == 1
    assert graph.for_revision("base").index.indexed_files == 1
    structural_changes = tuple(
        item
        for item in brief.evidence_catalog.items
        if item.kind == "structural_change"
        and item.metadata["symbol_kind"] == "method"
    )
    assert len(structural_changes) == 1
    assert structural_changes[0].operation == "renamed"
    assert structural_changes[0].metadata["base_path"] == "src/old_service.py"
    assert structural_changes[0].metadata["head_path"] == "src/new_service.py"


def test_added_relation_produces_one_head_only_structural_change(
    tmp_path: Path,
) -> None:
    head_root = tmp_path / "head"
    base_root = tmp_path / "base"
    _create_index(head_root)
    _create_index(
        base_root,
        source="class Service:\n    pass\n",
        include_method=False,
    )
    packet = _packet(
        "@@ -0,0 +1,3 @@\n"
        "+class Service:\n"
        "+    def run(self):\n"
        "+        return 1\n"
    )
    changes = parse_changed_files(packet.changed_files)
    graph = map_packet_changed_symbols(
        packet,
        changes,
        CodegraphProvider(head_root, revision_side="head"),
        base_provider=CodegraphProvider(base_root, revision_side="base"),
    )
    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(packet=packet, changes=changes, structural_graph=graph)
    )

    structural_changes = {
        item.metadata["qualified_name"]: item
        for item in brief.evidence_catalog.items
        if item.kind == "structural_change"
    }
    assert structural_changes["src.service.Service"].operation == "modified"
    structural_change = structural_changes["src.service.Service.run"]
    assert structural_change.operation == "added"
    assert structural_change.structural_change is not None
    assert structural_change.structural_change.base_symbol_evidence_id is None
    assert structural_change.structural_change.head_symbol_evidence_id is not None


def test_unavailable_counterpart_lookup_does_not_claim_symbol_addition(
    tmp_path: Path,
) -> None:
    head_root = tmp_path / "head"
    missing_base_root = tmp_path / "base"
    _create_index(head_root)
    packet = _packet(
        "@@ -0,0 +1,3 @@\n"
        "+class Service:\n"
        "+    def run(self):\n"
        "+        return 1\n"
    )
    changes = parse_changed_files(packet.changed_files)

    graph = map_packet_changed_symbols(
        packet,
        changes,
        CodegraphProvider(head_root, revision_side="head"),
        base_provider=CodegraphProvider(
            missing_base_root,
            revision_side="base",
        ),
    )
    base = graph.for_revision("base")
    assert base is not None
    assert base.counterpart_coverage is not None
    assert base.counterpart_coverage.state == "unavailable"
    assert "codegraph_index_missing" in {
        item.code for item in base.diagnostics
    }

    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(
            packet=packet,
            changes=changes,
            structural_graph=graph,
        )
    )
    assert {
        item.operation
        for item in brief.evidence_catalog.items
        if item.kind == "structural_change"
        } == {"unresolved"}


def test_removed_relation_maps_exact_base_symbol(tmp_path: Path) -> None:
    head_root = tmp_path / "head"
    base_root = tmp_path / "base"
    _create_index(
        head_root,
        source="class Service:\n    pass\n",
        include_method=False,
    )
    _create_index(base_root)
    packet = _packet(
        "@@ -2,2 +2,0 @@\n"
        "-    def run(self):\n"
        "-        return 1\n"
    )
    changes = parse_changed_files(packet.changed_files)

    graph = map_packet_changed_symbols(
        packet,
        changes,
        CodegraphProvider(head_root, revision_side="head"),
        base_provider=CodegraphProvider(base_root, revision_side="base"),
    )
    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(
            packet=packet,
            changes=changes,
            structural_graph=graph,
        )
    )

    removed = tuple(
        item
        for item in brief.evidence_catalog.items
        if item.kind == "symbol" and item.revision_side == "base"
    )
    assert len(removed) == 1
    assert removed[0].operation == "removed"
    assert removed[0].change_relation_ids == (
        changes.hunks[0].relations[0].id,
    )
    structural_change = next(
        item
        for item in brief.evidence_catalog.items
        if item.kind == "structural_change"
    )
    assert structural_change.operation == "removed"
    assert structural_change.structural_change is not None
    assert structural_change.structural_change.base_symbol_evidence_id == removed[0].id
    assert structural_change.structural_change.head_symbol_evidence_id is None


def test_added_only_line_pairs_existing_base_symbol_as_modified(
    tmp_path: Path,
) -> None:
    head_root = tmp_path / "head"
    base_root = tmp_path / "base"
    _create_index(
        head_root,
        source=(
            "class Service:\n"
            "    def run(self):\n"
            "        trace()\n"
            "        return 1\n"
        ),
    )
    _create_index(base_root)
    packet = _packet(
        "@@ -2,2 +2,3 @@\n"
        "     def run(self):\n"
        "+        trace()\n"
        "         return 1\n"
    )
    changes = parse_changed_files(packet.changed_files)

    graph = map_packet_changed_symbols(
        packet,
        changes,
        CodegraphProvider(head_root, revision_side="head"),
        base_provider=CodegraphProvider(base_root, revision_side="base"),
    )
    head, base = graph.revisions
    assert len(head.overlaps) == 1
    assert base.overlaps == ()
    assert [item.qualified_name for item in base.counterpart_symbols] == [
        "src.service.Service.run"
    ]

    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(
            packet=packet,
            changes=changes,
            structural_graph=graph,
        )
    )
    structural_change = next(
        item
        for item in brief.evidence_catalog.items
        if item.kind == "structural_change"
    )
    assert structural_change.operation == "modified"
    assert structural_change.structural_change is not None
    assert structural_change.structural_change.base_symbol_evidence_id
    assert structural_change.structural_change.head_symbol_evidence_id
    base_counterpart_id = structural_change.structural_change.base_symbol_evidence_id
    assert base_counterpart_id not in {
        relation.target_id
        for relation in brief.projection_candidates.relations
    }


def test_removed_only_line_pairs_existing_head_symbol_as_modified(
    tmp_path: Path,
) -> None:
    head_root = tmp_path / "head"
    base_root = tmp_path / "base"
    _create_index(head_root)
    _create_index(
        base_root,
        source=(
            "class Service:\n"
            "    def run(self):\n"
            "        trace()\n"
            "        return 1\n"
        ),
    )
    packet = _packet(
        "@@ -2,3 +2,2 @@\n"
        "     def run(self):\n"
        "-        trace()\n"
        "         return 1\n"
    )
    changes = parse_changed_files(packet.changed_files)

    graph = map_packet_changed_symbols(
        packet,
        changes,
        CodegraphProvider(head_root, revision_side="head"),
        base_provider=CodegraphProvider(base_root, revision_side="base"),
    )
    head, base = graph.revisions
    assert head.overlaps == ()
    assert len(base.overlaps) == 1
    assert [item.qualified_name for item in head.counterpart_symbols] == [
        "src.service.Service.run"
    ]

    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(
            packet=packet,
            changes=changes,
            structural_graph=graph,
        )
    )
    structural_change = next(
        item
        for item in brief.evidence_catalog.items
        if item.kind == "structural_change"
    )
    assert structural_change.operation == "modified"
    assert structural_change.structural_change is not None
    assert structural_change.structural_change.base_symbol_evidence_id
    assert structural_change.structural_change.head_symbol_evidence_id


def test_replacement_hunk_uses_presence_for_distinct_symbol_identities() -> None:
    packet = _packet(
        "@@ -1 +1 @@\n"
        "-def old_anchor(): pass\n"
        "+def focus_relevant_anchor(): pass\n"
    )
    changes = parse_changed_files(packet.changed_files)
    hunk_id = changes.hunks[0].id
    graph = StructuralGraphCollection(
        revisions=(
            _revision_result(
                "head",
                hunk_id,
                _symbol("head:new", "focus_relevant_anchor"),
            ),
            _revision_result(
                "base",
                hunk_id,
                _symbol("base:old", "old_anchor"),
            ),
        )
    )

    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(
            packet=packet,
            changes=changes,
            structural_graph=graph,
            requirements=(
                Requirement(
                    id="R1",
                    text="Expose focus_relevant_anchor",
                ),
                Requirement(
                    id="G1",
                    text="Remove old_anchor",
                    purpose="guardrail",
                    kind="guardrail",
                ),
            ),
        )
    )
    operations = {
        item.metadata["qualified_name"]: item.operation
        for item in brief.evidence_catalog.items
        if item.kind == "structural_change"
    }

    assert operations == {
        "focus_relevant_anchor": "added",
        "old_anchor": "removed",
    }
    html = render_html(brief)
    assert 'class="isolated-anchor operation-added"' in html
    assert 'class="isolated-anchor operation-removed"' in html
    assert "focus_relevant_anchor" in html
    assert "old_anchor" in html


def test_head_only_file_symbol_retains_modified_file_status() -> None:
    packet = _packet(
        "@@ -1 +1 @@\n"
        "-from package import old_dependency\n"
        "+from package import new_dependency\n"
    )
    changes = parse_changed_files(packet.changed_files)
    hunk_id = changes.hunks[0].id
    graph = StructuralGraphCollection(
        revisions=(
            _revision_result(
                "head",
                hunk_id,
                _symbol("head:file", "src/service.py", kind="file"),
            ),
            _revision_result("base", hunk_id),
        )
    )

    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(
            packet=packet,
            changes=changes,
            structural_graph=graph,
        )
    )
    structural_change = next(
        item
        for item in brief.evidence_catalog.items
        if item.kind == "structural_change"
    )

    assert structural_change.metadata["symbol_kind"] == "file"
    assert structural_change.operation == "modified"


@pytest.mark.parametrize(
    ("status", "base_path", "head_path", "patch", "revision_side"),
    (
        (
            "added",
            None,
            "src/service.py",
            "@@ -0,0 +1 @@\n+def run(): pass\n",
            "head",
        ),
        (
            "removed",
            "src/service.py",
            None,
            "@@ -1 +0,0 @@\n-def run(): pass\n",
            "base",
        ),
    ),
)
def test_file_existence_status_applies_to_every_structural_symbol(
    status: str,
    base_path: str | None,
    head_path: str | None,
    patch: str,
    revision_side: str,
) -> None:
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=8,
        title=f"{status.title()} service",
        source_records=(),
        head_sha="head123",
        base_sha="base123",
        changed_files=(
            ChangedFile(
                base_path=base_path,
                head_path=head_path,
                status=status,
                patch=patch,
            ),
        ),
    ).with_revision()
    changes = parse_changed_files(packet.changed_files)
    hunk_id = changes.hunks[0].id
    symbol = _symbol(f"{revision_side}:run", "run")
    head_symbols = (symbol,) if revision_side == "head" else ()
    base_symbols = (symbol,) if revision_side == "base" else ()
    graph = StructuralGraphCollection(
        revisions=(
            _revision_result(
                "head",
                hunk_id,
                *head_symbols,
            ),
            _revision_result(
                "base",
                hunk_id,
                *base_symbols,
            ),
        )
    )

    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(packet=packet, changes=changes, structural_graph=graph)
    )
    structural_change = next(
        item
        for item in brief.evidence_catalog.items
        if item.kind == "structural_change"
    )

    assert structural_change.metadata["symbol_kind"] == "function"
    assert structural_change.operation == status


def test_unmapped_opposite_revision_does_not_prove_symbol_addition() -> None:
    packet = _packet(
        "@@ -2 +2 @@\n"
        "-    return old_value\n"
        "+    return new_value\n"
    )
    changes = parse_changed_files(packet.changed_files)
    hunk_id = changes.hunks[0].id
    graph = StructuralGraphCollection(
        revisions=(
            _revision_result(
                "head",
                hunk_id,
                _symbol("head:run", "run", start_line=2, end_line=2),
            ),
            _revision_result("base", hunk_id, state="partial"),
        )
    )

    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(
            packet=packet,
            changes=changes,
            structural_graph=graph,
        )
    )
    structural_change = next(
        item
        for item in brief.evidence_catalog.items
        if item.kind == "structural_change"
    )

    assert structural_change.operation == "unresolved"


def test_mapping_another_relation_in_the_hunk_does_not_prove_absence() -> None:
    packet = _packet(
        "@@ -1,5 +1,5 @@\n"
        " def first():\n"
        "-    return old_first\n"
        "+    return new_first\n"
        " def second():\n"
        "-    return old_second\n"
        "+    return new_second\n"
    )
    changes = parse_changed_files(packet.changed_files)
    hunk_id = changes.hunks[0].id
    graph = StructuralGraphCollection(
        revisions=(
            _revision_result(
                "head",
                hunk_id,
                _symbol("head:first", "first", start_line=2),
            ),
            _revision_result(
                "base",
                hunk_id,
                _symbol("base:second", "second", start_line=4),
                state="partial",
            ),
        )
    )

    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(
            packet=packet,
            changes=changes,
            structural_graph=graph,
        )
    )
    operations = {
        item.metadata["qualified_name"]: item.operation
        for item in brief.evidence_catalog.items
        if item.kind == "structural_change"
    }

    assert operations == {
        "first": "unresolved",
        "second": "unresolved",
    }


def test_one_hunk_can_map_changes_in_two_sibling_symbols(tmp_path: Path) -> None:
    source = "def first():\n    return 2\n\ndef second():\n    return 4\n"
    source_path = tmp_path / "src" / "service.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(source, encoding="utf-8")
    database = tmp_path / ".codegraph" / "codegraph.db"
    database.parent.mkdir()
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE nodes (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
                qualified_name TEXT NOT NULL, file_path TEXT NOT NULL,
                language TEXT NOT NULL, start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL
            );
            CREATE TABLE edges (
                source TEXT NOT NULL, target TEXT NOT NULL, kind TEXT NOT NULL
            );
            CREATE TABLE files (
                path TEXT PRIMARY KEY, content_hash TEXT NOT NULL
            );
            """
        )
        connection.executemany(
            "INSERT INTO nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ("first", "function", "first", "first", "src/service.py", "python", 1, 2),
                ("second", "function", "second", "second", "src/service.py", "python", 4, 5),
            ),
        )
        connection.execute(
            "INSERT INTO files VALUES (?, ?)",
            ("src/service.py", hashlib.sha256(source.encode()).hexdigest()),
        )
    patch = (
        "@@ -1,5 +1,5 @@\n"
        " def first():\n"
        "-    return 1\n"
        "+    return 2\n"
        " \n"
        " def second():\n"
        "-    return 3\n"
        "+    return 4\n"
    )

    packet = _packet(patch)
    graph = map_packet_changed_symbols(
        packet, parse_changed_files(packet.changed_files), CodegraphProvider(tmp_path)
    )
    result = graph.for_revision("head")
    assert result is not None

    assert [(item.symbol.id, item.changed_lines) for item in result.overlaps] == [
        ("first", (2,)),
        ("second", (5,)),
    ]
    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(
            packet=packet,
            changes=parse_changed_files(packet.changed_files),
            structural_graph=graph,
        )
    )
    assert {
        item.structural_change.review_symbol_id
        for item in brief.evidence_catalog.items
        if item.kind == "structural_change"
        and item.structural_change is not None
        } == {
            "E:review_symbol:8568070b59da412edbf2",
            "E:review_symbol:08ad1eed70311d4303da",
        }


def test_module_level_change_falls_back_to_file_symbol(tmp_path: Path) -> None:
    source = "from package import dependency\n\ndef run():\n    return dependency()\n"
    source_path = tmp_path / "src" / "service.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(source, encoding="utf-8")
    database = tmp_path / ".codegraph" / "codegraph.db"
    database.parent.mkdir()
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE nodes (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
                qualified_name TEXT NOT NULL, file_path TEXT NOT NULL,
                language TEXT NOT NULL, start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL
            );
            CREATE TABLE edges (
                source TEXT NOT NULL, target TEXT NOT NULL, kind TEXT NOT NULL
            );
            CREATE TABLE files (
                path TEXT PRIMARY KEY, content_hash TEXT NOT NULL
            );
            """
        )
        connection.executemany(
            "INSERT INTO nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                (
                    "file:service",
                    "file",
                    "service.py",
                    "src/service.py",
                    "src/service.py",
                    "python",
                    1,
                    4,
                ),
                (
                    "function:run",
                    "function",
                    "run",
                    "run",
                    "src/service.py",
                    "python",
                    3,
                    4,
                ),
            ),
        )
        connection.execute(
            "INSERT INTO files VALUES (?, ?)",
            ("src/service.py", hashlib.sha256(source.encode()).hexdigest()),
        )
    hunks = parse_unified_patch(
        "src/service.py",
        "@@ -0,0 +1 @@\n+from package import dependency\n",
    )

    result = CodegraphProvider(tmp_path).symbols_overlapping(hunks)

    assert [(item.symbol.kind, item.symbol.qualified_name) for item in result.overlaps] == [
        ("file", "src/service.py"),
    ]
    assert "structural_graph_no_symbol_overlap" not in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_document_hunks_do_not_reduce_codegraph_coverage(tmp_path: Path) -> None:
    _create_index(tmp_path)
    code_hunks = parse_unified_patch(
        "src/service.py",
        "@@ -3 +3 @@\n-        return 1\n+        return 2\n",
    )
    document_hunks = parse_unified_patch(
        "README.md",
        "@@ -0,0 +1 @@\n+# Documentation\n",
    )

    result = CodegraphProvider(tmp_path).symbols_overlapping(
        (*code_hunks, *document_hunks)
    )

    assert result.index.state == "available"
    assert result.index.requested_files == 1
    assert result.index.indexed_files == 1
    assert result.hunk_count == 1
    assert "codegraph_file_not_indexed" not in {
        diagnostic.code for diagnostic in result.diagnostics
    }
    assert "structural_graph_file_not_applicable" in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_added_only_file_is_not_applicable_to_base_coverage(
    tmp_path: Path,
) -> None:
    added = parse_unified_patch(
        "src/new_service.py",
        "@@ -0,0 +1 @@\n+def created(): pass\n",
    )

    result = CodegraphProvider(
        tmp_path,
        revision_side="base",
    ).symbols_overlapping(added)

    assert result.index.state == "available"
    assert result.index.requested_files == 0
    assert result.index.indexed_files == 0
    assert result.hunk_count == 0
    assert "codegraph_file_not_indexed" not in {
        diagnostic.code for diagnostic in result.diagnostics
    }
    assert "structural_graph_revision_not_applicable" in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_removed_only_file_is_not_applicable_to_head_coverage(
    tmp_path: Path,
) -> None:
    removed = parse_unified_patch(
        "src/old_service.py",
        "@@ -1 +0,0 @@\n-def removed(): pass\n",
    )

    result = CodegraphProvider(
        tmp_path,
        revision_side="head",
    ).symbols_overlapping(removed)

    assert result.index.state == "available"
    assert result.index.requested_files == 0
    assert result.hunk_count == 0
    assert "codegraph_file_not_indexed" not in {
        diagnostic.code for diagnostic in result.diagnostics
    }
    assert "structural_graph_revision_not_applicable" in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_mixed_added_and_replaced_files_keep_base_coverage_available(
    tmp_path: Path,
) -> None:
    _create_index(tmp_path)
    added = parse_unified_patch(
        "src/new_service.py",
        "@@ -0,0 +1 @@\n+def created(): pass\n",
    )
    replaced = parse_unified_patch(
        "src/service.py",
        "@@ -3 +3 @@\n-        return 0\n+        return 1\n",
    )

    result = CodegraphProvider(
        tmp_path,
        revision_side="base",
    ).symbols_overlapping((*added, *replaced))

    assert result.index.state == "available"
    assert result.index.requested_files == 1
    assert result.index.indexed_files == 1
    assert result.hunk_count == 1
    assert result.mapped_hunk_count == 1
    assert {
        diagnostic.code for diagnostic in result.diagnostics
    } >= {"structural_graph_revision_not_applicable"}
    assert "codegraph_file_not_indexed" not in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_replacement_hunk_remains_applicable_to_both_revisions(
    tmp_path: Path,
) -> None:
    _create_index(tmp_path)
    replaced = parse_unified_patch(
        "src/service.py",
        "@@ -3 +3 @@\n-        return 0\n+        return 1\n",
    )

    head = CodegraphProvider(
        tmp_path,
        revision_side="head",
    ).symbols_overlapping(replaced)
    base = CodegraphProvider(
        tmp_path,
        revision_side="base",
    ).symbols_overlapping(replaced)

    assert (head.index.requested_files, head.hunk_count) == (1, 1)
    assert (base.index.requested_files, base.hunk_count) == (1, 1)
    assert head.mapped_hunk_count == base.mapped_hunk_count == 1
    assert "structural_graph_revision_not_applicable" not in {
        diagnostic.code
        for result in (head, base)
        for diagnostic in result.diagnostics
    }


def test_file_with_one_applicable_hunk_is_not_labeled_inapplicable(
    tmp_path: Path,
) -> None:
    _create_index(tmp_path)
    hunks = parse_unified_patch(
        "src/service.py",
        "@@ -1 +1,0 @@\n-class Service:\n"
        "@@ -2,0 +2 @@\n+class RenamedService:\n",
    )

    base = CodegraphProvider(
        tmp_path,
        revision_side="base",
    ).symbols_overlapping(hunks)
    head = CodegraphProvider(
        tmp_path,
        revision_side="head",
    ).symbols_overlapping(hunks)

    assert base.hunk_count == head.hunk_count == 1
    assert "structural_graph_revision_not_applicable" not in {
        diagnostic.code
        for result in (head, base)
        for diagnostic in result.diagnostics
    }


def test_stale_index_is_not_used(tmp_path: Path) -> None:
    _create_index(tmp_path)
    (tmp_path / "src" / "service.py").write_text(
        "class Service:\n    def run(self):\n        return 2\n",
        encoding="utf-8",
    )
    hunks = parse_unified_patch(
        "src/service.py",
        "@@ -3 +3 @@\n-        return 1\n+        return 2\n",
    )

    result = CodegraphProvider(tmp_path).symbols_overlapping(hunks)

    assert result.index.state == "stale"
    assert result.overlaps == ()
    assert "codegraph_index_stale" in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_live_review_checkout_must_match_expected_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_index(tmp_path)
    monkeypatch.setattr(
        "prismcode.providers.codegraph._checkout_revision",
        lambda _root: "different-head",
    )
    hunks = parse_unified_patch(
        "src/service.py",
        "@@ -3 +3 @@\n-        return 1\n+        return 2\n",
    )

    result = CodegraphProvider(
        tmp_path,
        expected_revision="expected-head",
    ).symbols_overlapping(hunks)

    assert result.index.state == "stale"
    assert result.overlaps == ()
    assert "codegraph_checkout_revision_mismatch" in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_stale_base_revision_preserves_head_and_excludes_base_facts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    head_root = tmp_path / "head"
    base_root = tmp_path / "base"
    _create_index(
        head_root,
        source="class Service:\n    def run(self):\n        return 2\n",
    )
    _create_index(base_root)
    monkeypatch.setattr(
        "prismcode.providers.codegraph._checkout_revision",
        lambda root: "head123" if root == head_root else "wrong-base",
    )
    packet = _packet(
        "@@ -3 +3 @@\n-        return 1\n+        return 2\n"
    )
    changes = parse_changed_files(packet.changed_files)

    graph = map_packet_changed_symbols(
        packet,
        changes,
        CodegraphProvider(
            head_root,
            expected_revision=packet.head_sha,
            revision_side="head",
        ),
        base_provider=CodegraphProvider(
            base_root,
            expected_revision=packet.base_sha,
            revision_side="base",
        ),
    )
    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(
            packet=packet,
            changes=changes,
            structural_graph=graph,
        )
    )

    head = graph.for_revision("head")
    base = graph.for_revision("base")
    assert head is not None and head.index.state == "available"
    assert base is not None and base.index.state == "stale"
    assert base.overlaps == ()
    assert {
        item.revision_side
        for item in brief.evidence_catalog.items
        if item.kind == "symbol" and item.changed
    } == {"head"}


def test_deletion_only_hunk_reports_one_missing_base_input(tmp_path: Path) -> None:
    _create_index(tmp_path)
    packet = _packet("@@ -2,1 +2,0 @@\n-    def run(self):\n")

    graph = map_packet_changed_symbols(
        packet,
        parse_changed_files(packet.changed_files),
        CodegraphProvider(tmp_path),
    )

    assert [item.code for item in graph.diagnostics] == [
        "structural_graph_base_input_missing"
    ]


def test_missing_patch_is_explicitly_reported(tmp_path: Path) -> None:
    _create_index(tmp_path)

    packet = _packet(None)
    graph = map_packet_changed_symbols(
        packet, parse_changed_files(packet.changed_files), CodegraphProvider(tmp_path)
    )
    result = graph.for_revision("head")
    assert result is not None

    assert result.overlaps == ()
    assert [item.code for item in graph.diagnostics] == [
        "structural_graph_patch_unavailable"
    ]


def test_analyzer_preserves_structural_facts_without_using_them_as_conclusions(
    tmp_path: Path,
) -> None:
    _create_index(
        tmp_path,
        source="class Service:\n    def run(self):\n        return 2\n",
    )
    patch = (
        "@@ -3 +3 @@\n"
        "-        return 1\n"
        "+        return 2\n"
    )
    packet = _packet(patch)
    structural = map_packet_changed_symbols(
        packet, parse_changed_files(packet.changed_files), CodegraphProvider(tmp_path)
    )
    lexical_only = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))

    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(packet=packet, structural_graph=structural)
    )

    assert brief.schema_version == "review_brief.v45"
    assert brief.requirements == lexical_only.requirements == ()
    serialized = brief.to_dict()
    assert "structural_graph" not in serialized
    symbol = next(
        item for item in serialized["evidence_catalog"]["items"]
        if item["kind"] == "symbol"
    )
    assert symbol["metadata"]["qualified_name"] == "src.service.Service.run"
    observed = brief.observed_transformation
    assert len(observed.structural_change_evidence_ids) == 1
    assert observed.topology.base_symbol_change_evidence_ids == ()
    assert observed.topology.head_symbol_change_evidence_ids == (
        observed.structural_change_evidence_ids
    )
    assert observed.fallback_change_evidence_ids == ()


def test_bounded_paths_load_unchanged_y_to_x_to_z_neighbors(tmp_path: Path) -> None:
    sources = {
        "src/adapter.py": "def adapt():\n    return core()\n",
        "src/core.py": "def core():\n    return persist()\n",
        "src/store.py": "def persist():\n    return True\n",
        "src/audit.py": "def audit():\n    return notify()\n",
        "src/notify.py": "def notify():\n    return True\n",
        "tests/test_adapter.py": "def test_adapt():\n    assert adapt()\n",
    }
    for path, source in sources.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
    database = tmp_path / ".codegraph" / "codegraph.db"
    database.parent.mkdir()
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE nodes (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
                qualified_name TEXT NOT NULL, file_path TEXT NOT NULL,
                language TEXT NOT NULL, start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL
            );
            CREATE TABLE edges (
                source TEXT NOT NULL, target TEXT NOT NULL, kind TEXT NOT NULL
            );
            CREATE TABLE files (
                path TEXT PRIMARY KEY, content_hash TEXT NOT NULL
            );
            """
        )
        connection.executemany(
            "INSERT INTO nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                (
                    "Y", "function", "adapt", "src.adapter.adapt",
                    "src/adapter.py", "python", 1, 2,
                ),
                (
                    "X", "function", "core", "src.core.core",
                    "src/core.py", "python", 1, 2,
                ),
                (
                    "Z", "function", "persist", "src.store.persist",
                    "src/store.py", "python", 1, 2,
                ),
                (
                    "W", "function", "audit", "src.audit.audit",
                    "src/audit.py", "python", 1, 2,
                ),
                (
                    "V", "function", "notify", "src.notify.notify",
                    "src/notify.py", "python", 1, 2,
                ),
                (
                    "T", "function", "test_adapt", "tests.test_adapter.test_adapt",
                    "tests/test_adapter.py", "python", 1, 2,
                ),
                (
                    "F", "file", "adapter.py", "src/adapter.py",
                    "src/adapter.py", "python", 1, 2,
                ),
                (
                    "C", "class", "Adapter", "src.adapter.Adapter",
                    "src/adapter.py", "python", 1, 2,
                ),
                (
                    "FX", "file", "core.py", "src/core.py",
                    "src/core.py", "python", 1, 2,
                ),
            ),
        )
        connection.executemany(
            "INSERT INTO edges VALUES (?, ?, ?)",
            (
                ("Y", "X", "calls"),
                ("X", "Z", "calls"),
                ("Z", "W", "calls"),
                ("W", "V", "calls"),
                ("T", "Y", "calls"),
                ("F", "C", "contains"),
                ("C", "Y", "contains"),
                ("FX", "X", "contains"),
            ),
        )
        connection.executemany(
            "INSERT INTO files VALUES (?, ?)",
            tuple(
                (path, hashlib.sha256(source.encode()).hexdigest())
                for path, source in sources.items()
            ),
        )
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=10,
        title="Wire adapter",
        source_records=(),
        changed_files=(
            ChangedFile(
                base_path="src/adapter.py",
                head_path="src/adapter.py",
                patch="@@ -2 +2 @@\n-    return old()\n+    return core()\n",
            ),
        ),
        source_url="https://github.com/acme/widget/pull/10",
        head_sha="head123",
    ).with_revision()

    graph = map_packet_changed_symbols(
        packet, parse_changed_files(packet.changed_files), CodegraphProvider(tmp_path)
    )
    result = graph.for_revision("head")
    assert result is not None

    y_x_z = next(
        path
        for path in result.paths
        if [step.target.id for step in path.steps] == ["X", "Z"]
    )
    assert [step.direction for step in y_x_z.steps] == ["outgoing", "outgoing"]
    assert y_x_z.classification == "runtime"
    assert y_x_z.depth == 2
    assert y_x_z.steps[-1].target.sources[0].url == (
        "https://github.com/acme/widget/blob/head123/src/store.py#L1-L2"
    )
    incoming_test = next(
        path for path in result.paths if [step.target.id for step in path.steps] == ["T"]
    )
    assert incoming_test.steps[0].direction == "incoming"
    assert incoming_test.classification == "mixed"
    assert any(path.depth == 3 and path.steps[-1].target.id == "W" for path in result.paths)
    assert all(step.target.id != "V" for path in result.paths for step in path.steps)
    assert max(path.depth for path in result.paths) == 3
    assert all(step.relation != "contains" for path in result.paths for step in path.steps)
    assert [
        (relation.parent.id, relation.child.id)
        for relation in result.ownership_relations
    ] == [("C", "Y"), ("F", "C"), ("FX", "X")]
    assert result.ownership_relations[0].parent.sources[0].url == (
        "https://github.com/acme/widget/blob/head123/src/adapter.py#L1-L2"
    )


def test_traversal_budgets_are_fair_and_reported_per_seed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def symbol(identifier: str) -> GraphSymbol:
        return GraphSymbol(
            id=identifier,
            kind="function",
            name=identifier,
            qualified_name=identifier,
            file_path=f"src/{identifier}.py",
            language="python",
            start_line=1,
            end_line=2,
            sources=(SourceRef(label=identifier),),
        )

    symbols = {
        identifier: symbol(identifier)
        for identifier in ("A", "A1", "A2", "A3", "B", "B1")
    }
    adjacency = {
        "A": ("A1", "A2", "A3"),
        "B": ("B1",),
    }
    provider = CodegraphProvider(tmp_path)
    monkeypatch.setattr(
        provider,
        "_connect",
        lambda: nullcontext(SimpleNamespace(row_factory=None)),
    )
    monkeypatch.setattr(
        provider,
        "_neighbor_steps",
        lambda _connection, current, _relations: tuple(
            GraphPathStep(
                source=current,
                target=symbols[target],
                relation="calls",
                direction="outgoing",
            )
            for target in adjacency.get(current.id, ())
        ),
    )
    monkeypatch.setattr(provider, "_ownership_parents", lambda *_args: ())
    initial = StructuralGraphResult(
        index=StructuralGraphIndexStatus(state="available", provider="codegraph"),
        hunk_count=2,
        overlaps=(
            HunkSymbolOverlap(hunk_id="H:A", symbol=symbols["A"], changed_lines=(1,)),
            HunkSymbolOverlap(hunk_id="H:B", symbol=symbols["B"], changed_lines=(1,)),
        ),
    )

    result = provider.expand_structure(
        initial,
        policy=StructuralTraversalPolicy(
            max_depth=1,
            max_nodes_per_seed=10,
            max_paths_per_seed=2,
            max_total_nodes=20,
            max_total_paths=10,
        ),
    )

    assert [(item.seed_symbol_id, item.state) for item in result.traversal_coverage] == [
        ("A", "truncated"),
        ("B", "complete"),
    ]
    assert result.traversal_coverage[0].limiting_dimensions == (
        "seed_path_budget",
    )
    assert result.traversal_coverage[0].path_count == 2
    assert result.traversal_coverage[1].path_count == 1
    assert any(item.seed_symbol_id == "B" for item in result.paths)
    assert [item.code for item in result.diagnostics] == [
        "structural_graph_seed_traversal_truncated"
    ]


def test_review_path_budget_is_global_and_round_robin_fair(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def symbol(identifier: str) -> GraphSymbol:
        return GraphSymbol(
            id=identifier,
            kind="function",
            name=identifier,
            qualified_name=identifier,
            file_path=f"src/{identifier}.py",
            language="python",
            start_line=1,
            end_line=2,
        )

    symbols = {
        identifier: symbol(identifier)
        for identifier in ("A", "A1", "A2", "B", "B1", "B2")
    }
    adjacency = {"A": ("A1", "A2"), "B": ("B1", "B2")}
    provider = CodegraphProvider(tmp_path)
    monkeypatch.setattr(
        provider,
        "_connect",
        lambda: nullcontext(SimpleNamespace(row_factory=None)),
    )
    monkeypatch.setattr(
        provider,
        "_neighbor_steps",
        lambda _connection, current, _relations: tuple(
            GraphPathStep(
                source=current,
                target=symbols[target],
                relation="calls",
                direction="outgoing",
            )
            for target in adjacency.get(current.id, ())
        ),
    )
    monkeypatch.setattr(provider, "_ownership_parents", lambda *_args: ())

    result = provider.expand_structure(
        StructuralGraphResult(
            index=StructuralGraphIndexStatus(state="available", provider="codegraph"),
            hunk_count=2,
            overlaps=(
                HunkSymbolOverlap(
                    hunk_id="H:A",
                    symbol=symbols["A"],
                    changed_lines=(1,),
                ),
                HunkSymbolOverlap(
                    hunk_id="H:B",
                    symbol=symbols["B"],
                    changed_lines=(1,),
                ),
            ),
        ),
        policy=StructuralTraversalPolicy(
            max_depth=1,
            max_nodes_per_seed=10,
            max_paths_per_seed=10,
            max_total_nodes=20,
            max_total_paths=2,
        ),
    )

    assert [item.seed_symbol_id for item in result.paths] == ["A", "B"]
    assert len(result.paths) == 2
    assert {
        item.limiting_dimensions for item in result.traversal_coverage
    } == {("review_path_budget",)}


def test_review_budget_retains_direct_paths_before_deeper_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def symbol(identifier: str) -> GraphSymbol:
        return GraphSymbol(
            id=identifier,
            kind="function",
            name=identifier,
            qualified_name=identifier,
            file_path=f"src/{identifier}.py",
            language="python",
            start_line=1,
            end_line=2,
        )

    symbols = {
        identifier: symbol(identifier)
        for identifier in ("A", "A1", "A2", "B", "B1", "B2", "B3")
    }
    adjacency = {
        "A": ("A1",),
        "A1": ("A2",),
        "B": ("B1", "B2", "B3"),
    }
    provider = CodegraphProvider(tmp_path)
    monkeypatch.setattr(
        provider,
        "_connect",
        lambda: nullcontext(SimpleNamespace(row_factory=None)),
    )
    monkeypatch.setattr(
        provider,
        "_neighbor_steps",
        lambda _connection, current, _relations: tuple(
            GraphPathStep(
                source=current,
                target=symbols[target],
                relation="calls",
                direction="outgoing",
            )
            for target in adjacency.get(current.id, ())
        ),
    )
    monkeypatch.setattr(provider, "_ownership_parents", lambda *_args: ())

    result = provider.expand_structure(
        StructuralGraphResult(
            index=StructuralGraphIndexStatus(state="available", provider="codegraph"),
            hunk_count=2,
            overlaps=(
                HunkSymbolOverlap(
                    hunk_id="H:A",
                    symbol=symbols["A"],
                    changed_lines=(1,),
                ),
                HunkSymbolOverlap(
                    hunk_id="H:B",
                    symbol=symbols["B"],
                    changed_lines=(1,),
                ),
            ),
        ),
        policy=StructuralTraversalPolicy(
            max_depth=2,
            max_nodes_per_seed=10,
            max_paths_per_seed=10,
            max_total_nodes=20,
            max_total_paths=3,
        ),
    )

    assert [
        (path.seed_symbol_id, path.depth, path.steps[-1].target.id)
        for path in result.paths
    ] == [
        ("A", 1, "A1"),
        ("B", 1, "B1"),
        ("B", 1, "B2"),
    ]
    assert all(path.depth == 1 for path in result.paths)


def test_per_seed_node_budget_reports_its_limiting_dimension(
    tmp_path: Path,
    monkeypatch,
) -> None:
    seed = GraphSymbol(
        id="seed",
        kind="function",
        name="seed",
        qualified_name="seed",
        file_path="src/seed.py",
        language="python",
        start_line=1,
        end_line=2,
    )
    neighbors = tuple(
        GraphSymbol(
            id=f"neighbor-{index}",
            kind="function",
            name=f"neighbor-{index}",
            qualified_name=f"neighbor-{index}",
            file_path=f"src/neighbor_{index}.py",
            language="python",
            start_line=1,
            end_line=2,
        )
        for index in range(2)
    )
    provider = CodegraphProvider(tmp_path)
    monkeypatch.setattr(
        provider,
        "_connect",
        lambda: nullcontext(SimpleNamespace(row_factory=None)),
    )
    monkeypatch.setattr(
        provider,
        "_neighbor_steps",
        lambda _connection, current, _relations: (
            tuple(
                GraphPathStep(
                    source=current,
                    target=target,
                    relation="calls",
                    direction="outgoing",
                )
                for target in neighbors
            )
            if current.id == seed.id
            else ()
        ),
    )
    monkeypatch.setattr(provider, "_ownership_parents", lambda *_args: ())

    result = provider.expand_structure(
        StructuralGraphResult(
            index=StructuralGraphIndexStatus(state="available", provider="codegraph"),
            hunk_count=1,
            overlaps=(
                HunkSymbolOverlap(
                    hunk_id="H:seed",
                    symbol=seed,
                    changed_lines=(1,),
                ),
            ),
        ),
        policy=StructuralTraversalPolicy(
            max_depth=1,
            max_nodes_per_seed=2,
            max_paths_per_seed=10,
            max_total_nodes=10,
            max_total_paths=10,
        ),
    )

    assert result.traversal_coverage[0].state == "truncated"
    assert result.traversal_coverage[0].node_count == 2
    assert result.traversal_coverage[0].limiting_dimensions == (
        "seed_node_budget",
    )


def test_ownership_ancestry_is_bounded_and_cycle_safe(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def symbol(identifier: str) -> GraphSymbol:
        return GraphSymbol(
            id=identifier,
            kind="class" if identifier != "C" else "method",
            name=identifier,
            qualified_name=identifier,
            file_path="src/service.py",
            language="python",
            start_line=1,
            end_line=4,
        )

    symbols = {identifier: symbol(identifier) for identifier in ("C", "P1", "P2", "P3")}
    parents = {
        "C": ((symbols["P1"], symbols["C"]),),
        "P1": ((symbols["P2"], symbols["P1"]),),
        "P2": ((symbols["P3"], symbols["P2"]),),
        "P3": ((symbols["C"], symbols["P3"]),),
    }
    provider = CodegraphProvider(tmp_path)
    monkeypatch.setattr(
        provider,
        "_connect",
        lambda: nullcontext(SimpleNamespace(row_factory=None)),
    )
    monkeypatch.setattr(provider, "_neighbor_steps", lambda *_args: ())
    monkeypatch.setattr(
        provider,
        "_ownership_parents",
        lambda _connection, child_ids: tuple(
            relation
            for child_id in child_ids
            for relation in parents.get(child_id, ())
        ),
    )

    result = provider.expand_structure(
        StructuralGraphResult(
            index=StructuralGraphIndexStatus(state="available", provider="codegraph"),
            hunk_count=1,
            overlaps=(
                HunkSymbolOverlap(
                    hunk_id="H:C",
                    symbol=symbols["C"],
                    changed_lines=(1,),
                ),
            ),
        ),
        ownership_policy=StructuralOwnershipPolicy(max_depth=2),
    )

    assert [
        (relation.parent.id, relation.child.id)
        for relation in result.ownership_relations
    ] == [("P1", "C"), ("P2", "P1")]
    assert [item.code for item in result.diagnostics] == [
        "structural_graph_ownership_truncated"
    ]
    assert result.ownership_coverage is not None
    assert result.ownership_coverage.state == "truncated"
    assert result.ownership_coverage.observed_symbol_ids == ("C",)
    assert result.ownership_coverage.relation_count == 2
    assert result.ownership_coverage.limiting_dimensions == ("depth_budget",)

    cycle_relations, limiting_dimensions = provider._collect_ownership_relations(
        SimpleNamespace(),
        (symbols["C"],),
        policy=StructuralOwnershipPolicy(max_depth=8),
    )
    assert [
        (relation.parent.id, relation.child.id)
        for relation in cycle_relations
    ] == [("P1", "C"), ("P2", "P1"), ("P3", "P2")]
    assert limiting_dimensions == ()
