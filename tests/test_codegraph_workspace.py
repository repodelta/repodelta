from __future__ import annotations

import base64
import os
import shutil
import subprocess
from pathlib import Path
from typing import Mapping

import pytest

from repodelta.providers.workspace import (
    _codegraph_command,
    _initialize_index,
    isolated_review_roots,
    remote_review_roots,
)


class FakeRunner:
    def __init__(
        self,
        *,
        fail_index_side: str = "",
        fail_cleanup: bool = False,
        revisions: dict[str, str] | None = None,
    ) -> None:
        self.fail_index_side = fail_index_side
        self.fail_cleanup = fail_cleanup
        self.commands: list[tuple[str, ...]] = []
        self.managed_roots: dict[str, Path] = {}
        self.revisions = revisions or {
            "refs/repodelta/head": "head123",
            "refs/repodelta/base": "base123",
        }

    def __call__(
        self,
        command: tuple[str, ...],
        _timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        if command[:2] == ("fake-codegraph", "init"):
            root = Path(command[2]).resolve()
            if root.name == self.fail_index_side:
                return subprocess.CompletedProcess(
                    command,
                    1,
                    "",
                    f"{root.name} index failed",
                )
            database = root / ".codegraph" / "codegraph.db"
            database.parent.mkdir(parents=True, exist_ok=True)
            database.touch()
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[0] != "git":
            raise AssertionError(command)

        operation = command[3:]
        if operation[:1] == ("rev-parse",):
            return subprocess.CompletedProcess(
                command,
                0,
                self.revisions[operation[1]] + "\n",
                "",
            )
        if operation[:3] == ("worktree", "add", "--detach"):
            target = Path(operation[3]).resolve()
            target.mkdir(parents=True)
            self.managed_roots[target.name] = target
            return subprocess.CompletedProcess(command, 0, "", "")
        if operation[:3] == ("worktree", "remove", "--force"):
            target = Path(operation[3]).resolve()
            if self.fail_cleanup:
                return subprocess.CompletedProcess(
                    command,
                    1,
                    "",
                    "cleanup failed",
                )
            shutil.rmtree(target)
            return subprocess.CompletedProcess(command, 0, "", "")
        if operation == ("worktree", "prune"):
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(command)


class FakeFetchRunner:
    def __init__(self, *, failure: str = "") -> None:
        self.failure = failure
        self.calls: list[
            tuple[tuple[str, ...], dict[str, str]]
        ] = []

    def __call__(
        self,
        command: tuple[str, ...],
        _timeout: int,
        environment: Mapping[str, str],
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append((command, dict(environment)))
        if command[:3] == ("git", "init", "--bare"):
            Path(command[3]).mkdir(parents=True)
        if self.failure and "fetch" in command:
            return subprocess.CompletedProcess(
                command,
                1,
                "",
                self.failure,
            )
        return subprocess.CompletedProcess(command, 0, "", "")


def _commands(
    runner: FakeRunner,
    prefix: tuple[str, ...],
) -> tuple[tuple[str, ...], ...]:
    return tuple(
        command for command in runner.commands if command[: len(prefix)] == prefix
    )


def test_supported_installed_codegraph_is_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    def runner(
        command: tuple[str, ...], _timeout: int
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            "Initialize CodeGraph and build the project index",
            "",
        )

    monkeypatch.setattr(
        shutil,
        "which",
        lambda name: "/tools/codegraph" if name == "codegraph" else None,
    )

    assert _codegraph_command(runner=runner) == ("/tools/codegraph",)
    assert calls == [("/tools/codegraph", "init", "--help")]


def test_unrelated_same_name_executable_falls_back_to_scoped_npx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def runner(
        command: tuple[str, ...], _timeout: int
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            0,
            "Utilities for Python source graphs",
            "",
        )

    locations = {
        "codegraph": "/python/bin/codegraph",
        "npx": "/node/bin/npx",
    }
    monkeypatch.setattr(shutil, "which", locations.get)

    assert _codegraph_command(runner=runner) == (
        "/node/bin/npx",
        "--yes",
        "@colbymchenry/codegraph@1.2.0",
    )


def test_npx_only_environment_uses_scoped_tested_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        shutil,
        "which",
        lambda name: "/node/bin/npx" if name == "npx" else None,
    )

    assert _codegraph_command() == (
        "/node/bin/npx",
        "--yes",
        "@colbymchenry/codegraph@1.2.0",
    )


def test_missing_supported_codegraph_names_scoped_package_and_pypi_collision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)

    with pytest.raises(ValueError) as captured:
        _codegraph_command()

    message = str(captured.value)
    assert "@colbymchenry/codegraph" in message
    assert "unrelated PyPI `codegraph`" in message
    assert "--no-structural-graph" in message


