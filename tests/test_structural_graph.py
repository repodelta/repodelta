from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from prismcode.codegraph import CodegraphProvider
from prismcode.contracts import ChangedFile, ReviewSourcePacket
from prismcode.diff_hunks import parse_unified_patch
from prismcode.structural_graph import StructuralGraphProvider
from prismcode.structural_mapping import map_packet_changed_symbols


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
    assert hunks[0].new_snippet == "    def run(self):"


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

    result = map_packet_changed_symbols(_packet(patch), CodegraphProvider(tmp_path))

    assert result.index.state == "available"
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

    result = map_packet_changed_symbols(_packet(patch), CodegraphProvider(tmp_path))

    assert [(item.symbol.id, item.changed_lines) for item in result.overlaps] == [
        ("first", (2,)),
        ("second", (5,)),
    ]


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

    result = map_packet_changed_symbols(_packet(None), CodegraphProvider(tmp_path))

    assert result.overlaps == ()
    assert [item.code for item in result.diagnostics] == [
        "structural_graph_patch_unavailable"
    ]
