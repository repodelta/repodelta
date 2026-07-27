from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

Command = tuple[str, ...]
CommandRunner = Callable[[Command, int], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class PreparedCodegraphRoots:
    """Exact revision roots prepared for one review invocation."""

    head: Path
    base: Path | None = None


def _run(command: Command, timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(
            f"Could not run {' '.join(command[:2])}: {exc}"
        ) from exc


def _checked(
    runner: CommandRunner,
    command: Command,
    *,
    timeout: int,
    action: str,
) -> str:
    result = runner(command, timeout)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise ValueError(f"{action} failed: {detail or 'command returned non-zero'}")
    return result.stdout.strip()


def _codegraph_command() -> Command:
    executable = shutil.which("codegraph")
    if executable:
        return (executable,)
    npx = shutil.which("npx")
    if npx:
        return (npx, "--yes", "@colbymchenry/codegraph")
    raise ValueError(
        "--prepare-codegraph requires `codegraph` or `npx` on PATH"
    )


def _validate_checkout(
    root: Path,
    expected_revision: str,
    *,
    runner: CommandRunner,
) -> None:
    actual = _checked(
        runner,
        ("git", "-C", str(root), "rev-parse", "HEAD"),
        timeout=10,
        action=f"Reading checkout revision for {root}",
    )
    if not expected_revision or actual != expected_revision:
        raise ValueError(
            f"{root} is at {actual or 'an unknown revision'}, expected "
            f"{expected_revision or 'a GitHub revision'}"
        )
    tracked_changes = _checked(
        runner,
        (
            "git",
            "-C",
            str(root),
            "status",
            "--porcelain",
            "--untracked-files=no",
        ),
        timeout=10,
        action=f"Checking tracked changes for {root}",
    )
    if tracked_changes:
        raise ValueError(
            f"{root} has tracked working-tree changes; Codegraph preparation "
            "requires a clean exact revision"
        )


def _prepare_index(
    root: Path,
    *,
    runner: CommandRunner,
    codegraph_command: Command,
) -> None:
    action = "sync" if (root / ".codegraph" / "codegraph.db").is_file() else "init"
    _checked(
        runner,
        (*codegraph_command, action, str(root)),
        timeout=300,
        action=f"Codegraph {action} for {root}",
    )


@contextmanager
def prepared_codegraph_roots(
    *,
    repo_root: str | Path,
    head_revision: str,
    base_revision: str,
    base_repo_root: str | Path | None = None,
    runner: CommandRunner = _run,
    codegraph_command: Command | None = None,
) -> Iterator[PreparedCodegraphRoots]:
    """Prepare exact head/base indexes and clean only the base worktree we own."""

    head = Path(repo_root).resolve()
    command = codegraph_command or _codegraph_command()
    _validate_checkout(head, head_revision, runner=runner)
    _prepare_index(head, runner=runner, codegraph_command=command)

    if base_repo_root is not None:
        base = Path(base_repo_root).resolve()
        _validate_checkout(base, base_revision, runner=runner)
        _prepare_index(base, runner=runner, codegraph_command=command)
        yield PreparedCodegraphRoots(head=head, base=base)
        return

    if not base_revision:
        raise ValueError(
            "--prepare-codegraph requires the pull request base SHA"
        )

    temporary_parent = Path(
        tempfile.mkdtemp(prefix="prismcode-review-base-")
    ).resolve()
    base = temporary_parent / "checkout"
    worktree_added = False
    try:
        _checked(
            runner,
            (
                "git",
                "-C",
                str(head),
                "worktree",
                "add",
                "--detach",
                str(base),
                base_revision,
            ),
            timeout=60,
            action=f"Creating temporary base worktree at {base_revision}",
        )
        worktree_added = True
        _prepare_index(base, runner=runner, codegraph_command=command)
        yield PreparedCodegraphRoots(head=head, base=base)
    finally:
        active_error = sys.exc_info()[0] is not None
        cleanup_error = ""
        try:
            if worktree_added:
                try:
                    cleanup = runner(
                        (
                            "git",
                            "-C",
                            str(head),
                            "worktree",
                            "remove",
                            "--force",
                            str(base),
                        ),
                        60,
                    )
                    if cleanup.returncode:
                        cleanup_error = (
                            cleanup.stderr or cleanup.stdout
                        ).strip() or "git worktree remove returned non-zero"
                except ValueError as exc:
                    cleanup_error = str(exc)
                if cleanup_error:
                    try:
                        runner(
                            ("git", "-C", str(head), "worktree", "prune"),
                            30,
                        )
                    except ValueError:
                        pass
        finally:
            shutil.rmtree(temporary_parent, ignore_errors=True)
        if cleanup_error and not active_error:
            raise ValueError(
                "Temporary base worktree cleanup failed after its directory "
                f"was removed: {cleanup_error}"
            )
