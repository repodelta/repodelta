from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from prismcode.facts.path_profile import fact_profile
from prismcode.model.contracts import (
    ClosureRevisionObservation,
    ClosureScanCoverage,
    ClosureScanMatch,
    ClosureScanPlan,
    ClosureScanPlanSet,
    ClosureScanResult,
    ClosureScanResultSet,
    ClosureScanSelector,
    ClosureScanSurface,
    ClosureScanTruncation,
    Diagnostic,
    SourceRef,
)

_IGNORED_DIRECTORIES = frozenset({
    ".codegraph", ".git", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".tox", ".venv", "__pycache__", "build", "dist", "node_modules",
    "vendor", "venv",
})
_SYMBOL_NAME = re.compile(
    r"(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_]*(?![A-Za-z0-9_])"
)


class ClosureScanner(Protocol):
    def scan(self, plans: ClosureScanPlanSet) -> ClosureScanResultSet: ...


@dataclass(frozen=True)
class ClosureScanLimits:
    max_files: int = 2_000
    max_bytes: int = 8_000_000
    max_matches_per_plan: int = 100


class RepositoryClosureScanner:
    """Scan exact base/head checkouts without interpreting the observations."""

    def __init__(
        self,
        head_root: str | Path,
        *,
        expected_head_revision: str | None,
        base_root: str | Path | None = None,
        expected_base_revision: str | None = None,
        limits: ClosureScanLimits = ClosureScanLimits(),
    ) -> None:
        self.roots = {
            "head": Path(head_root).resolve(),
            "base": Path(base_root).resolve() if base_root else None,
        }
        self.expected_revisions = {
            "head": expected_head_revision or "",
            "base": expected_base_revision or "",
        }
        self.limits = limits

    def scan(self, plans: ClosureScanPlanSet) -> ClosureScanResultSet:
        results = ClosureScanResultSet(
            tuple(self._scan_plan(plan) for plan in plans.plans)
        )
        results.validate_consistency(plans)
        return results

    def _scan_plan(self, plan: ClosureScanPlan) -> ClosureScanResult:
        return ClosureScanResult(
            id=f"CSR:{plan.statement_id}",
            plan_id=plan.id,
            statement_id=plan.statement_id,
            statement_kind=plan.statement_kind,
            expectation=plan.expectation,
            revisions=tuple(
                self._scan_revision(plan, revision_side)
                for revision_side in plan.revision_sides
            ),
        )

    def _scan_revision(
        self,
        plan: ClosureScanPlan,
        revision_side: Literal["base", "head"],
    ) -> ClosureRevisionObservation:
        root = self.roots[revision_side]
        expected = self.expected_revisions[revision_side]
        if root is None:
            return _unavailable_revision(
                plan,
                revision_side,
                Path("."),
                "",
                "closure_scan_base_input_missing",
                (
                    "Base closure evidence is unavailable because no base "
                    "checkout was provided; removal is not inferred."
                ),
            )
        revision = _checkout_revision(root)
        if not revision or (expected and revision != expected):
            return _unavailable_revision(
                plan,
                revision_side,
                root,
                revision,
                "closure_scan_stale_checkout",
                (
                    f"Closure scanning requires {revision_side} checkout "
                    f"{expected or '(unknown)'}; observed "
                    f"{revision or '(unavailable)'}."
                ),
            )
        if not _tracked_checkout_clean(root):
            return _unavailable_revision(
                plan,
                revision_side,
                root,
                revision,
                "closure_scan_dirty_checkout",
                (
                    f"Closure scanning requires tracked {revision_side} "
                    "checkout content to match the reviewed revision exactly."
                ),
            )
        if not plan.selectors:
            return _unavailable_revision(
                plan,
                revision_side,
                root,
                revision,
                "closure_scan_no_executable_selector",
                f"{plan.id} has no conservative executable selector.",
            )
        paths, path_truncation = _repository_paths(root, self.limits)
        return _scan_paths(
            plan,
            revision_side,
            root,
            revision,
            paths,
            path_truncation,
            self.limits,
        )


def unavailable_scan_results(
    plans: ClosureScanPlanSet,
    *,
    message: str = "No bounded repository scan provider was configured.",
) -> ClosureScanResultSet:
    results = ClosureScanResultSet(
        tuple(
            ClosureScanResult(
                id=f"CSR:{plan.statement_id}",
                plan_id=plan.id,
                statement_id=plan.statement_id,
                statement_kind=plan.statement_kind,
                expectation=plan.expectation,
                revisions=tuple(
                    _unavailable_revision(
                        plan,
                        side,
                        Path("."),
                        "",
                        "closure_scan_provider_unavailable",
                        message,
                    )
                    for side in plan.revision_sides
                ),
            )
            for plan in plans.plans
        )
    )
    results.validate_consistency(plans)
    return results


def _repository_paths(
    root: Path,
    limits: ClosureScanLimits,
) -> tuple[tuple[Path, ...], ClosureScanTruncation | None]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
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
        for path in (root / relative,)
        if not set(Path(relative).parts) & _IGNORED_DIRECTORIES
        and not path.is_symlink()
    )
    truncation = (
        ClosureScanTruncation(
            kind="file_limit",
            surface="paths",
            limit=limits.max_files,
            observed=len(paths),
        )
        if len(paths) > limits.max_files
        else None
    )
    return paths[: limits.max_files], truncation


