from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from prismcode.providers.workspace import prepared_codegraph_roots


class FakeRunner:
    def __init__(
        self,
        revisions: dict[Path, str],
        *,
        fail_base_index: bool = False,
        fail_cleanup: bool = False,
    ) -> None:
        self.revisions = {path.resolve(): revision for path, revision in revisions.items()}
        self.fail_base_index = fail_base_index
        self.fail_cleanup = fail_cleanup
        self.commands: list[tuple[str, ...]] = []
        self.managed_base: Path | None = None

    def __call__(
        self,
        command: tuple[str, ...],
        _timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        if command[:2] == ("fake-codegraph", "init"):
            root = Path(command[2]).resolve()
            if self.fail_base_index and root == self.managed_base:
                return subprocess.CompletedProcess(
                    command, 1, "", "base index failed"
                )
            database = root / ".codegraph" / "codegraph.db"
            database.parent.mkdir(parents=True, exist_ok=True)
            database.touch()
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:2] == ("fake-codegraph", "sync"):
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[0] != "git":
            raise AssertionError(command)

        root = Path(command[2]).resolve()
        operation = command[3:]
        if operation == ("rev-parse", "HEAD"):
            return subprocess.CompletedProcess(
                command, 0, self.revisions[root] + "\n", ""
            )
        if operation == (
            "status",
            "--porcelain",
            "--untracked-files=no",
        ):
            return subprocess.CompletedProcess(command, 0, "", "")
        if operation[:3] == ("worktree", "add", "--detach"):
            target = Path(operation[3]).resolve()
            target.mkdir(parents=True)
            self.managed_base = target
            self.revisions[target] = operation[4]
            return subprocess.CompletedProcess(command, 0, "", "")
        if operation[:3] == ("worktree", "remove", "--force"):
            target = Path(operation[3]).resolve()
            if self.fail_cleanup:
                return subprocess.CompletedProcess(
                    command, 1, "", "cleanup failed"
                )
            shutil.rmtree(target)
            self.revisions.pop(target, None)
            return subprocess.CompletedProcess(command, 0, "", "")
        if operation == ("worktree", "prune"):
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(command)


def _command_names(runner: FakeRunner) -> tuple[tuple[str, ...], ...]:
    return tuple(command[:2] for command in runner.commands)


def test_missing_head_index_is_initialized_and_managed_base_is_removed(
    tmp_path: Path,
) -> None:
    head = tmp_path / "head"
    head.mkdir()
    runner = FakeRunner({head: "head123"})

    with prepared_codegraph_roots(
        repo_root=head,
        head_revision="head123",
        base_revision="base123",
        runner=runner,
        codegraph_command=("fake-codegraph",),
    ) as roots:
        assert roots.head == head.resolve()
        assert roots.base is not None
        managed_base = roots.base
        assert managed_base.exists()
        assert (managed_base / ".codegraph" / "codegraph.db").is_file()

    assert not managed_base.exists()
    assert _command_names(runner).count(("fake-codegraph", "init")) == 2
    assert ("worktree", "remove") in tuple(
        command[3:5] for command in runner.commands if command[0] == "git"
    )


def test_existing_head_and_explicit_base_are_synced_and_never_deleted(
    tmp_path: Path,
) -> None:
    head = tmp_path / "head"
    base = tmp_path / "base"
    for root in (head, base):
        database = root / ".codegraph" / "codegraph.db"
        database.parent.mkdir(parents=True)
        database.touch()
    runner = FakeRunner({head: "head123", base: "base123"})

    with prepared_codegraph_roots(
        repo_root=head,
        head_revision="head123",
        base_revision="base123",
        base_repo_root=base,
        runner=runner,
        codegraph_command=("fake-codegraph",),
    ) as roots:
        assert roots.base == base.resolve()

    assert base.exists()
    assert _command_names(runner).count(("fake-codegraph", "sync")) == 2
    assert not any("remove" in command for command in runner.commands)


def test_managed_base_is_removed_when_indexing_fails(tmp_path: Path) -> None:
    head = tmp_path / "head"
    head.mkdir()
    runner = FakeRunner({head: "head123"}, fail_base_index=True)

    with pytest.raises(ValueError, match="base index failed"):
        with prepared_codegraph_roots(
            repo_root=head,
            head_revision="head123",
            base_revision="base123",
            runner=runner,
            codegraph_command=("fake-codegraph",),
        ):
            raise AssertionError("index failure must prevent review")

    assert runner.managed_base is not None
    assert not runner.managed_base.exists()


def test_managed_base_is_removed_when_review_body_fails(tmp_path: Path) -> None:
    head = tmp_path / "head"
    head.mkdir()
    runner = FakeRunner({head: "head123"})

    with pytest.raises(RuntimeError, match="render failed"):
        with prepared_codegraph_roots(
            repo_root=head,
            head_revision="head123",
            base_revision="base123",
            runner=runner,
            codegraph_command=("fake-codegraph",),
        ):
            raise RuntimeError("render failed")

    assert runner.managed_base is not None
    assert not runner.managed_base.exists()


def test_cleanup_failure_still_removes_private_directory(
    tmp_path: Path,
) -> None:
    head = tmp_path / "head"
    head.mkdir()
    runner = FakeRunner({head: "head123"}, fail_cleanup=True)

    with pytest.raises(ValueError, match="cleanup failed"):
        with prepared_codegraph_roots(
            repo_root=head,
            head_revision="head123",
            base_revision="base123",
            runner=runner,
            codegraph_command=("fake-codegraph",),
        ):
            pass

    assert runner.managed_base is not None
    assert not runner.managed_base.exists()


def test_checkout_revision_mismatch_prevents_preparation(tmp_path: Path) -> None:
    head = tmp_path / "head"
    head.mkdir()
    runner = FakeRunner({head: "wrong"})

    with pytest.raises(ValueError, match="expected head123"):
        with prepared_codegraph_roots(
            repo_root=head,
            head_revision="head123",
            base_revision="base123",
            runner=runner,
            codegraph_command=("fake-codegraph",),
        ):
            raise AssertionError("revision mismatch must prevent review")

    assert not any(command[0] == "fake-codegraph" for command in runner.commands)
