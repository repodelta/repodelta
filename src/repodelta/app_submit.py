from __future__ import annotations

import base64
import json
import os
import re
import stat
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Sequence


GITHUB_API_URL = "https://api.github.com"
REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


class SubmissionError(RuntimeError):
    """A bounded submission failure that never includes credential material."""


@dataclass(frozen=True)
class SubmissionConfig:
    app_id: str
    installation_id: str
    private_key: Path
    repo: str
    head: str
    base: str
    title: str
    body: str
    reviewers: tuple[str, ...] = ()
    draft: bool = False
    repo_root: Path = Path(".")


@dataclass(frozen=True)
class SubmittedPullRequest:
    number: int
    url: str
    author: str


Run = Callable[..., subprocess.CompletedProcess[bytes]]
Open = Callable[..., object]


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _validate_numeric_id(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized.isdecimal():
        raise SubmissionError(f"{label} must be a numeric GitHub identifier")
    return normalized


def _validate_repo(value: str) -> str:
    if not REPOSITORY_PATTERN.fullmatch(value) or value.endswith(".git"):
        raise SubmissionError("repository must use GitHub owner/name form")
    return value


def validate_private_key(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        status = resolved.stat()
    except OSError as exc:
        raise SubmissionError("GitHub App private key is not readable") from exc
    if not stat.S_ISREG(status.st_mode):
        raise SubmissionError("GitHub App private key must be a regular file")
    if stat.S_IMODE(status.st_mode) & 0o077:
        raise SubmissionError(
            "GitHub App private key must not be readable or writable by group or others"
        )
    return resolved


def create_app_jwt(
    app_id: str,
    private_key: Path,
    *,
    now: int | None = None,
    run: Run = subprocess.run,
) -> str:
    app_id = _validate_numeric_id(app_id, "App ID")
    private_key = validate_private_key(private_key)
    issued_at = int(time.time()) if now is None else now
    header = _encode(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _encode(
        json.dumps(
            {"iat": issued_at - 60, "exp": issued_at + 540, "iss": app_id},
            separators=(",", ":"),
        ).encode()
    )
    unsigned = f"{header}.{payload}".encode("ascii")
    try:
        completed = run(
            ["openssl", "dgst", "-sha256", "-sign", str(private_key)],
            input=unsigned,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SubmissionError("Unable to sign the GitHub App request") from exc
    return f"{header}.{payload}.{_encode(completed.stdout)}"


def _request_json(
    url: str,
    *,
    method: str,
    authorization: str,
    payload: dict[str, object] | None = None,
    stage: str,
    open_url: Open = urllib.request.urlopen,
) -> dict[str, object]:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": authorization,
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "repodelta-bot",
        },
    )
    try:
        with open_url(request) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        raise SubmissionError(
            f"GitHub API returned HTTP {exc.code} while {stage}"
        ) from exc
    except (OSError, ValueError) as exc:
        raise SubmissionError(f"GitHub API failed while {stage}") from exc
    if not isinstance(result, dict):
        raise SubmissionError(f"GitHub API returned an invalid response while {stage}")
    return result


def request_installation_token(
    installation_id: str,
    app_jwt: str,
    *,
    open_url: Open = urllib.request.urlopen,
) -> str:
    installation_id = _validate_numeric_id(installation_id, "Installation ID")
    response = _request_json(
        f"{GITHUB_API_URL}/app/installations/{installation_id}/access_tokens",
        method="POST",
        authorization=f"Bearer {app_jwt}",
        stage="requesting an installation token",
        open_url=open_url,
    )
    token = response.get("token")
    if not isinstance(token, str) or not token:
        raise SubmissionError("GitHub did not return an installation token")
    return token


@contextmanager
def temporary_git_credentials(token: str) -> Iterator[dict[str, str]]:
    with tempfile.TemporaryDirectory(prefix="repodelta-bot-") as directory:
        root = Path(directory)
        token_path = root / "token"
        askpass_path = root / "askpass.sh"
        token_path.write_text(token)
        token_path.chmod(0o600)
        askpass_path.write_text(
            "#!/bin/sh\n"
            "case \"$1\" in\n"
            "  *Username*) printf '%s\\n' 'x-access-token' ;;\n"
            f"  *Password*) exec /bin/cat '{token_path}' ;;\n"
            "  *) exit 1 ;;\n"
            "esac\n"
        )
        askpass_path.chmod(0o700)
        yield {
            "GIT_ASKPASS": str(askpass_path),
            "GIT_TERMINAL_PROMPT": "0",
        }


def push_head(
    config: SubmissionConfig,
    token: str,
    *,
    run: Run = subprocess.run,
) -> None:
    repo = _validate_repo(config.repo)
    remote = f"https://x-access-token@github.com/{repo}.git"
    with temporary_git_credentials(token) as credential_env:
        environment = os.environ.copy()
        environment.update(credential_env)
        try:
            run(
                [
                    "git",
                    "-c",
                    "credential.helper=",
                    "push",
                    "--",
                    remote,
                    f"HEAD:refs/heads/{config.head}",
                ],
                cwd=config.repo_root,
                env=environment,
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise SubmissionError("Git push through the GitHub App failed") from exc


def create_pull_request(
    config: SubmissionConfig,
    token: str,
    *,
    open_url: Open = urllib.request.urlopen,
) -> SubmittedPullRequest:
    repo = _validate_repo(config.repo)
    api_root = f"{GITHUB_API_URL}/repos/{repo}"
    pull = _request_json(
        f"{api_root}/pulls",
        method="POST",
        authorization=f"Bearer {token}",
        payload={
            "title": config.title,
            "head": config.head,
            "base": config.base,
            "body": config.body,
            "draft": config.draft,
        },
        stage="creating the pull request",
        open_url=open_url,
    )
    number = pull.get("number")
    url = pull.get("html_url")
    user = pull.get("user")
    author = user.get("login") if isinstance(user, dict) else None
    if not isinstance(number, int) or not isinstance(url, str) or not isinstance(author, str):
        raise SubmissionError("GitHub returned an incomplete pull request response")
    if config.reviewers:
        try:
            _request_json(
                f"{api_root}/pulls/{number}/requested_reviewers",
                method="POST",
                authorization=f"Bearer {token}",
                payload={"reviewers": list(config.reviewers)},
                stage="requesting human reviewers",
                open_url=open_url,
            )
        except SubmissionError as exc:
            raise SubmissionError(
                f"Pull request {url} was created, but requesting human reviewers failed"
            ) from exc
    return SubmittedPullRequest(number=number, url=url, author=author)


def submit_change(
    config: SubmissionConfig,
    *,
    run: Run = subprocess.run,
    open_url: Open = urllib.request.urlopen,
    now: int | None = None,
) -> SubmittedPullRequest:
    app_jwt = create_app_jwt(
        config.app_id,
        config.private_key,
        now=now,
        run=run,
    )
    token = request_installation_token(
        config.installation_id,
        app_jwt,
        open_url=open_url,
    )
    push_head(config, token, run=run)
    return create_pull_request(config, token, open_url=open_url)
