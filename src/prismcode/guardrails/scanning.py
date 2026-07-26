from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from prismcode.model.contracts import (
    Diagnostic,
    GuardrailScanCoverage,
    GuardrailScanMatch,
    GuardrailScanPlan,
    GuardrailScanPlanSet,
    GuardrailScanResult,
    GuardrailScanResultSet,
    GuardrailScanSelector,
    GuardrailScanSurface,
    GuardrailScanTruncation,
    SourceRef,
)

_IGNORED_DIRECTORIES = frozenset(
    {
        ".codegraph",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "vendor",
        "venv",
    }
)
_SYMBOL_NAME = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_]*(?![A-Za-z0-9_])")


class GuardrailScanner(Protocol):
    def scan(self, plans: GuardrailScanPlanSet) -> GuardrailScanResultSet: ...


@dataclass(frozen=True)
class GuardrailScanLimits:
    max_files: int = 2_000
    max_bytes: int = 8_000_000
    max_matches_per_plan: int = 100


class RepositoryGuardrailScanner:
    """Execute typed selectors without reinterpreting guardrail prose."""

    def __init__(
        self,
        repo_root: str | Path,
        *,
        expected_revision: str | None,
        limits: GuardrailScanLimits = GuardrailScanLimits(),
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.expected_revision = expected_revision or ""
        self.limits = limits

    def scan(self, plans: GuardrailScanPlanSet) -> GuardrailScanResultSet:
        if not plans.plans:
            return GuardrailScanResultSet()
        revision = _checkout_revision(self.repo_root)
        if not revision or (
            self.expected_revision and revision != self.expected_revision
        ):
            results = tuple(
                _unavailable(
                    plan,
                    self.repo_root,
                    revision,
                    "guardrail_scan_stale_checkout",
                    (
                        "Guardrail scanning requires a checkout at the reviewed "
                        f"head {self.expected_revision or '(unknown)'}; observed "
                        f"{revision or '(unavailable)'}."
                    ),
                )
                for plan in plans.plans
            )
        elif not _tracked_checkout_clean(self.repo_root):
            results = tuple(
                _unavailable(
                    plan,
                    self.repo_root,
                    revision,
                    "guardrail_scan_dirty_checkout",
                    (
                        "Guardrail scanning requires tracked checkout content "
                        "to match the reviewed head exactly."
                    ),
                )
                for plan in plans.plans
            )
        else:
            paths, path_truncation = self._repository_paths()
            results = tuple(
                self._scan_plan(plan, revision, paths, path_truncation)
                for plan in plans.plans
            )
        result_set = GuardrailScanResultSet(results)
        result_set.validate_consistency(plans)
        return result_set

    def _repository_paths(
        self,
    ) -> tuple[tuple[Path, ...], GuardrailScanTruncation | None]:
        result = subprocess.run(
            ["git", "-C", str(self.repo_root), "ls-files", "-z"],
            check=True,
            capture_output=True,
            timeout=10,
        )
        tracked = sorted(
            item.decode("utf-8", errors="surrogateescape")
            for item in result.stdout.split(b"\0")
            if item
        )
        paths = tuple(
            path
            for relative in tracked
            for path in (self.repo_root / relative,)
            if not set(Path(relative).parts) & _IGNORED_DIRECTORIES
            and not path.is_symlink()
        )
        truncation = (
            GuardrailScanTruncation(
                kind="file_limit",
                surface="paths",
                limit=self.limits.max_files,
                observed=len(paths),
            )
            if len(paths) > self.limits.max_files
            else None
        )
        return paths[: self.limits.max_files], truncation

    def _scan_plan(
        self,
        plan: GuardrailScanPlan,
        revision: str,
        paths: tuple[Path, ...],
        path_truncation: GuardrailScanTruncation | None,
    ) -> GuardrailScanResult:
        if not plan.selectors:
            return _unavailable(
                plan,
                self.repo_root,
                revision,
                "guardrail_scan_no_executable_selector",
                f"{plan.id} has no conservative executable selector.",
            )
        matches: list[GuardrailScanMatch] = []
        bytes_read = 0
        inspected_paths = 0
        inspected_files = 0
        inspected_symbol_names = 0
        truncations: list[GuardrailScanTruncation] = []
        if path_truncation is not None:
            truncations.append(path_truncation)
        stopped = False

        for path in paths:
            inspected_paths += 1
            relative = path.relative_to(self.repo_root).as_posix()
            for selector in plan.selectors:
                if _matches(relative, selector):
                    matches.append(
                        _match(plan, selector, "paths", relative, None, relative)
                    )
                    if len(matches) >= self.limits.max_matches_per_plan:
                        truncations.append(
                            GuardrailScanTruncation(
                                kind="match_limit",
                                surface="paths",
                                limit=self.limits.max_matches_per_plan,
                                observed=len(matches),
                            )
                        )
                        stopped = True
                        break
            if stopped:
                break

        for path in (() if stopped else paths):
            relative = path.relative_to(self.repo_root).as_posix()
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            if b"\0" in raw[:4_096]:
                continue
            if bytes_read + len(raw) > self.limits.max_bytes:
                truncations.append(
                    GuardrailScanTruncation(
                        kind="byte_limit",
                        surface="file_content",
                        limit=self.limits.max_bytes,
                        observed=bytes_read + len(raw),
                    )
                )
                break
            bytes_read += len(raw)
            inspected_files += 1
            text = raw.decode("utf-8", errors="replace")
            for line_number, line in enumerate(text.splitlines(), start=1):
                for selector in plan.selectors:
                    if _matches(line, selector):
                        matches.append(
                            _match(
                                plan,
                                selector,
                                "file_content",
                                relative,
                                line_number,
                                line.strip()[:240],
                            )
                        )
                        if len(matches) >= self.limits.max_matches_per_plan:
                            truncations.append(
                                GuardrailScanTruncation(
                                    kind="match_limit",
                                    surface="file_content",
                                    limit=self.limits.max_matches_per_plan,
                                    observed=len(matches),
                                )
                            )
                            stopped = True
                            break
                if stopped:
                    break
                for symbol_name in _SYMBOL_NAME.findall(line):
                    inspected_symbol_names += 1
                    for selector in plan.selectors:
                        if (
                            selector.kind == "identifier"
                            and symbol_name.casefold() == selector.value.casefold()
                        ):
                            matches.append(
                                _match(
                                    plan,
                                    selector,
                                    "symbol_names",
                                    relative,
                                    line_number,
                                    symbol_name,
                                )
                            )
                            if len(matches) >= self.limits.max_matches_per_plan:
                                truncations.append(
                                    GuardrailScanTruncation(
                                        kind="match_limit",
                                        surface="symbol_names",
                                        limit=self.limits.max_matches_per_plan,
                                        observed=len(matches),
                                    )
                                )
                                stopped = True
                                break
                    if stopped:
                        break
                if stopped:
                    break
            if stopped:
                break

        partial = bool(truncations)
        state = "partial" if partial else "complete"
        coverage_message = (
            _truncation_message(tuple(truncations))
            if truncations
            else "All eligible tracked checkout files were inspected."
        )
        paths_partial = any(
            item.kind == "file_limit" or item.surface == "paths"
            for item in truncations
        )
        coverages = (
            GuardrailScanCoverage(
                surface="paths",
                state="partial" if paths_partial else "complete",
                inspected_count=inspected_paths,
                message=(
                    coverage_message
                    if paths_partial
                    else "Eligible repository paths enumerated."
                ),
            ),
            GuardrailScanCoverage(
                surface="file_content",
                state=state,
                inspected_count=inspected_files,
                inspected_bytes=bytes_read,
                message=coverage_message,
            ),
            GuardrailScanCoverage(
                surface="symbol_names",
                state=state,
                inspected_count=inspected_symbol_names,
                inspected_bytes=bytes_read,
                message=coverage_message,
            ),
        )
        diagnostics = ()
        if truncations:
            diagnostics = (
                Diagnostic(
                    code="guardrail_scan_budget_truncated",
                    message=coverage_message,
                    sources=(SourceRef(label="repository checkout", path="."),),
                ),
            )
        return GuardrailScanResult(
            id=f"GSR:{plan.guardrail_id}",
            plan_id=plan.id,
            guardrail_id=plan.guardrail_id,
            revision=revision,
            root_path=".",
            state=state,
            coverages=coverages,
            truncations=tuple(truncations),
            matches=tuple(matches),
            diagnostics=diagnostics,
        )


def unavailable_scan_results(
    plans: GuardrailScanPlanSet,
    *,
    message: str = "No bounded repository scan provider was configured.",
) -> GuardrailScanResultSet:
    results = GuardrailScanResultSet(
        tuple(
            _unavailable(
                plan,
                Path("."),
                "",
                "guardrail_scan_provider_unavailable",
                message,
            )
            for plan in plans.plans
        )
    )
    results.validate_consistency(plans)
    return results


def _unavailable(
    plan: GuardrailScanPlan,
    root: Path,
    revision: str,
    code: str,
    message: str,
) -> GuardrailScanResult:
    return GuardrailScanResult(
        id=f"GSR:{plan.guardrail_id}",
        plan_id=plan.id,
        guardrail_id=plan.guardrail_id,
        revision=revision,
        root_path="." if root.name else str(root),
        state="unavailable",
        coverages=tuple(
            GuardrailScanCoverage(
                surface=surface,
                state="unavailable",
                message=message,
            )
            for surface in plan.surfaces
        ),
        diagnostics=(
            Diagnostic(
                code=code,
                message=message,
            ),
        ),
    )


def _matches(value: str, selector: GuardrailScanSelector) -> bool:
    if selector.kind == "phrase":
        return selector.value.casefold() in value.casefold()
    return bool(
        re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(selector.value)}(?![A-Za-z0-9_])",
            value,
            re.IGNORECASE,
        )
    )


def _match(
    plan: GuardrailScanPlan,
    selector: GuardrailScanSelector,
    surface: GuardrailScanSurface,
    path: str,
    line: int | None,
    excerpt: str,
) -> GuardrailScanMatch:
    identity = "\0".join(
        (plan.id, selector.id, surface, path, str(line or 0))
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return GuardrailScanMatch(
        id=f"GSM:{digest}",
        plan_id=plan.id,
        guardrail_id=plan.guardrail_id,
        selector_id=selector.id,
        surface=surface,
        path=path,
        line=line,
        excerpt=excerpt,
    )


def _checkout_revision(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()


def _tracked_checkout_clean(repo_root: Path) -> bool:
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "status",
                "--porcelain",
                "--untracked-files=no",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return not result.stdout.strip()


def _truncation_message(
    truncations: tuple[GuardrailScanTruncation, ...],
) -> str:
    return "Scan stopped at " + ", ".join(
        (
            f"{item.kind.replace('_', ' ')} on {item.surface} "
            f"(limit {item.limit}, observed {item.observed})"
        )
        for item in truncations
    ) + "."
