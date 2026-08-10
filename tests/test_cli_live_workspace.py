from __future__ import annotations

import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

import repodelta.cli as cli
from repodelta.model.contracts import ChangedFile, ReviewSourcePacket, SourceRecord
from repodelta.providers.workspace import ReviewRevisionRoots


def _repository(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repository"
    root.mkdir()
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    (root / "service.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(root), "add", "service.py"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=RepoDelta Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "test",
        ],
        check=True,
        capture_output=True,
    )
    revision = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return root, revision


def _packet(revision: str) -> ReviewSourcePacket:
    return ReviewSourcePacket(
        repository="acme/widget",
        pull_request=42,
        title="Review remote workspace",
        source_records=(
            SourceRecord(
                id="github-pr:acme/widget#42",
                kind="pull_request",
                repository="acme/widget",
                title="Review remote workspace",
                body="## Requirements\n- Preserve the reviewed revision.",
            ),
        ),
        changed_files=(
            ChangedFile(
                base_path="service.py",
                head_path="service.py",
                patch="@@ -1 +1 @@\n-VALUE = 0\n+VALUE = 1\n",
            ),
        ),
        head_sha=revision,
        base_sha="base123",
    ).with_revision()


def _run(
    monkeypatch: pytest.MonkeyPatch,
    output: Path,
    *extra: str,
) -> int:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "repodelta",
            "review",
            "--repo",
            "acme/widget",
            "--pr",
            "42",
            "--no-structural-graph",
            "--output",
            str(output),
            *extra,
        ],
    )
    return cli.main()


def test_live_cli_uses_remote_workspace_when_repo_root_is_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, revision = _repository(tmp_path)
    packet = _packet(revision)
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(cli, "_resolve_github_token", lambda *_: "secret")
    monkeypatch.setattr(
        cli.GitHubPullRequestAdapter,
        "load",
        lambda *_: packet,
    )

    @contextmanager
    def remote(**kwargs: object):
        calls.append(kwargs)
        yield ReviewRevisionRoots(head=root)

    monkeypatch.setattr(cli, "remote_review_roots", remote)
    monkeypatch.setattr(
        cli,
        "isolated_review_roots",
        lambda **_: (_ for _ in ()).throw(AssertionError("local path selected")),
    )
    output = tmp_path / "remote.html"

    assert _run(monkeypatch, output) == 0
    assert output.is_file()
    assert calls == [
        {
            "repository": "acme/widget",
            "pull_request": 42,
            "api_url": "https://api.github.com",
            "token": "secret",
            "head_revision": revision,
            "base_revision": "base123",
            "structural_graph_enabled": False,
        }
    ]


def test_live_cli_repo_root_explicitly_selects_local_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, revision = _repository(tmp_path)
    packet = _packet(revision)
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(cli, "_resolve_github_token", lambda *_: None)
    monkeypatch.setattr(
        cli.GitHubPullRequestAdapter,
        "load",
        lambda *_: packet,
    )

    @contextmanager
    def local(**kwargs: object):
        calls.append(kwargs)
        yield ReviewRevisionRoots(head=root)

    monkeypatch.setattr(cli, "isolated_review_roots", local)
    monkeypatch.setattr(
        cli,
        "remote_review_roots",
        lambda **_: (_ for _ in ()).throw(AssertionError("remote path selected")),
    )
    output = tmp_path / "local.html"

    assert _run(monkeypatch, output, "--repo-root", str(root)) == 0
    assert output.is_file()
    assert calls == [
        {
            "repo_root": str(root),
            "head_revision": revision,
            "base_revision": "base123",
            "structural_graph_enabled": False,
        }
    ]
