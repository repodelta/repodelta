from __future__ import annotations

import json
from hashlib import sha256
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

from .contracts import (
    ChangedFile,
    Diagnostic,
    ReviewSourcePacket,
    SourceRecord,
    SourceRef,
    VerificationObservation,
)
from .criteria import extract_intent, extract_requirement_texts

JsonValue = dict[str, Any] | list[Any]
Transport = Callable[[Request, float], tuple[int, Mapping[str, str], bytes]]
_LINKED_ISSUES_QUERY = """
query PrismCodeLinkedIssues($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      closingIssuesReferences(first: 20) {
        nodes { number title url body }
      }
    }
  }
}
"""

class GitHubApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, url: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.url = url


class GitHubJsonClient(Protocol):
    def get_json(self, path: str, query: Mapping[str, str | int] | None = None) -> JsonValue: ...

    def post_graphql(self, query: str, variables: Mapping[str, object]) -> JsonValue: ...


def _default_transport(request: Request, timeout: float) -> tuple[int, Mapping[str, str], bytes]:
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers.items()), response.read()
    except HTTPError as exc:
        body = exc.read()
        raise GitHubApiError(
            _http_error_message(exc.code, body),
            status_code=exc.code,
            url=request.full_url,
        ) from exc
    except URLError as exc:
        raise GitHubApiError(f"GitHub request failed: {exc.reason}", url=request.full_url) from exc


def _http_error_message(status_code: int, body: bytes) -> str:
    detail = ""
    try:
        payload = json.loads(body.decode("utf-8"))
        if isinstance(payload, dict) and payload.get("message"):
            detail = f": {payload['message']}"
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass
    return f"GitHub API returned HTTP {status_code}{detail}"


