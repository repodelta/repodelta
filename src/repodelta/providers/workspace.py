from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Mapping
from urllib.parse import quote, urlparse, urlunparse

Command = tuple[str, ...]
CommandRunner = Callable[[Command, int], subprocess.CompletedProcess[str]]
EnvironmentCommandRunner = Callable[
    [Command, int, Mapping[str, str]], subprocess.CompletedProcess[str]
]

_CODEGRAPH_NPM_PACKAGE = "@colbymchenry/codegraph"
_CODEGRAPH_NPX_SPEC = f"{_CODEGRAPH_NPM_PACKAGE}@1.2.0"
_CODEGRAPH_INSTALL_GUIDANCE = (
    "RepoDelta structural mapping requires the CodeGraph CLI from "
    "`@colbymchenry/codegraph` (not the unrelated PyPI `codegraph` package); "
    "install it with `npm install -g @colbymchenry/codegraph`, provide Node.js "
    "with `npx`, or use --no-structural-graph"
)


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


def _run_with_environment(
    command: Command,
    timeout: int,
    environment: Mapping[str, str],
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env={**os.environ, **environment},
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


def _checked_with_environment(
    runner: EnvironmentCommandRunner,
    command: Command,
    *,
    timeout: int,
    action: str,
    environment: Mapping[str, str],
    secret: str | None = None,
) -> str:
    result = runner(command, timeout, environment)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        if secret:
            encoded = base64.b64encode(
                f"x-access-token:{secret}".encode("utf-8")
            ).decode("ascii")
            detail = detail.replace(secret, "[redacted]")
            detail = detail.replace(encoded, "[redacted]")
        raise ValueError(f"{action} failed: {detail or 'command returned non-zero'}")
    return result.stdout.strip()


def _repository_git_url(repository: str, api_url: str) -> str:
    parts = repository.strip().split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError("repository must use owner/name form")
    parsed = urlparse(api_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("GitHub API URL must be an absolute HTTPS URL")
    if parsed.hostname.casefold() == "api.github.com":
        netloc = "github.com"
        prefix = ""
    else:
        netloc = parsed.netloc
        api_path = parsed.path.rstrip("/")
        if not api_path.endswith("/api/v3"):
            raise ValueError(
                "GitHub Enterprise API URL must end with /api/v3"
            )
        prefix = api_path.removesuffix("/api/v3")
    owner, name = (quote(item, safe="") for item in parts)
    path = f"{prefix}/{owner}/{name}.git"
    return urlunparse(("https", netloc, path, "", "", ""))


def _git_auth_environment(token: str | None) -> dict[str, str]:
    environment = {
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    if token:
        encoded = base64.b64encode(
            f"x-access-token:{token}".encode("utf-8")
        ).decode("ascii")
        environment.update(
            {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "http.extraHeader",
                "GIT_CONFIG_VALUE_0": f"Authorization: Basic {encoded}",
            }
        )
    return environment


def _installed_codegraph_is_supported(
    executable: str,
    *,
    runner: CommandRunner,
) -> bool:
    """Identify the external CLI by the smallest capability RepoDelta consumes."""

    try:
        result = runner((executable, "init", "--help"), 15)
    except ValueError:
        return False
    description = f"{result.stdout}\n{result.stderr}".casefold()
    return (
        result.returncode == 0
        and "codegraph" in description
        and "index" in description
    )


def _codegraph_command(*, runner: CommandRunner = _run) -> Command:
    executable = shutil.which("codegraph")
    if executable and _installed_codegraph_is_supported(
        executable,
        runner=runner,
    ):
        return (executable,)
    npx = shutil.which("npx")
    if npx:
        return (npx, "--yes", _CODEGRAPH_NPX_SPEC)
    raise ValueError(_CODEGRAPH_INSTALL_GUIDANCE)


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
    database = root / ".codegraph" / "codegraph.db"
    if not database.is_file():
        raise ValueError(
            f"CodeGraph init for {root} did not create "
            f"{database.relative_to(root)}. {_CODEGRAPH_INSTALL_GUIDANCE}"
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
        tempfile.mkdtemp(prefix="repodelta-review-")
    ).resolve()
    head = temporary_parent / "head"
    base = temporary_parent / "base"
    managed_roots: list[Path] = []
    command = (
        codegraph_command or _codegraph_command(runner=runner)
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


@contextmanager
def remote_review_roots(
    *,
    repository: str,
    pull_request: int,
    api_url: str,
    token: str | None,
    head_revision: str,
    base_revision: str,
    structural_graph_enabled: bool,
    fetch_runner: EnvironmentCommandRunner = _run_with_environment,
    workspace_runner: CommandRunner = _run,
    codegraph_command: Command | None = None,
) -> Iterator[ReviewRevisionRoots]:
    """Fetch exact PR revisions into a private Git source and remove it."""

    if pull_request <= 0:
        raise ValueError("pull request number must be positive")
    if not head_revision:
        raise ValueError("live review requires the pull request head SHA")
    if structural_graph_enabled and not base_revision:
        raise ValueError(
            "structure-aware review requires the pull request base SHA"
        )
    git_url = _repository_git_url(repository, api_url)
    environment = _git_auth_environment(token)
    non_secret_environment = _git_auth_environment(None)
    temporary_parent = Path(
        tempfile.mkdtemp(prefix="repodelta-remote-")
    ).resolve()
    source = temporary_parent / "source.git"
    base_ref = "refs/repodelta/base"
    head_ref = "refs/repodelta/head"
    try:
        _checked_with_environment(
            fetch_runner,
            ("git", "init", "--bare", str(source)),
            timeout=30,
            action="Creating temporary Git source",
            environment=non_secret_environment,
            secret=token,
        )
        _checked_with_environment(
            fetch_runner,
            ("git", "-C", str(source), "remote", "add", "origin", git_url),
            timeout=30,
            action="Configuring temporary Git source",
            environment=non_secret_environment,
            secret=token,
        )
        refspecs = [
            f"+refs/pull/{pull_request}/head:{head_ref}",
        ]
        if structural_graph_enabled:
            refspecs.append(f"+{base_revision}:{base_ref}")
        _checked_with_environment(
            fetch_runner,
            (
                "git",
                "-C",
                str(source),
                "fetch",
                "--no-tags",
                "--depth=1",
                "origin",
                *refspecs,
            ),
            timeout=300,
            action="Fetching pull request revisions",
            environment=environment,
            secret=token,
        )
        observed_head = _checked(
            workspace_runner,
            ("git", "-C", str(source), "rev-parse", head_ref),
            timeout=30,
            action="Validating fetched head revision",
        )
        if observed_head != head_revision:
            raise ValueError(
                "Fetched pull request head does not match GitHub metadata"
            )
        if structural_graph_enabled:
            observed_base = _checked(
                workspace_runner,
                ("git", "-C", str(source), "rev-parse", base_ref),
                timeout=30,
                action="Validating fetched base revision",
            )
            if observed_base != base_revision:
                raise ValueError(
                    "Fetched pull request base does not match GitHub metadata"
                )
        with isolated_review_roots(
            repo_root=source,
            head_revision=head_revision,
            base_revision=base_revision,
            structural_graph_enabled=structural_graph_enabled,
            runner=workspace_runner,
            codegraph_command=codegraph_command,
        ) as roots:
            yield roots
    finally:
        shutil.rmtree(temporary_parent, ignore_errors=True)
