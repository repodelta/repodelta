from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from prismcode.cli import main
from prismcode.model.contracts import ChangedFile, ReviewSourcePacket, SourceRecord


def _write_fixture(tmp_path: Path, *, body: str | None = None) -> Path:
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=12,
        title="Update service",
        source_records=(
            (
                SourceRecord(
                    id="pr:12",
                    kind="pull_request",
                    repository="acme/widget",
                    title="Update service",
                    body=body,
                ),
            )
            if body is not None
            else ()
        ),
        changed_files=(
            ChangedFile(
                base_path="src/service.py",
                head_path="src/service.py",
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
    source: str = "def run():\n    return 2\n",
    content_hash: str | None = None,
    include_file: bool = True,
) -> None:
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
    assert "base unavailable · uncovered change relations retained" in captured.err


def test_cli_missing_index_uses_change_relation_fallback(
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
        "change-relation fallback used"
    ) in capsys.readouterr().err


def test_cli_shadow_without_provider_is_unavailable_and_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("PRISMCODE_LLM_MODEL", raising=False)
    fixture = _write_fixture(tmp_path)
    output = tmp_path / "review.html"

    assert _run_cli(
        monkeypatch,
        fixture,
        tmp_path / "repo",
        output,
        "--llm-shadow",
    ) == 0

    artifact = Path(f"{output}.llm-shadow.json")
    assert artifact.exists()
    assert json.loads(artifact.read_text(encoding="utf-8"))["summary"] == {
        "admitted_count": 0,
        "artifact_written": True,
        "completed_count": 0,
        "deferred_count": 0,
        "failed_count": 0,
        "state": "unavailable",
    }
    assert "LLM shadow: unavailable" in output.read_text(encoding="utf-8")
    assert "LLM shadow: unavailable" in capsys.readouterr().err


def test_cli_prepares_labeling_packet_without_invoking_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("PRISMCODE_LLM_MODEL", raising=False)
    fixture = _write_fixture(tmp_path)
    output = tmp_path / "review.html"
    packet = tmp_path / "labeling.json"

    assert _run_cli(
        monkeypatch,
        fixture,
        tmp_path / "repo",
        output,
        "--llm-shadow-labeling-output",
        str(packet),
    ) == 0

    raw = json.loads(packet.read_text(encoding="utf-8"))
    assert raw["schema_version"] == "llm_shadow_labeling_packet.v1"
    assert raw["admissions"] == []
    assert "LLM shadow: off" in output.read_text(encoding="utf-8")
    assert str(packet) in capsys.readouterr().out


def test_cli_blinded_run_requires_exact_packet_and_complete_labels_before_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _write_fixture(
        tmp_path,
        body="## Change\n- Update service behavior.\n",
    )
    packet_path = tmp_path / "labeling.json"
    assert _run_cli(
        monkeypatch,
        fixture,
        tmp_path / "repo",
        tmp_path / "prepare.html",
        "--llm-shadow-labeling-output",
        str(packet_path),
    ) == 0
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    request = packet["admissions"][0]["request"]
    assert request is not None
    selections = [
        {
            "evidence_id": item["evidence_id"],
            "role": "supporting",
            "semantic_role": "unknown",
            "rationale": "Test-only frozen disposition.",
        }
        for item in request["candidates"]
    ]
    response = {
        "schema_version": request["schema_version"],
        "request_id": request["request_id"],
        "subject_id": request["subject_id"],
        "selections": selections,
        "rejected_evidence_ids": [],
        "insufficient_evidence_ids": [],
        "unresolved_surfaces": request["coverage_limits"],
    }
    labels_path = tmp_path / "labels.json"
    labels_path.write_text(
        json.dumps(
            {
                "schema_version": "llm_shadow_human_labels.v1",
                "authority": "human_review",
                "rubric_version": "test.v1",
                "labels": [
                    {"claim_id": request["subject_id"], "response": response}
                ],
            }
        ),
        encoding="utf-8",
    )
    replay_path = tmp_path / "replay.json"
    replay_path.write_text(
        json.dumps({"request": request, "response": response}),
        encoding="utf-8",
    )
    output = tmp_path / "executed.html"

    assert _run_cli(
        monkeypatch,
        fixture,
        tmp_path / "repo",
        output,
        "--llm-shadow",
        "--llm-shadow-labeling-input",
        str(packet_path),
        "--llm-shadow-human-labels",
        str(labels_path),
        "--llm-shadow-replay",
        str(replay_path),
    ) == 0

    execution = json.loads(
        Path(f"{output}.llm-shadow.json").read_text(encoding="utf-8")
    )
    assert execution["summary"]["completed_count"] == 1
    assert execution["observations"][0]["request"] == request


def test_cli_blinded_run_rejects_packet_drift_before_provider_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _write_fixture(
        tmp_path,
        body="## Change\n- Update service behavior.\n",
    )
    packet_path = tmp_path / "labeling.json"
    assert _run_cli(
        monkeypatch,
        fixture,
        tmp_path / "repo",
        tmp_path / "prepare.html",
        "--llm-shadow-labeling-output",
        str(packet_path),
    ) == 0
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["head_sha"] = "different-head"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    output = tmp_path / "drifted.html"

    assert _run_cli(
        monkeypatch,
        fixture,
        tmp_path / "repo",
        output,
        "--llm-shadow",
        "--llm-shadow-labeling-input",
        str(packet_path),
        "--llm-shadow-human-labels",
        str(tmp_path / "must-not-be-read.json"),
    ) == 2

    assert not Path(f"{output}.llm-shadow.json").exists()


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
        "change-relation fallback used"
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
                base_path="src/unindexed.py",
                head_path="src/unindexed.py",
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
        "base unavailable · change-relation fallback used for uncovered changes"
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
        "Structural mapping: disabled · change-relation fallback used"
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