@dataclass
class GitHubClient:
    token: str | None = None
    api_url: str = "https://api.github.com"
    trusted_api_hosts: tuple[str, ...] = ("api.github.com",)
    timeout: float = 30.0
    transport: Transport = _default_transport

    def __post_init__(self) -> None:
        parsed = urlparse(self.api_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("GitHub API URL must be an absolute HTTPS URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("GitHub API URL must not contain credentials, query, or fragment")
        trusted_hosts = {host.casefold() for host in self.trusted_api_hosts}
        if self.token and parsed.hostname.casefold() not in trusted_hosts:
            raise ValueError(
                "Refusing to send a token to an untrusted GitHub API host; "
                "set trusted_api_hosts explicitly"
            )

    def get_json(self, path: str, query: Mapping[str, str | int] | None = None) -> JsonValue:
        base = self.api_url.rstrip("/")
        normalized_path = "/" + path.lstrip("/")
        url = f"{base}{normalized_path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "prismcode-open-core",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        status, _, body = self.transport(Request(url, headers=headers, method="GET"), self.timeout)
        if status < 200 or status >= 300:
            raise GitHubApiError(_http_error_message(status, body), status_code=status, url=url)
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubApiError("GitHub API returned invalid JSON", status_code=status, url=url) from exc

    def post_graphql(self, query: str, variables: Mapping[str, object]) -> JsonValue:
        base = self.api_url.rstrip("/")
        url = (
            base.removesuffix("/api/v3") + "/api/graphql"
            if base.endswith("/api/v3")
            else base + "/graphql"
        )
        headers = {
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "prismcode-open-core",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        encoded = json.dumps({"query": query, "variables": dict(variables)}).encode("utf-8")
        status, _, body = self.transport(
            Request(url, headers=headers, data=encoded, method="POST"),
            self.timeout,
        )
        if status < 200 or status >= 300:
            raise GitHubApiError(_http_error_message(status, body), status_code=status, url=url)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubApiError("GitHub GraphQL returned invalid JSON", status_code=status, url=url) from exc
        if isinstance(payload, dict) and payload.get("errors"):
            raise GitHubApiError("GitHub GraphQL returned errors", status_code=status, url=url)
        return payload


def _normalize_repo(repository: str) -> tuple[str, str]:
    parts = repository.strip().split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError("repository must use owner/name form")
    return parts[0], parts[1]


@dataclass
class GitHubPullRequestAdapter:
    client: GitHubJsonClient
    max_files: int = 300

    def load(self, repository: str, pull_request: int) -> ReviewSourcePacket:
        if pull_request <= 0:
            raise ValueError("pull request number must be positive")
        if self.max_files <= 0:
            raise ValueError("max_files must be positive")

        owner, name = _normalize_repo(repository)
        owner_path = quote(owner, safe="")
        name_path = quote(name, safe="")
        pr_path = f"/repos/{owner_path}/{name_path}/pulls/{pull_request}"
        raw_pr = self.client.get_json(pr_path)
        if not isinstance(raw_pr, dict):
            raise GitHubApiError("GitHub pull request response was not an object")

        pr_url = str(raw_pr.get("html_url") or f"https://github.com/{repository}/pull/{pull_request}")
        title = str(raw_pr.get("title") or f"Pull request #{pull_request}")
        body = raw_pr.get("body")
        body_text = body if isinstance(body, str) else None
        diagnostics: list[Diagnostic] = []

        changed_files, file_diagnostics = self._load_files(
            repository=repository,
            owner_path=owner_path,
            name_path=name_path,
            pull_request=pull_request,
            expected_count=_as_int(raw_pr.get("changed_files")),
        )
        diagnostics.extend(file_diagnostics)

        head = raw_pr.get("head") if isinstance(raw_pr.get("head"), dict) else {}
        base = raw_pr.get("base") if isinstance(raw_pr.get("base"), dict) else {}
        user = raw_pr.get("user") if isinstance(raw_pr.get("user"), dict) else {}

        record_body = body_text or ""
        source_records = [
            SourceRecord(
                id=f"github-pr:{repository}#{pull_request}",
                kind="pull_request",
                repository=repository,
                url=pr_url,
                title=title,
                body=record_body,
                revision="sha256:" + sha256(f"{title}\0{record_body}".encode("utf-8")).hexdigest(),
            )
        ]
        linked_issue_records, issue_diagnostics = self._load_linked_issues(
            repository=repository,
            owner=owner,
            name=name,
            pull_request=pull_request,
        )
        source_records.extend(linked_issue_records)
        diagnostics.extend(issue_diagnostics)
        if not linked_issue_records and not issue_diagnostics:
            diagnostics.append(
                Diagnostic(
                    code="github_linked_issue_not_found",
                    severity="info",
                    message="GitHub returned no Development-linked Issue for this pull request.",
                    sources=(SourceRef(label="pull request", url=pr_url),),
                )
            )
        head_sha = head.get("sha") if isinstance(head.get("sha"), str) else None
        verification_observations: list[VerificationObservation] = []
        if head_sha:
            verification_observations, verification_diagnostics = self._load_verification(
                owner_path=owner_path,
                name_path=name_path,
                head_sha=head_sha,
            )
            diagnostics.extend(verification_diagnostics)
            if not verification_observations and not verification_diagnostics:
                diagnostics.append(
                    Diagnostic(
                        code="github_verification_not_found",
                        severity="info",
                        message="GitHub returned no Check Run or commit-status observation for the current PR head.",
                    )
                )
        else:
            diagnostics.append(
                Diagnostic(
                    code="github_head_sha_unavailable",
                    message="The PR head SHA is unavailable, so current-head verification could not be collected.",
                    sources=(SourceRef(label="pull request", url=pr_url),),
                )
            )
        packet = ReviewSourcePacket(
            repository=repository,
            pull_request=pull_request,
            title=title,
            source_records=tuple(source_records),
            changed_files=tuple(changed_files),
            verification_observations=tuple(verification_observations),
            source_url=pr_url,
            head_sha=head_sha,
            base_sha=base.get("sha"),
            diagnostics=tuple(diagnostics),
            metadata={
                "source": "github",
                "state": raw_pr.get("state"),
                "merged": bool(raw_pr.get("merged")),
                "draft": bool(raw_pr.get("draft")),
                "author": user.get("login"),
                "additions": _as_int(raw_pr.get("additions")),
                "deletions": _as_int(raw_pr.get("deletions")),
                "changed_files_reported": _as_int(raw_pr.get("changed_files")),
                "changed_files_collected": len(changed_files),
            },
        )
        return packet.with_revision()

    def _load_linked_issues(
        self,
        *,
        repository: str,
        owner: str,
        name: str,
        pull_request: int,
    ) -> tuple[list[SourceRecord], list[Diagnostic]]:
        try:
            payload = self.client.post_graphql(
                _LINKED_ISSUES_QUERY,
                {"owner": owner, "name": name, "number": pull_request},
            )
        except GitHubApiError as exc:
            return [], [Diagnostic(code="github_linked_issues_unavailable", message=str(exc))]
        data = payload.get("data") if isinstance(payload, dict) else None
        repository_row = data.get("repository") if isinstance(data, dict) else None
        pr_row = repository_row.get("pullRequest") if isinstance(repository_row, dict) else None
        references = pr_row.get("closingIssuesReferences") if isinstance(pr_row, dict) else None
        nodes = references.get("nodes", []) if isinstance(references, dict) else []
        records: list[SourceRecord] = []
        for row in nodes if isinstance(nodes, list) else []:
            if not isinstance(row, dict) or not isinstance(row.get("number"), int):
                continue
            issue_number = row["number"]
            issue_title = str(row.get("title") or f"Issue #{issue_number}")
            issue_body = str(row.get("body") or "")
            records.append(
                SourceRecord(
                    id=f"github-issue:{repository}#{issue_number}",
                    kind="linked_issue",
                    repository=repository,
                    url=row.get("url") if isinstance(row.get("url"), str) else None,
                    title=issue_title,
                    body=issue_body,
                    revision="sha256:"
                    + sha256(f"{issue_title}\0{issue_body}".encode("utf-8")).hexdigest(),
                )
            )
        diagnostics = []
        if len(records) > 1:
            diagnostics.append(
                Diagnostic(
                    code="github_linked_issues_ambiguous",
                    message=f"GitHub returned {len(records)} linked Issues; no single primary Issue was inferred.",
                )
            )
        return records, diagnostics

    def _load_verification(
        self,
        *,
        owner_path: str,
        name_path: str,
        head_sha: str,
    ) -> tuple[list[VerificationObservation], list[Diagnostic]]:
        observations: list[VerificationObservation] = []
        diagnostics: list[Diagnostic] = []
        checks_path = f"/repos/{owner_path}/{name_path}/commits/{head_sha}/check-runs"
        statuses_path = f"/repos/{owner_path}/{name_path}/commits/{head_sha}/status"
        try:
            payload = self.client.get_json(checks_path, {"per_page": 100})
            rows = payload.get("check_runs", []) if isinstance(payload, dict) else []
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, dict):
                    continue
                observations.append(
                    VerificationObservation(
                        id=f"check-run:{row.get('id')}",
                        name=str(row.get("name") or "check run"),
                        kind="check_run",
                        status=str(row.get("status") or "unknown"),
                        conclusion=str(row.get("conclusion") or ""),
                        head_sha=str(row.get("head_sha") or head_sha),
                        details_url=row.get("html_url") if isinstance(row.get("html_url"), str) else None,
                    )
                )
        except GitHubApiError as exc:
            diagnostics.append(Diagnostic(code="github_check_runs_unavailable", message=str(exc)))
        try:
            payload = self.client.get_json(statuses_path)
            rows = payload.get("statuses", []) if isinstance(payload, dict) else []
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, dict):
                    continue
                observations.append(
                    VerificationObservation(
                        id=f"commit-status:{row.get('id')}",
                        name=str(row.get("context") or "commit status"),
                        kind="commit_status",
                        status="completed" if row.get("state") not in {"pending", None} else "pending",
                        conclusion=str(row.get("state") or ""),
                        head_sha=head_sha,
                        details_url=row.get("target_url") if isinstance(row.get("target_url"), str) else None,
                    )
                )
        except GitHubApiError as exc:
            diagnostics.append(Diagnostic(code="github_commit_statuses_unavailable", message=str(exc)))
        return observations, diagnostics

    def _load_files(
        self,
        *,
        repository: str,
        owner_path: str,
        name_path: str,
        pull_request: int,
        expected_count: int | None,
    ) -> tuple[list[ChangedFile], list[Diagnostic]]:
        files: list[ChangedFile] = []
        diagnostics: list[Diagnostic] = []
        page = 1

        while len(files) < self.max_files:
            per_page = min(100, self.max_files - len(files))
            path = f"/repos/{owner_path}/{name_path}/pulls/{pull_request}/files"
            payload = self.client.get_json(path, {"per_page": per_page, "page": page})
            if not isinstance(payload, list):
                raise GitHubApiError("GitHub changed-files response was not an array")
            for item in payload:
                if not isinstance(item, dict) or not item.get("filename"):
                    continue
                filename = str(item["filename"])
                patch = item.get("patch") if isinstance(item.get("patch"), str) else None
                source_url = item.get("blob_url") if isinstance(item.get("blob_url"), str) else None
                files.append(
                    ChangedFile(
                        path=filename,
                        status=str(item.get("status") or "modified"),
                        additions=_as_int(item.get("additions")),
                        deletions=_as_int(item.get("deletions")),
                        changes=_as_int(item.get("changes")),
                        source_url=source_url,
                        patch=patch,
                    )
                )
                if patch is None:
                    diagnostics.append(
                        Diagnostic(
                            code="github_patch_unavailable",
                            severity="warning",
                            message=(
                                f"GitHub did not provide a patch for {filename}. The file is listed, but its "
                                "line-level change content is unavailable to this run."
                            ),
                            sources=(SourceRef(label="changed file", url=source_url, path=filename),),
                        )
                    )
                if len(files) >= self.max_files:
                    break
            if len(payload) < per_page or not payload:
                break
            page += 1

        if expected_count is not None and expected_count > len(files):
            diagnostics.append(
                Diagnostic(
                    code="github_file_limit_reached",
                    severity="warning",
                    message=(
                        f"GitHub reports {expected_count} changed files, but this run collected {len(files)} "
                        f"because --max-files is {self.max_files}."
                    ),
                    sources=(
                        SourceRef(
                            label="pull request",
                            url=f"https://github.com/{repository}/pull/{pull_request}/files",
                        ),
                    ),
                )
            )
        return files, diagnostics


def _as_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