def test_successful_command_without_codegraph_index_fails_closed(
    tmp_path: Path,
) -> None:
    def runner(
        command: tuple[str, ...], _timeout: int
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, "done", "")

    with pytest.raises(ValueError) as captured:
        _initialize_index(
            tmp_path,
            runner=runner,
            codegraph_command=("same-name-command",),
        )

    message = str(captured.value)
    assert ".codegraph/codegraph.db" in message
    assert "@colbymchenry/codegraph" in message
    assert "unrelated PyPI `codegraph`" in message


def test_head_and_base_indexes_are_private_and_removed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    caller_database = source / ".codegraph" / "codegraph.db"
    caller_database.parent.mkdir()
    caller_database.write_text("caller owned", encoding="utf-8")
    runner = FakeRunner()

    with isolated_review_roots(
        repo_root=source,
        head_revision="head123",
        base_revision="base123",
        structural_graph_enabled=True,
        runner=runner,
        codegraph_command=("fake-codegraph",),
    ) as roots:
        assert roots.head != source.resolve()
        assert roots.base is not None
        assert roots.base != source.resolve()
        assert roots.head.parent == roots.base.parent
        assert (roots.head / ".codegraph" / "codegraph.db").is_file()
        assert (roots.base / ".codegraph" / "codegraph.db").is_file()
        managed_parent = roots.head.parent

    assert not managed_parent.exists()
    assert caller_database.read_text(encoding="utf-8") == "caller owned"
    assert len(_commands(runner, ("fake-codegraph", "init"))) == 2
    assert len(_commands(runner, ("git", "-C"))) == 4


