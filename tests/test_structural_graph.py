from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from prismcode.pipeline import DeterministicAnalyzer
from prismcode.providers.codegraph import CodegraphProvider
from prismcode.model.contracts import AnalysisInput, ChangedFile, ReviewSourcePacket
from prismcode.changes.hunks import parse_changed_files, parse_unified_patch
from prismcode.providers.structural import StructuralGraphProvider
from prismcode.providers.mapping import map_packet_changed_symbols


def _create_index(
    root: Path,
    *,
    source: str = "class Service:\n    def run(self):\n        return 1\n",
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
        connection.executemany(
            """
            INSERT INTO nodes
                (id, kind, name, qualified_name, file_path, language,
                 start_line, end_line)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
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
                (
                    "method:Service.run",
                    "method",
                    "run",
                    "src.service.Service.run",
                    "src/service.py",
                    "python",
                    2,
                    3,
                ),
            ),
        )
        connection.execute(
            "INSERT INTO files (path, content_hash) VALUES (?, ?)",
            ("src/service.py", hashlib.sha256(source.encode()).hexdigest()),
        )
    return database


def _packet(patch: str | None) -> ReviewSourcePacket:
    return ReviewSourcePacket(
        repository="acme/widget",
        pull_request=7,
        title="Change service",
        source_url="https://github.com/acme/widget/pull/7",
        head_sha="head123",
        source_records=(),
        changed_files=(
            ChangedFile(
                path="src/service.py",
                patch=patch,
                source_url="https://github.com/acme/widget/pull/7/files",
            ),
        ),
    ).with_revision()


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
    assert len(hunks[0].spans) == 2
    assert hunks[0].spans[0].old_snippet == "old_first()"
    assert hunks[0].spans[0].new_snippet == "new_first()"
    assert hunks[0].spans[1].old_snippet == "old_second()"
    assert hunks[0].spans[1].new_snippet == "new_second()"


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
    result = map_packet_changed_symbols(
        packet, parse_changed_files(packet.changed_files), CodegraphProvider(tmp_path)
    )

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
    result = map_packet_changed_symbols(
        packet, parse_changed_files(packet.changed_files), CodegraphProvider(tmp_path)
    )

    assert [(item.symbol.id, item.changed_lines) for item in result.overlaps] == [
        ("first", (2,)),
        ("second", (5,)),
    ]


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


def test_deletion_only_hunk_reports_base_index_requirement(tmp_path: Path) -> None:
    _create_index(tmp_path)
    hunks = parse_unified_patch(
        "src/service.py",
        "@@ -2,1 +2,0 @@\n-    def run(self):\n",
    )

    result = CodegraphProvider(tmp_path).symbols_overlapping(hunks)

    assert result.overlaps == ()
    assert "structural_graph_base_index_required" in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_missing_patch_is_explicitly_reported(tmp_path: Path) -> None:
    _create_index(tmp_path)

    packet = _packet(None)
    result = map_packet_changed_symbols(
        packet, parse_changed_files(packet.changed_files), CodegraphProvider(tmp_path)
    )

    assert result.overlaps == ()
    assert [item.code for item in result.diagnostics] == [
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

    assert brief.schema_version == "review_brief.v17"
    assert brief.requirements == lexical_only.requirements == ()
    serialized = brief.to_dict()
    assert "structural_graph" not in serialized
    symbol = next(
        item for item in serialized["evidence_catalog"]["items"]
        if item["kind"] == "symbol"
    )
    assert symbol["metadata"]["qualified_name"] == "src.service.Service.run"


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
                ("F", "Y", "contains"),
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
                path="src/adapter.py",
                patch="@@ -2 +2 @@\n-    return old()\n+    return core()\n",
            ),
        ),
        source_url="https://github.com/acme/widget/pull/10",
        head_sha="head123",
    ).with_revision()

    result = map_packet_changed_symbols(
        packet, parse_changed_files(packet.changed_files), CodegraphProvider(tmp_path)
    )

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
