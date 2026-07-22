from __future__ import annotations

from typing import Any

from prismcode.analysis import DeterministicAnalyzer
from prismcode.github import GitHubPullRequestAdapter, extract_intent, extract_requirement_texts
from prismcode.rendering import render_html


class FakeClient:
    def __init__(self, responses: dict[tuple[str, tuple[tuple[str, str | int], ...]], Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, tuple[tuple[str, str | int], ...]]] = []

    def get_json(self, path: str, query: dict[str, str | int] | None = None) -> Any:
        key = (path, tuple(sorted((query or {}).items())))
        self.calls.append(key)
        return self.responses[key]


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


def test_github_adapter_collects_real_pr_facts_without_claiming_alignment() -> None:
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
                "additions": 20,
                "deletions": 3,
                "head": {"sha": "head123"},
                "base": {"sha": "base123"},
                "user": {"login": "octocat"},
            },
            (files_path, (("page", 1), ("per_page", 100))): [
                {
                    "filename": "src/a.py",
                    "status": "modified",
                    "additions": 18,
                    "deletions": 2,
                    "changes": 20,
                    "blob_url": "https://github.com/acme/widget/blob/head123/src/a.py",
                    "patch": "@@ -1 +1 @@",
                },
                {
                    "filename": "tests/test_a.py",
                    "status": "added",
                    "additions": 2,
                    "deletions": 1,
                    "changes": 3,
                    "blob_url": "https://github.com/acme/widget/blob/head123/tests/test_a.py",
                },
            ],
        }
    )

    review = GitHubPullRequestAdapter(client=client).load("acme/widget", 42)

    assert [item.text for item in review.requirements] == ["Emit a trace.", "Preserve behavior."]
    assert all(item.status == "unresolved" for item in review.requirements)
    assert all(not item.implemented for item in review.requirements)
    assert all(not item.verification for item in review.requirements)
    assert [item.path for item in review.changed_files] == ["src/a.py", "tests/test_a.py"]
    assert review.metadata["head_sha"] == "head123"
    assert review.metadata["changed_files_collected"] == 2
    assert [item.code for item in review.diagnostics] == ["github_patch_unavailable"]

    html = render_html(DeterministicAnalyzer().analyze(review))
    assert "Collection notes" in html
    assert "github_patch_unavailable" in html
    assert "https://github.com/acme/widget/blob/head123/src/a.py" in html


def test_github_adapter_reports_title_fallback_and_file_cap() -> None:
    pr_path = "/repos/acme/widget/pulls/7"
    files_path = "/repos/acme/widget/pulls/7/files"
    client = FakeClient(
        {
            (pr_path, ()): {
                "html_url": "https://github.com/acme/widget/pull/7",
                "title": "Fallback requirement",
                "body": "No structured requirements here.",
                "changed_files": 2,
                "head": {},
                "base": {},
                "user": {},
            },
            (files_path, (("page", 1), ("per_page", 1))): [
                {
                    "filename": "src/a.py",
                    "status": "modified",
                    "additions": 1,
                    "deletions": 0,
                    "changes": 1,
                    "blob_url": "https://github.com/acme/widget/blob/head/src/a.py",
                    "patch": "@@",
                }
            ],
        }
    )

    review = GitHubPullRequestAdapter(client=client, max_files=1).load("acme/widget", 7)

    assert [item.text for item in review.requirements] == ["Fallback requirement"]
    assert [item.code for item in review.diagnostics] == [
        "requirements_title_fallback",
        "github_file_limit_reached",
    ]