def test_all_private_roots_are_removed_when_base_indexing_fails(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    runner = FakeRunner(fail_index_side="base")

    with pytest.raises(ValueError, match="base index failed"):
        with isolated_review_roots(
            repo_root=source,
            head_revision="head123",
            base_revision="base123",
            structural_graph_enabled=True,
            runner=runner,
            codegraph_command=("fake-codegraph",),
        ):
            raise AssertionError("index failure must prevent review")

    assert set(runner.managed_roots) == {"head", "base"}
    assert not any(root.exists() for root in runner.managed_roots.values())


def test_all_private_roots_are_removed_when_review_body_fails(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    runner = FakeRunner()

    with pytest.raises(RuntimeError, match="render failed"):
        with isolated_review_roots(
            repo_root=source,
            head_revision="head123",
            base_revision="base123",
            structural_graph_enabled=True,
            runner=runner,
            codegraph_command=("fake-codegraph",),
        ):
            raise RuntimeError("render failed")

    assert not any(root.exists() for root in runner.managed_roots.values())


def test_cleanup_failure_still_removes_private_directory(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    runner = FakeRunner(fail_cleanup=True)

    with pytest.raises(ValueError, match="cleanup failed"):
        with isolated_review_roots(
            repo_root=source,
            head_revision="head123",
            base_revision="base123",
            structural_graph_enabled=True,
            runner=runner,
            codegraph_command=("fake-codegraph",),
        ) as roots:
            managed_parent = roots.head.parent

    assert not managed_parent.exists()
    assert _commands(runner, ("git", "-C"))[-1][3:] == ("worktree", "prune")


def test_no_structural_graph_creates_only_private_head_without_codegraph(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    runner = FakeRunner()

    def reject_resolution(_name: str) -> None:
        raise AssertionError("CodeGraph resolution must remain disabled")

    monkeypatch.setattr(shutil, "which", reject_resolution)

    with isolated_review_roots(
        repo_root=source,
        head_revision="head123",
        base_revision="",
        structural_graph_enabled=False,
        runner=runner,
    ) as roots:
        assert roots.head.exists()
        assert roots.base is None
        managed_head = roots.head

    assert not managed_head.exists()
    assert not _commands(runner, ("fake-codegraph",))


@pytest.mark.parametrize(
    ("head_revision", "base_revision", "message"),
    (
        ("", "base123", "head SHA"),
        ("head123", "", "base SHA"),
    ),
)
def test_required_revision_is_validated_before_worktree_creation(
    tmp_path: Path,
    head_revision: str,
    base_revision: str,
    message: str,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    runner = FakeRunner()

    with pytest.raises(ValueError, match=message):
        with isolated_review_roots(
            repo_root=source,
            head_revision=head_revision,
            base_revision=base_revision,
            structural_graph_enabled=True,
            runner=runner,
            codegraph_command=("fake-codegraph",),
        ):
            raise AssertionError("missing revision must prevent review")

    assert runner.commands == []


def test_live_review_workflow_uses_default_remote_workspace() -> None:
    workflow = Path(".github/workflows/review.yml").read_text(encoding="utf-8")

    assert "fetch-depth" not in workflow
    review_command = next(
        line for line in workflow.splitlines()
        if "repodelta review --repo" in line
    )
    assert "--repo-root" not in review_command


def test_remote_review_fetches_exact_private_revisions_without_persisting_token(
    tmp_path: Path,
) -> None:
    fetch_runner = FakeFetchRunner()
    workspace_runner = FakeRunner()
    secret = "github-secret-token"

    with remote_review_roots(
        repository="acme/widget",
        pull_request=42,
        api_url="https://api.github.com",
        token=secret,
        head_revision="head123",
        base_revision="base123",
        structural_graph_enabled=True,
        fetch_runner=fetch_runner,
        workspace_runner=workspace_runner,
        codegraph_command=("fake-codegraph",),
    ) as roots:
        managed_parent = roots.head.parent
        remote_parent = Path(fetch_runner.calls[0][0][3]).parent
        assert roots.head.exists()
        assert roots.base is not None and roots.base.exists()

    commands = [command for command, _ in fetch_runner.calls]
    fetch = next(command for command in commands if "fetch" in command)
    assert "--filter=blob:none" not in fetch
    assert "+refs/pull/42/head:refs/repodelta/head" in fetch
    assert "+base123:refs/repodelta/base" in fetch
    assert any("https://github.com/acme/widget.git" in command for command in commands)
    assert all(secret not in argument for command in commands for argument in command)
    encoded = base64.b64encode(
        f"x-access-token:{secret}".encode("utf-8")
    ).decode("ascii")
    authenticated = [
        environment
        for command, environment in fetch_runner.calls
        if "fetch" in command
    ]
    unauthenticated = [
        environment
        for command, environment in fetch_runner.calls
        if "fetch" not in command
    ]
    assert authenticated == [
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.extraHeader",
            "GIT_CONFIG_VALUE_0": f"Authorization: Basic {encoded}",
        }
    ]
    assert all("GIT_CONFIG_VALUE_0" not in item for item in unauthenticated)
    assert not managed_parent.exists()
    assert not remote_parent.exists()
    assert len(_commands(workspace_runner, ("fake-codegraph", "init"))) == 2


def test_remote_no_structural_review_fetches_only_head() -> None:
    fetch_runner = FakeFetchRunner()
    workspace_runner = FakeRunner()

    with remote_review_roots(
        repository="acme/widget",
        pull_request=42,
        api_url="https://github.example/enterprise/api/v3",
        token=None,
        head_revision="head123",
        base_revision="",
        structural_graph_enabled=False,
        fetch_runner=fetch_runner,
        workspace_runner=workspace_runner,
    ) as roots:
        assert roots.head.exists()
        assert roots.base is None

    fetch = next(
        command for command, _ in fetch_runner.calls if "fetch" in command
    )
    assert "+refs/pull/42/head:refs/repodelta/head" in fetch
    assert not any("refs/repodelta/base" in argument for argument in fetch)
    assert any(
        "https://github.example/enterprise/acme/widget.git" in command
        for command, _ in fetch_runner.calls
    )
    assert all(
        "GIT_CONFIG_VALUE_0" not in environment
        for _, environment in fetch_runner.calls
    )
    assert not _commands(workspace_runner, ("fake-codegraph",))


def test_remote_review_rejects_revision_mismatch_and_removes_source() -> None:
    fetch_runner = FakeFetchRunner()
    workspace_runner = FakeRunner(
        revisions={
            "refs/repodelta/head": "different",
            "refs/repodelta/base": "base123",
        }
    )

    with pytest.raises(ValueError, match="head does not match"):
        with remote_review_roots(
            repository="acme/widget",
            pull_request=42,
            api_url="https://api.github.com",
            token=None,
            head_revision="head123",
            base_revision="base123",
            structural_graph_enabled=True,
            fetch_runner=fetch_runner,
            workspace_runner=workspace_runner,
            codegraph_command=("fake-codegraph",),
        ):
            raise AssertionError("mismatched revision must prevent review")

    remote_parent = Path(fetch_runner.calls[0][0][3]).parent
    assert not remote_parent.exists()
    assert not _commands(workspace_runner, ("fake-codegraph",))


@pytest.mark.parametrize("failure", ("index", "review"))
def test_remote_review_removes_every_owned_root_after_downstream_failure(
    failure: str,
) -> None:
    fetch_runner = FakeFetchRunner()
    workspace_runner = FakeRunner(
        fail_index_side="base" if failure == "index" else ""
    )

    expected = ValueError if failure == "index" else RuntimeError
    match = "base index failed" if failure == "index" else "render failed"
    with pytest.raises(expected, match=match):
        with remote_review_roots(
            repository="acme/widget",
            pull_request=42,
            api_url="https://api.github.com",
            token=None,
            head_revision="head123",
            base_revision="base123",
            structural_graph_enabled=True,
            fetch_runner=fetch_runner,
            workspace_runner=workspace_runner,
            codegraph_command=("fake-codegraph",),
        ):
            if failure == "review":
                raise RuntimeError("render failed")

    remote_parent = Path(fetch_runner.calls[0][0][3]).parent
    assert not remote_parent.exists()
    assert not any(root.exists() for root in workspace_runner.managed_roots.values())


@pytest.mark.parametrize("encoded", (False, True))
def test_remote_fetch_failure_redacts_token_and_removes_source(
    encoded: bool,
) -> None:
    secret = "github-secret-token"
    exposed = (
        base64.b64encode(f"x-access-token:{secret}".encode()).decode()
        if encoded
        else secret
    )
    fetch_runner = FakeFetchRunner(failure=f"access denied for {exposed}")

    with pytest.raises(ValueError) as captured:
        with remote_review_roots(
            repository="acme/widget",
            pull_request=42,
            api_url="https://api.github.com",
            token=secret,
            head_revision="head123",
            base_revision="base123",
            structural_graph_enabled=True,
            fetch_runner=fetch_runner,
        ):
            raise AssertionError("fetch failure must prevent review")

    assert secret not in str(captured.value)
    assert exposed not in str(captured.value)
    assert "[redacted]" in str(captured.value)
    remote_parent = Path(fetch_runner.calls[0][0][3]).parent
    assert not remote_parent.exists()
