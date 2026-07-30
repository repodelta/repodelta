from __future__ import annotations

from types import SimpleNamespace

import pytest

import prismcode.cli as cli
from prismcode.intake.github import GitHubApiError


def test_resolve_github_token_prefers_configured_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "  env-token  ")

    def unexpected_run(*args: object, **kwargs: object) -> object:
        pytest.fail("gh should not run when the configured environment token exists")

    monkeypatch.setattr(cli.subprocess, "run", unexpected_run)

    assert (
        cli._resolve_github_token("GITHUB_TOKEN", "https://api.github.com")
        == "env-token"
    )


def test_resolve_github_token_falls_back_to_authenticated_gh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    observed: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        observed["command"] = command
        observed["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="gh-token\n")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    assert (
        cli._resolve_github_token("GITHUB_TOKEN", "https://api.github.com")
        == "gh-token"
    )
    assert observed["command"] == [
        "gh",
        "auth",
        "token",
        "--hostname",
        "github.com",
    ]
    assert observed["kwargs"] == {
        "check": False,
        "capture_output": True,
        "text": True,
        "timeout": 5,
    }


def test_resolve_github_token_uses_enterprise_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PRIVATE_GITHUB_TOKEN", raising=False)
    observed: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        observed.append(command)
        return SimpleNamespace(returncode=0, stdout="enterprise-token")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    assert (
        cli._resolve_github_token(
            "PRIVATE_GITHUB_TOKEN",
            "https://github.example.com/api/v3",
        )
        == "enterprise-token"
    )
    assert observed == [
        [
            "gh",
            "auth",
            "token",
            "--hostname",
            "github.example.com",
        ]
    ]


def test_enrich_github_auth_error_explains_private_repo_404() -> None:
    enriched = cli._enrich_github_auth_error(
        GitHubApiError(
            "GitHub API returned HTTP 404: Not Found",
            status_code=404,
            url="https://api.github.com/repos/acme/private/pulls/1",
        ),
        token=None,
        token_env="GITHUB_TOKEN",
        api_url="https://api.github.com",
    )

    assert enriched.status_code == 404
    assert "No GitHub token was available from GITHUB_TOKEN" in str(enriched)
    assert "gh auth token --hostname github.com" in str(enriched)