def _scan_paths(
    plan: ClosureScanPlan,
    revision_side: Literal["base", "head"],
    root: Path,
    revision: str,
    paths: tuple[Path, ...],
    path_truncation: ClosureScanTruncation | None,
    limits: ClosureScanLimits,
) -> ClosureRevisionObservation:
    matches: list[ClosureScanMatch] = []
    truncations = [path_truncation] if path_truncation else []
    bytes_read = inspected_files = inspected_symbols = 0
    stopped = False

    def add_match(
        selector: ClosureScanSelector,
        surface: ClosureScanSurface,
        path: str,
        line: int | None,
        excerpt: str,
    ) -> None:
        nonlocal stopped
        matches.append(
            _match(plan, selector, revision_side, surface, path, line, excerpt)
        )
        if len(matches) >= limits.max_matches_per_plan:
            truncations.append(
                ClosureScanTruncation(
                    kind="match_limit",
                    surface=surface,
                    limit=limits.max_matches_per_plan,
                    observed=len(matches),
                )
            )
            stopped = True

    inspected_paths = 0
    for path in paths:
        inspected_paths += 1
        relative = path.relative_to(root).as_posix()
        for selector in plan.selectors:
            if _matches(relative, selector):
                add_match(selector, "paths", relative, None, relative)
                if stopped:
                    break
        if stopped:
            break

    for path in (() if stopped else paths):
        relative = path.relative_to(root).as_posix()
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if b"\0" in raw[:4_096]:
            continue
        if bytes_read + len(raw) > limits.max_bytes:
            truncations.append(
                ClosureScanTruncation(
                    kind="byte_limit",
                    surface="file_content",
                    limit=limits.max_bytes,
                    observed=bytes_read + len(raw),
                )
            )
            break
        bytes_read += len(raw)
        inspected_files += 1
        for line_number, line in enumerate(
            raw.decode("utf-8", errors="replace").splitlines(), start=1
        ):
            for selector in plan.selectors:
                if _matches(line, selector):
                    add_match(
                        selector, "file_content", relative, line_number,
                        line.strip()[:240],
                    )
                    if stopped:
                        break
            if stopped:
                break
            for symbol in _SYMBOL_NAME.findall(line):
                inspected_symbols += 1
                for selector in plan.selectors:
                    if (
                        selector.kind == "identifier"
                        and symbol.casefold() == selector.value.casefold()
                    ):
                        add_match(
                            selector, "symbol_names", relative, line_number, symbol
                        )
                        if stopped:
                            break
                if stopped:
                    break
            if stopped:
                break
        if stopped:
            break

    truncation_tuple = tuple(truncations)
    state = "partial" if truncation_tuple else "complete"
    message = (
        _truncation_message(truncation_tuple)
        if truncation_tuple
        else "All eligible tracked checkout files were inspected."
    )
    paths_partial = any(
        item.kind == "file_limit" or item.surface == "paths"
        for item in truncation_tuple
    )
    coverages = (
        ClosureScanCoverage(
            "paths", "partial" if paths_partial else "complete",
            inspected_paths, message=message,
        ),
        ClosureScanCoverage(
            "file_content", state, inspected_files, bytes_read, message
        ),
        ClosureScanCoverage(
            "symbol_names", state, inspected_symbols, bytes_read, message
        ),
    )
    diagnostics = (
        (
            Diagnostic(
                code="closure_scan_budget_truncated",
                message=message,
                sources=(SourceRef(label=f"{revision_side} checkout", path="."),),
            ),
        )
        if truncation_tuple
        else ()
    )
    return ClosureRevisionObservation(
        revision_side=revision_side,
        revision=revision,
        root_path=".",
        state=state,
        coverages=coverages,
        truncations=truncation_tuple,
        matches=tuple(matches),
        diagnostics=diagnostics,
    )


def _unavailable_revision(
    plan: ClosureScanPlan,
    revision_side: Literal["base", "head"],
    root: Path,
    revision: str,
    code: str,
    message: str,
) -> ClosureRevisionObservation:
    return ClosureRevisionObservation(
        revision_side=revision_side,
        revision=revision,
        root_path="." if root.name else str(root),
        state="unavailable",
        coverages=tuple(
            ClosureScanCoverage(surface, "unavailable", message=message)
            for surface in plan.surfaces
        ),
        diagnostics=(Diagnostic(code=code, message=message),),
    )


def _matches(value: str, selector: ClosureScanSelector) -> bool:
    if selector.kind == "phrase":
        return selector.value.casefold() in value.casefold()
    return bool(re.search(
        rf"(?<![A-Za-z0-9_]){re.escape(selector.value)}(?![A-Za-z0-9_])",
        value,
        re.IGNORECASE,
    ))


def _match(
    plan: ClosureScanPlan,
    selector: ClosureScanSelector,
    revision_side: Literal["base", "head"],
    surface: ClosureScanSurface,
    path: str,
    line: int | None,
    excerpt: str,
) -> ClosureScanMatch:
    identity = "\0".join(
        (plan.id, revision_side, selector.id, surface, path, str(line or 0))
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return ClosureScanMatch(
        id=f"CSM:{digest}",
        plan_id=plan.id,
        statement_id=plan.statement_id,
        selector_id=selector.id,
        revision_side=revision_side,
        surface=surface,
        profile=fact_profile(path),
        path=path,
        line=line,
        excerpt=excerpt,
    )


def _checkout_revision(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()


def _tracked_checkout_clean(root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain",
             "--untracked-files=no"],
            check=True, capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return not result.stdout.strip()


def _truncation_message(
    truncations: tuple[ClosureScanTruncation, ...],
) -> str:
    return " ".join(
        f"{item.kind} reached {item.limit} while observing {item.observed} "
        f"items on {item.surface}."
        for item in truncations
    )
