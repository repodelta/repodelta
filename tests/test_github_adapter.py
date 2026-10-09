from __future__ import annotations

from typing import Any

import pytest

from repodelta.pipeline import DeterministicAnalyzer
from repodelta.model.contracts import AnalysisInput
from repodelta.intake.github import (
    GitHubApiError,
    GitHubClient,
    GitHubPullRequestAdapter,
)
from repodelta.semantics.criteria import extract_intent, extract_requirement_texts
from repodelta.presentation.html import render_html


_DEFAULT_GRAPHQL = object()


class FakeClient:
    def __init__(
        self,
        responses: dict[tuple[str, tuple[tuple[str, str | int], ...]], Any],
        *,
        linked_issues: list[dict[str, Any]] | None = None,
        graphql_payload: Any = _DEFAULT_GRAPHQL,
        graphql_error: GitHubApiError | None = None,
    ) -> None:
        self.responses = responses
        self.linked_issues = linked_issues or []
        self.graphql_payload = graphql_payload
        self.graphql_error = graphql_error

    def get_json(self, path: str, query: dict[str, str | int] | None = None) -> Any:
        return self.responses[(path, tuple(sorted((query or {}).items())))]

    def post_graphql(self, query: str, variables: dict[str, object]) -> Any:
        assert "closingIssuesReferences" in query
        if self.graphql_error is not None:
            raise self.graphql_error
        if self.graphql_payload is not _DEFAULT_GRAPHQL:
            return self.graphql_payload
        return {
            "data": {
                "repository": {
                    "pullRequest": {
                        "closingIssuesReferences": {"nodes": self.linked_issues}
                    }
                }
            }
        }


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
    checks_path = "/repos/acme/widget/commits/head123/check-runs"
    statuses_path = "/repos/acme/widget/commits/head123/status"
    client = FakeClient(
        {
            (pr_path, ()): {
                "html_url": "https://github.com/acme/widget/pull/42",
                "title": "Add audit trace",
                "body": "Explain the result.\n\n## Requirements\n- Emit a trace.\n- Preserve behavior.",
                "state": "open",
                "draft": False,
                "changed_files": 3,
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
                {
                    "filename": "src/new_name.py",
                    "previous_filename": "src/old_name.py",
                    "status": "renamed",
                    "blob_url": "https://github.com/acme/widget/blob/head123/src/new_name.py",
                    "patch": "@@ -1 +1 @@\n-old_name()\n+new_name()\n",
                },
            ],
            (checks_path, (("per_page", 100),)): {
                "check_runs": [{
                    "id": 9,
                    "name": "test",
                    "status": "completed",
                    "conclusion": "success",
                    "head_sha": "head123",
                    "html_url": "https://github.com/acme/widget/actions/runs/9"
                }]
            },
            (statuses_path, ()): {"statuses": []},
        }
    )

    packet = GitHubPullRequestAdapter(client=client).load("acme/widget", 42)
    packet.validate_consistency()
    assert packet.head_sha == "head123"
    assert [
        (item.base_path, item.head_path)
        for item in packet.changed_files
    ] == [
        ("src/a.py", "src/a.py"),
        (None, "tests/test_a.py"),
        ("src/old_name.py", "src/new_name.py"),
    ]
    assert [item.code for item in packet.diagnostics] == [
        "github_patch_unavailable",
        "github_linked_issue_not_found",
    ]
    assert packet.verification_observations[0].kind == "check_run"
    assert not hasattr(packet, "requirements")

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    assert [item.text for item in brief.requirements] == ["Emit a trace.", "Preserve behavior."]
    html = render_html(brief)
    assert "Collection notes" not in html
    assert "Source coverage" in html
    assert "PR #42" in html
    assert "PR #42 · Requirements" in html
    assert "#requirements" in html


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
    assert [item.code for item in packet.diagnostics] == [
        "github_file_limit_reached",
        "github_linked_issue_not_found",
        "github_head_sha_unavailable",
    ]
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    assert brief.requirements == ()
    assert brief.intent.text == "No structured requirements here."
    assert brief.intent.authority == "pr_description"
    html = render_html(brief)
    assert "No explicit acceptance criteria found." in html
    assert "R1" not in html


