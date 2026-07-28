from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from prismcode.providers.workspace import isolated_review_roots


class FakeRunner:
    def __init__(
        self,
        *,
        fail_index_side: str = "",
        fail_cleanup: bool = False,
    ) -> None:
        self.fail_index_side = fail_index_side
        self.fail_cleanup = fail_cleanup
        self.commands: list[tuple[str, ...]] = []
        self.managed_roots: dict[str, Path] = {}

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


def _commands(
    runner: FakeRunner,
    prefix: tuple[str, ...],
) -> tuple[tuple[str, ...], ...]:
    return tuple(
        command for command in runner.commands if command[: len(prefix)] == prefix
    )


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
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    runner = FakeRunner()

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


def test_live_review_workflow_provisions_pr_revision_objects() -> None:
    workflow = Path(".github/workflows/review.yml").read_text(encoding="utf-8")

    assert "uses: actions/checkout@v4\n        with:\n          fetch-depth: 0" in workflow
