from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from prismcode.cli import main
from prismcode.model.contracts import ChangedFile, ReviewSourcePacket


def _write_fixture(tmp_path: Path) -> Path:
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=12,
        title="Update service",
        source_records=(),
        changed_files=(
            ChangedFile(
                path="src/service.py",
                patch=(
                    "@@ -1,2 +1,2 @@\n"
                    " def run():\n"
                    "-    return 1\n"
                    "+    return 2\n"
                ),
            ),
        ),
    ).with_revision()
    fixture = tmp_path / "review.json"
    fixture.write_text(
        json.dumps(
            {
                "schema_version": "analysis_fixture.v3",
                "source_packet": asdict(packet),
                "requirements": [],
                "evidence": [],
            }
        ),
        encoding="utf-8",
    )
    return fixture


def _write_index(
    repo_root: Path,
    *,
    content_hash: str | None = None,
    include_file: bool = True,
) -> None:
    source = "def run():\n    return 2\n"
    source_path = repo_root / "src" / "service.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(source, encoding="utf-8")
    database = repo_root / ".codegraph" / "codegraph.db"
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
        connection.execute(
            "INSERT INTO nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "function:run",
                "function",
                "run",
                "run",
                "src/service.py",
                "python",
                1,
                2,
            ),
        )
        if include_file:
            connection.execute(
                "INSERT INTO files VALUES (?, ?)",
                (
                    "src/service.py",
                    content_hash or hashlib.sha256(source.encode()).hexdigest(),
                ),
            )


def _run_cli(
    monkeypatch: pytest.MonkeyPatch,
    fixture: Path,
    repo_root: Path,
    output: Path,
    *extra: str,
) -> int:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prismcode",
            "review",
            "--fixture",
            str(fixture),
            "--repo-root",
            str(repo_root),
            "--output",
            str(output),
            *extra,
        ],
    )
    return main()


def test_cli_runs_available_codegraph_mapping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = _write_fixture(tmp_path)
    repo_root = tmp_path / "repo"
    _write_index(repo_root)

    assert _run_cli(
        monkeypatch, fixture, repo_root, tmp_path / "review.html"
    ) == 0

    captured = capsys.readouterr()
    assert "Structural mapping: Codegraph available" in captured.err
    assert "1/1 hunks mapped to 1 symbols" in captured.err
    assert "uncovered change spans retained" in captured.err


def test_cli_missing_index_uses_changed_span_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = _write_fixture(tmp_path)

    assert _run_cli(
        monkeypatch, fixture, tmp_path / "repo", tmp_path / "review.html"
    ) == 0

    assert (
        "Structural mapping: skipped · Codegraph index not found · "
        "changed-span fallback used"
    ) in capsys.readouterr().err


def test_cli_stale_index_is_skipped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = _write_fixture(tmp_path)
    repo_root = tmp_path / "repo"
    _write_index(repo_root, content_hash="stale")

    assert _run_cli(
        monkeypatch, fixture, repo_root, tmp_path / "review.html"
    ) == 0

    assert (
        "Structural mapping: skipped · Codegraph index is stale · "
        "changed-span fallback used"
    ) in capsys.readouterr().err


def test_cli_partial_index_reports_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = _write_fixture(tmp_path)
    raw = json.loads(fixture.read_text(encoding="utf-8"))
    packet_raw = raw["source_packet"]
    packet_raw["changed_files"].append(
        asdict(
            ChangedFile(
                path="src/unindexed.py",
                patch="@@ -0,0 +1 @@\n+VALUE = 1\n",
            )
        )
    )
    packet = ReviewSourcePacket(
        repository=packet_raw["repository"],
        pull_request=packet_raw["pull_request"],
        title=packet_raw["title"],
        source_records=(),
        changed_files=tuple(ChangedFile(**row) for row in packet_raw["changed_files"]),
    ).with_revision()
    raw["source_packet"] = asdict(packet)
    fixture.write_text(json.dumps(raw), encoding="utf-8")
    repo_root = tmp_path / "repo"
    _write_index(repo_root)

    assert _run_cli(
        monkeypatch, fixture, repo_root, tmp_path / "review.html"
    ) == 0

    assert (
        "Structural mapping: partial · 1/2 changed files indexed · "
        "changed-span fallback used for uncovered changes"
    ) in capsys.readouterr().err


def test_cli_can_explicitly_disable_structural_mapping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = _write_fixture(tmp_path)

    assert _run_cli(
        monkeypatch,
        fixture,
        tmp_path / "repo",
        tmp_path / "review.html",
        "--no-structural-graph",
    ) == 0

    assert (
        "Structural mapping: disabled · changed-span fallback used"
    ) in capsys.readouterr().err


def test_cli_verbose_prints_structural_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = _write_fixture(tmp_path)

    assert _run_cli(
        monkeypatch,
        fixture,
        tmp_path / "repo",
        tmp_path / "review.html",
        "--verbose",
    ) == 0

    stderr = capsys.readouterr().err
    assert "Structural mapping: skipped" in stderr
    assert (
        "  - Structural coverage · codegraph · provider unavailable:"
        in stderr
    )