def test_github_graphql_linked_issue_supplies_primary_acceptance_criteria() -> None:
    pr_path = "/repos/acme/widget/pulls/8"
    files_path = "/repos/acme/widget/pulls/8/files"
    client = FakeClient(
        {
            (pr_path, ()): {
                "html_url": "https://github.com/acme/widget/pull/8",
                "title": "Implement trace",
                "body": "Implementation notes only; no Issue number is required here.",
                "changed_files": 1,
                "head": {},
                "base": {},
                "user": {},
            },
            (files_path, (("page", 1), ("per_page", 100))): [{
                "filename": "src/bounded_trace.py",
                "status": "added",
                "patch": "+def emit_bounded_trace(): pass",
            }],
        },
        linked_issues=[
            {
                "number": 41,
                "url": "https://github.com/acme/widget/issues/41",
                "title": "Trace requirements",
                "body": "## Acceptance criteria\n- Emit a bounded trace.\n- No UI changes.",
            }
        ],
    )
    packet = GitHubPullRequestAdapter(client=client).load("acme/widget", 8)
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    assert [item.text for item in brief.requirements] == ["Emit a bounded trace."]
    assert [item.text for item in brief.guardrails] == ["No UI changes."]
    html = render_html(brief)
    assert "Issue #41 · Acceptance criteria" in html
    assert "https://github.com/acme/widget/issues/41#acceptance-criteria" in html
    assert ">linked issue<" not in html


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"data": {}},
        {"data": {"repository": {}}},
        {"data": {"repository": {"pullRequest": {}}}},
        {
            "data": {
                "repository": {
                    "pullRequest": {"closingIssuesReferences": {}}
                }
            }
        },
        {
            "data": {
                "repository": {
                    "pullRequest": {
                        "closingIssuesReferences": {"nodes": {}}
                    }
                }
            }
        },
    ],
)
def test_malformed_linked_issue_structure_is_unavailable(payload: Any) -> None:
    records, diagnostics = GitHubPullRequestAdapter(
        client=FakeClient({}, graphql_payload=payload)
    )._load_linked_issues(
        repository="acme/widget",
        owner="acme",
        name="widget",
        pull_request=42,
    )

    assert records == []
    assert [item.code for item in diagnostics] == [
        "github_linked_issues_unavailable"
    ]
    assert all(item.code != "github_linked_issue_not_found" for item in diagnostics)


def test_linked_issue_lookup_failure_is_unavailable() -> None:
    records, diagnostics = GitHubPullRequestAdapter(
        client=FakeClient(
            {},
            graphql_error=GitHubApiError("linked-Issue lookup failed"),
        )
    )._load_linked_issues(
        repository="acme/widget",
        owner="acme",
        name="widget",
        pull_request=42,
    )

    assert records == []
    assert [item.code for item in diagnostics] == [
        "github_linked_issues_unavailable"
    ]


def test_partial_malformed_issue_nodes_retain_valid_records_but_are_unavailable() -> None:
    records, diagnostics = GitHubPullRequestAdapter(
        client=FakeClient(
            {},
            linked_issues=[
                {
                    "number": 41,
                    "title": "Retained issue",
                    "body": "## Requirements\n- Preserve the boundary.",
                },
                {"title": "Missing number"},
                {"number": True, "title": "Boolean is not an Issue number"},
            ],
        )
    )._load_linked_issues(
        repository="acme/widget",
        owner="acme",
        name="widget",
        pull_request=42,
    )

    assert [item.id for item in records] == ["github-issue:acme/widget#41"]
    assert [item.code for item in diagnostics] == [
        "github_linked_issues_unavailable"
    ]


@pytest.mark.parametrize(
    ("issue_body", "fallback_expected"),
    [
        ("", True),
        (None, False),
        ({"unexpected": "value"}, False),
    ],
)
def test_issue_body_validity_controls_pr_obligation_fallback_end_to_end(
    issue_body: Any,
    fallback_expected: bool,
) -> None:
    pr_path = "/repos/acme/widget/pulls/43"
    files_path = "/repos/acme/widget/pulls/43/files"
    client = FakeClient(
        {
            (pr_path, ()): {
                "html_url": "https://github.com/acme/widget/pull/43",
                "title": "Harden Issue authority",
                "body": (
                    "## Requirements\n"
                    "- Treat the PR as requirement authority.\n\n"
                    "## Change\n"
                    "- Preserve transformation extraction.\n"
                ),
                "changed_files": 0,
                "head": {},
                "base": {},
                "user": {},
            },
            (files_path, (("page", 1), ("per_page", 100))): [],
        },
        linked_issues=[
            {
                "number": 41,
                "title": "Real governing Issue",
                "body": issue_body,
                "url": "https://github.com/acme/widget/issues/41",
            }
        ],
    )

    packet = GitHubPullRequestAdapter(client=client).load("acme/widget", 43)
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))

    assert [item.text for item in brief.requirements] == (
        ["Treat the PR as requirement authority."] if fallback_expected else []
    )
    assert [item.kind for item in brief.transformation_contract.claims] == ["change"]
    unavailable = [
        item for item in packet.diagnostics
        if item.code == "github_linked_issues_unavailable"
    ]
    assert bool(unavailable) is not fallback_expected
    assert all(
        item.code != "github_linked_issue_not_found" for item in packet.diagnostics
    )


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
