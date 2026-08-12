from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from repodelta_bot.submit import (  # noqa: E402
    SubmissionConfig,
    SubmissionError,
    create_app_jwt,
    create_pull_request,
    push_head,
    request_installation_token,
    temporary_git_credentials,
    validate_private_key,
)


LOCAL_HEAD = "a" * 40
REMOTE_HEAD = "b" * 40


class JsonResponse:
    def __init__(self, value: dict[str, object]) -> None:
        self.value = value

    def __enter__(self) -> JsonResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, *args: object) -> bytes:
        return json.dumps(self.value).encode()


def _key(tmp_path: Path, mode: int = 0o600) -> Path:
    path = tmp_path / "app.pem"
    path.write_text("private")
    path.chmod(mode)
    return path


def _config(tmp_path: Path, **overrides: object) -> SubmissionConfig:
    values: dict[str, object] = {
        "app_id": "4557115",
        "installation_id": "152885056",
        "private_key": _key(tmp_path),
        "repo": "repodelta/repodelta",
        "head": "codex/example",
        "base": "main",
        "title": "Example",
        "body": "Body",
        "reviewers": ("maintainer",),
        "repo_root": tmp_path,
    }
    values.update(overrides)
    return SubmissionConfig(**values)  # type: ignore[arg-type]


def test_private_key_requires_owner_only_permissions(tmp_path: Path) -> None:
    with pytest.raises(SubmissionError, match="group or others"):
        validate_private_key(_key(tmp_path, 0o640))


def test_app_jwt_is_short_lived_and_signed_without_shell(tmp_path: Path) -> None:
    observed: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        observed["command"] = command
        observed["kwargs"] = kwargs
        return SimpleNamespace(stdout=b"signature")

    token = create_app_jwt("4557115", _key(tmp_path), now=1_000, run=fake_run)
    header, payload, signature = token.split(".")
    decoded = json.loads(base64.urlsafe_b64decode(payload + "=="))

    assert json.loads(base64.urlsafe_b64decode(header + "==")) == {
        "alg": "RS256",
        "typ": "JWT",
    }
    assert decoded == {"iat": 940, "exp": 1540, "iss": "4557115"}
    assert base64.urlsafe_b64decode(signature + "==") == b"signature"
    assert observed["command"] == [
        "openssl",
        "dgst",
        "-sha256",
        "-sign",
        str((tmp_path / "app.pem").resolve()),
    ]
    assert observed["kwargs"] == {
        "input": f"{header}.{payload}".encode(),
        "check": True,
        "capture_output": True,
    }


def test_installation_token_is_not_accepted_when_missing() -> None:
    def fake_open(request: object) -> JsonResponse:
        return JsonResponse({})

    with pytest.raises(SubmissionError, match="did not return"):
        request_installation_token("152885056", "jwt", open_url=fake_open)


def test_temporary_git_credentials_are_removed_after_use() -> None:
    observed: dict[str, Path] = {}
    with temporary_git_credentials("short-token") as environment:
        askpass = Path(environment["GIT_ASKPASS"])
        token_match = re.search(r"/bin/cat '([^']+)'", askpass.read_text())
        assert token_match is not None
        token_path = Path(token_match.group(1))
        observed = {"askpass": askpass, "token": token_path}
        assert token_path.read_text() == "short-token"
        assert token_path.stat().st_mode & 0o077 == 0
        assert "short-token" not in askpass.read_text()

    assert not observed["askpass"].exists()
    assert not observed["token"].exists()


def test_temporary_git_credentials_are_removed_after_failure() -> None:
    observed: dict[str, Path] = {}
    with pytest.raises(RuntimeError, match="stop"):
        with temporary_git_credentials("short-token") as environment:
            askpass = Path(environment["GIT_ASKPASS"])
            token_match = re.search(r"/bin/cat '([^']+)'", askpass.read_text())
            assert token_match is not None
            observed = {
                "askpass": askpass,
                "token": Path(token_match.group(1)),
            }
            raise RuntimeError("stop")

    assert not observed["askpass"].exists()
    assert not observed["token"].exists()


def test_git_push_keeps_token_out_of_arguments_and_environment(
    tmp_path: Path,
) -> None:
    observed: dict[str, object] = {"remote_reads": 0}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if command == ["git", "rev-parse", "--verify", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, f"{LOCAL_HEAD}\n".encode(), b"")
        if "ls-remote" in command:
            observed["remote_reads"] = int(observed["remote_reads"]) + 1
            head = REMOTE_HEAD if observed["remote_reads"] == 1 else LOCAL_HEAD
            return subprocess.CompletedProcess(
                command,
                0,
                f"{head}\trefs/heads/codex/example\n".encode(),
                b"",
            )
        observed["command"] = command
        observed["environment"] = kwargs["env"]
        askpass = Path(kwargs["env"]["GIT_ASKPASS"])
        assert askpass.exists()
        return subprocess.CompletedProcess(command, 0, b"", b"")

    push_head(_config(tmp_path), "short-token", run=fake_run)

    assert "short-token" not in repr(observed)
    assert observed["command"] == [
        "git",
        "-c",
        "credential.helper=",
        "push",
        "--",
        "https://x-access-token@github.com/repodelta/repodelta.git",
        "HEAD:refs/heads/codex/example",
    ]
    assert observed["remote_reads"] == 2


