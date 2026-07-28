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
class ReviewRevisionRoots:
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
        "structure-aware review requires `codegraph` or `npx` on PATH; "
        "use --no-structural-graph to disable structural mapping"
    )


def _initialize_index(
    root: Path,
    *,
    runner: CommandRunner,
    codegraph_command: Command,
) -> None:
    _checked(
        runner,
        (*codegraph_command, "init", str(root)),
        timeout=300,
        action=f"Codegraph init for {root}",
    )


@contextmanager
def isolated_review_roots(
    *,
    repo_root: str | Path,
    head_revision: str,
    base_revision: str,
    structural_graph_enabled: bool,
    runner: CommandRunner = _run,
    codegraph_command: Command | None = None,
) -> Iterator[ReviewRevisionRoots]:
    """Create exact private revision roots and remove every artifact we own."""

    source = Path(repo_root).resolve()
    if not head_revision:
        raise ValueError("live review requires the pull request head SHA")
    if structural_graph_enabled and not base_revision:
        raise ValueError(
            "structure-aware review requires the pull request base SHA"
        )
    temporary_parent = Path(
        tempfile.mkdtemp(prefix="prismcode-review-")
    ).resolve()
    head = temporary_parent / "head"
    base = temporary_parent / "base"
    managed_roots: list[Path] = []
    command = (
        codegraph_command or _codegraph_command()
        if structural_graph_enabled
        else None
    )
    try:
        revision_roots = [(head, head_revision)]
        if structural_graph_enabled:
            revision_roots.append((base, base_revision))
        for root, revision in revision_roots:
            _checked(
                runner,
                (
                    "git",
                    "-C",
                    str(source),
                    "worktree",
                    "add",
                    "--detach",
                    str(root),
                    revision,
                ),
                timeout=60,
                action=f"Creating temporary worktree at {revision}",
            )
            managed_roots.append(root)
            if command is not None:
                _initialize_index(
                    root,
                    runner=runner,
                    codegraph_command=command,
                )
        yield ReviewRevisionRoots(
            head=head,
            base=base if structural_graph_enabled else None,
        )
    finally:
        active_error = sys.exc_info()[0] is not None
        cleanup_errors = []
        try:
            for root in reversed(managed_roots):
                try:
                    cleanup = runner(
                        (
                            "git",
                            "-C",
                            str(source),
                            "worktree",
                            "remove",
                            "--force",
                            str(root),
                        ),
                        60,
                    )
                    if cleanup.returncode:
                        cleanup_errors.append(
                            cleanup.stderr or cleanup.stdout
                        )
                except ValueError as exc:
                    cleanup_errors.append(str(exc))
            if cleanup_errors:
                try:
                    runner(
                        ("git", "-C", str(source), "worktree", "prune"),
                        30,
                    )
                except ValueError:
                    pass
        finally:
            shutil.rmtree(temporary_parent, ignore_errors=True)
        if cleanup_errors and not active_error:
            detail = " ".join(
                item.strip()
                for item in cleanup_errors
                if item.strip()
            )
            raise ValueError(
                "Temporary review worktree cleanup failed after its private "
                f"directory was removed: {detail or 'git worktree remove failed'}"
            )
