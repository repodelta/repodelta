from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .contracts import ChangedFile, Diagnostic, Requirement, ReviewInput, SourceRef

JsonValue = dict[str, Any] | list[Any]
Transport = Callable[[Request, float], tuple[int, Mapping[str, str], bytes]]

_REQUIREMENT_HEADINGS = {
    "requirement",
    "requirements",
    "acceptance criteria",
    "acceptance criterion",
    "scope",
    "goals",
    "goal",
    "expected behavior",
    "expected behaviour",
}
_CHECKLIST_RE = re.compile(r"^\s*[-*+]\s+\[[ xX]\]\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+?)\s*$")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")


class GitHubApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, url: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.url = url


class GitHubJsonClient(Protocol):
    def get_json(self, path: str, query: Mapping[str, str | int] | None = None) -> JsonValue: ...


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
    timeout: float = 30.0
    transport: Transport = _default_transport

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


def _normalize_repo(repository: str) -> tuple[str, str]:
    parts = repository.strip().split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError("repository must use owner/name form")
    return parts[0], parts[1]


def _clean_markdown_text(value: str) -> str:
    value = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL)
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"[*_~]+", "", value)
    return " ".join(value.strip().split())


def extract_requirement_texts(body: str | None) -> tuple[str, ...]:
    """Extract explicit checklist items and bullets from requirement-like sections.

    This is deliberately conservative. It does not claim semantic coverage and it does
    not infer implementation evidence from a diff.
    """

    if not body:
        return ()

    current_heading: str | None = None
    values: list[str] = []
    seen: set[str] = set()

    for raw_line in body.splitlines():
        heading_match = _HEADING_RE.match(raw_line)
        if heading_match:
            current_heading = _clean_markdown_text(heading_match.group(1)).casefold()
            continue

        checklist_match = _CHECKLIST_RE.match(raw_line)
        bullet_match = _BULLET_RE.match(raw_line)
        candidate: str | None = None
        if checklist_match:
            candidate = checklist_match.group(1)
        elif bullet_match and current_heading in _REQUIREMENT_HEADINGS:
            candidate = bullet_match.group(1)

        if candidate is None:
            continue
        cleaned = _clean_markdown_text(candidate)
        key = cleaned.casefold()
        if cleaned and key not in seen:
            values.append(cleaned)
            seen.add(key)

    return tuple(values)


def extract_intent(body: str | None, title: str) -> str:
    if body:
        paragraph: list[str] = []
        for raw_line in body.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                if paragraph:
                    break
                continue
            if _HEADING_RE.match(raw_line) or _CHECKLIST_RE.match(raw_line) or _BULLET_RE.match(raw_line):
                if paragraph:
                    break
                continue
            paragraph.append(stripped)
        cleaned = _clean_markdown_text(" ".join(paragraph))
        if cleaned:
            return cleaned
    return title


@dataclass
class GitHubPullRequestAdapter:
    client: GitHubJsonClient
    max_files: int = 300

    def load(self, repository: str, pull_request: int) -> ReviewInput:
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
        requirement_texts = extract_requirement_texts(body_text)
        diagnostics: list[Diagnostic] = []

        if requirement_texts:
            requirement_source = "pull_request_description"
        else:
            requirement_texts = (title,)
            requirement_source = "title_fallback"
            diagnostics.append(
                Diagnostic(
                    code="requirements_title_fallback",
                    severity="warning",
                    message=(
                        "No explicit checklist or requirement-section bullets were found in the pull request "
                        "description. PrismCode used the pull request title as one unresolved requirement."
                    ),
                    sources=(SourceRef(label="pull request", url=pr_url),),
                )
            )

        requirements = tuple(
            Requirement(
                id=f"R{index}",
                text=text,
                status="unresolved",
                gaps=("No requirement-specific implementation or verification evidence has been established.",),
                sources=(SourceRef(label="pull request description", url=pr_url),),
            )
            for index, text in enumerate(requirement_texts, start=1)
        )

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

        return ReviewInput(
            repository=repository,
            pull_request=pull_request,
            title=title,
            intent=extract_intent(body_text, title),
            requirements=requirements,
            changed_files=tuple(changed_files),
            source_url=pr_url,
            diagnostics=tuple(diagnostics),
            metadata={
                "source": "github",
                "requirements_source": requirement_source,
                "state": raw_pr.get("state"),
                "draft": bool(raw_pr.get("draft")),
                "author": user.get("login"),
                "base_sha": base.get("sha"),
                "head_sha": head.get("sha"),
                "additions": _as_int(raw_pr.get("additions")),
                "deletions": _as_int(raw_pr.get("deletions")),
                "changed_files_reported": _as_int(raw_pr.get("changed_files")),
                "changed_files_collected": len(changed_files),
            },
        )

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
