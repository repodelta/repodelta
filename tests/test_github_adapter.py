from __future__ import annotations

from typing import Any

import pytest

from prismcode.analysis import DeterministicAnalyzer
from prismcode.contracts import AnalysisInput
from prismcode.github import GitHubClient, GitHubPullRequestAdapter, extract_intent, extract_requirement_texts
from prismcode.rendering import render_html


class FakeClient:
    def __init__(self, responses: dict[tuple[str, tuple[tuple[str, str | int], ...]], Any]) -> None:
        self.responses = responses

    def get_json(self, path: str, query: dict[str, str | int] | None = None) -> Any:
        return self.responses[(path, tuple(sorted((query or {}).items())))]


def test_extract_requirements_is_conservative_and_deduplicated() -> None:
    body = """
This change exposes an inspect-only trace.

## Acceptance criteria
- Produce the trace.
- Do not change normal review behavior.

## Notes
- This note is not a requirement.

- [x] Produce the trace.
"""
    assert extract_requirement_texts(body) == (
        "Produce the trace.",
        "Do not change normal review behavior.",
    )
    assert extract_intent(body, "Fallback") == "This change exposes an inspect-only trace."


def test_github_adapter_collects_only_source_facts() -> None:
    pr_path = "/repos/acme/widget/pulls/42"
    files_path = "/repos/acme/widget/pulls/42/files"
    client = FakeClient(
        {
            (pr_path, ()): {
                "html_url": "https://github.com/acme/widget/pull/42",
                "title": "Add audit trace",
                "body": "Explain the result.\n\n## Requirements\n- Emit a trace.\n- Preserve behavior.",
                "state": "open",
                "draft": False,
                "changed_files": 2,
                "head": {"sha": "head123"},
                "base": {"sha": "base123"},
                "user": {"login": "octocat"},
            },
            (files_path, (("page", 1), ("per_page", 100))): [
                {
                    "filename": "src/a.py",
                    "status": "modified",
                    "blob_url": "https://github.com/acme/widget/blob/head123/src/a.py",
                    "patch": "@@ -1 +1 @@",
                },
                {
                    "filename": "tests/test_a.py",
                    "status": "added",
                    "blob_url": "https://github.com/acme/widget/blob/head123/tests/test_a.py",
                },
            ],
        }
    )

    packet = GitHubPullRequestAdapter(client=client).load("acme/widget", 42)
    packet.validate_consistency()
    assert packet.head_sha == "head123"
    assert [item.path for item in packet.changed_files] == ["src/a.py", "tests/test_a.py"]
    assert [item.code for item in packet.diagnostics] == ["github_patch_unavailable"]
    assert not hasattr(packet, "requirements")

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    assert [item.requirement.text for item in brief.assessments] == ["Emit a trace.", "Preserve behavior."]
    assert all(item.implementation.status == "not_observed" for item in brief.assessments)
    assert "Collection notes" in render_html(brief)


def test_github_adapter_reports_file_cap_without_inferring_requirements() -> None:
    pr_path = "/repos/acme/widget/pulls/7"
    files_path = "/repos/acme/widget/pulls/7/files"
    client = FakeClient(
        {
            (pr_path, ()): {
                "title": "Fallback requirement",
                "body": "No structured requirements here.",
                "changed_files": 2,
                "head": {},
                "base": {},
                "user": {},
            },
            (files_path, (("page", 1), ("per_page", 1))): [
                {"filename": "src/a.py", "status": "modified", "patch": "@@"}
            ],
        }
    )
    packet = GitHubPullRequestAdapter(client=client, max_files=1).load("acme/widget", 7)
    assert [item.code for item in packet.diagnostics] == ["github_file_limit_reached"]
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    assert brief.assessments[0].requirement.text == "Fallback requirement"


def test_token_is_not_sent_to_untrusted_or_unsafe_api_url() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        GitHubClient(token="secret", api_url="http://github.example/api/v3")
    with pytest.raises(ValueError, match="untrusted"):
        GitHubClient(token="secret", api_url="https://github.example/api/v3")

    client = GitHubClient(
        token="secret",
        api_url="https://github.example/api/v3",
        trusted_api_hosts=("github.example",),
    )
    assert client.api_url == "https://github.example/api/v3"