def test_same_remote_head_fails_before_claiming_an_app_push(
    tmp_path: Path,
) -> None:
    observed_commands: list[list[str]] = []

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        observed_commands.append(command)
        if command == ["git", "rev-parse", "--verify", "HEAD"]:
            output = f"{LOCAL_HEAD}\n".encode()
        else:
            output = f"{LOCAL_HEAD}\trefs/heads/codex/example\n".encode()
        return subprocess.CompletedProcess(command, 0, output, b"")

    with pytest.raises(SubmissionError, match="no GitHub App push"):
        push_head(_config(tmp_path), "short-token", run=fake_run)

    assert not any(command[3:4] == ["push"] for command in observed_commands)


def test_leased_handoff_requires_and_pushes_from_the_observed_remote_head(
    tmp_path: Path,
) -> None:
    observed: dict[str, object] = {"remote_reads": 0}

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        if command == ["git", "rev-parse", "--verify", "HEAD"]:
            return subprocess.CompletedProcess(
                command, 0, f"{LOCAL_HEAD}\n".encode(), b""
            )
        if "ls-remote" in command:
            observed["remote_reads"] = int(observed["remote_reads"]) + 1
            head = REMOTE_HEAD if observed["remote_reads"] == 1 else LOCAL_HEAD
            return subprocess.CompletedProcess(
                command,
                0,
                f"{head}\trefs/heads/codex/example\n".encode(),
                b"",
            )
        observed["push"] = command
        return subprocess.CompletedProcess(command, 0, b"", b"")

    receipt = push_head(
        _config(tmp_path, expected_remote_head=REMOTE_HEAD),
        "short-token",
        run=fake_run,
    )

    assert receipt.previous_remote_head == REMOTE_HEAD
    assert receipt.remote_head == LOCAL_HEAD
    assert observed["push"] == [
        "git",
        "-c",
        "credential.helper=",
        "push",
        f"--force-with-lease=refs/heads/codex/example:{REMOTE_HEAD}",
        "--",
        "https://x-access-token@github.com/repodelta/repodelta.git",
        "HEAD:refs/heads/codex/example",
    ]


def test_leased_handoff_rejects_a_remote_head_change(tmp_path: Path) -> None:
    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        if command == ["git", "rev-parse", "--verify", "HEAD"]:
            output = f"{LOCAL_HEAD}\n".encode()
        else:
            output = f"{'c' * 40}\trefs/heads/codex/example\n".encode()
        return subprocess.CompletedProcess(command, 0, output, b"")

    with pytest.raises(SubmissionError, match="changed after it was selected"):
        push_head(
            _config(tmp_path, expected_remote_head=REMOTE_HEAD),
            "short-token",
            run=fake_run,
        )


def test_post_push_remote_head_must_match_local_head(tmp_path: Path) -> None:
    remote_reads = 0

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        nonlocal remote_reads
        if command == ["git", "rev-parse", "--verify", "HEAD"]:
            return subprocess.CompletedProcess(
                command, 0, f"{LOCAL_HEAD}\n".encode(), b""
            )
        if "ls-remote" in command:
            remote_reads += 1
            return subprocess.CompletedProcess(
                command,
                0,
                f"{REMOTE_HEAD}\trefs/heads/codex/example\n".encode(),
                b"",
            )
        return subprocess.CompletedProcess(command, 0, b"", b"")

    with pytest.raises(SubmissionError, match="did not establish"):
        push_head(_config(tmp_path), "short-token", run=fake_run)


def test_pull_request_creation_requests_human_reviewers(tmp_path: Path) -> None:
    requests: list[tuple[str, dict[str, object]]] = []
    responses = iter(
        [
            JsonResponse(
                {
                    "number": 250,
                    "html_url": "https://github.com/repodelta/repodelta/pull/250",
                    "user": {"login": "repodelta-change-submitter[bot]"},
                }
            ),
            JsonResponse({}),
        ]
    )

    def fake_open(request: object) -> JsonResponse:
        requests.append((request.full_url, json.loads(request.data)))
        return next(responses)

    result = create_pull_request(_config(tmp_path), "short-token", open_url=fake_open)

    assert result.number == 250
    assert result.author == "repodelta-change-submitter[bot]"
    assert requests[0][1]["head"] == "codex/example"
    assert requests[1] == (
        "https://api.github.com/repos/repodelta/repodelta/pulls/250/requested_reviewers",
        {"reviewers": ["maintainer"]},
    )
    assert "short-token" not in repr(requests)


def test_api_failure_is_bounded_without_credential_text() -> None:
    def fake_open(request: object) -> object:
        raise HTTPError(request.full_url, 403, "token=secret", {}, None)

    with pytest.raises(SubmissionError) as captured:
        request_installation_token("152885056", "sensitive-jwt", open_url=fake_open)

    message = str(captured.value)
    assert message == "GitHub API returned HTTP 403 while requesting an installation token"
    assert "sensitive-jwt" not in message
    assert "secret" not in message


def test_repository_must_use_owner_name_form(tmp_path: Path) -> None:
    with pytest.raises(SubmissionError, match="owner/name"):
        push_head(_config(tmp_path, repo="https://example.com/repo"), "token")
