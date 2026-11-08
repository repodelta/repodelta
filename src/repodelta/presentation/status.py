from __future__ import annotations

from repodelta.model.contracts import ProviderCoverage, StructuralCoverage


def format_structural_coverage(coverage: StructuralCoverage) -> str:
    """Format canonical coverage without inspecting provider diagnostics."""

    if coverage.state == "disabled":
        return "Structural mapping: disabled · change-relation fallback used"
    if coverage.state == "unavailable":
        return "Structural mapping: unavailable · change-relation fallback used"
    if coverage.state == "available":
        traversal = (
            f"{coverage.complete_seed_count}/{coverage.seed_count} seeds complete"
            + (
                f", {coverage.truncated_seed_count} truncated"
                if coverage.truncated_seed_count
                else ""
            )
        )
        return (
            "Structural mapping: Codegraph available · "
            f"{coverage.mapped_hunk_count}/{coverage.hunk_count} hunks mapped to "
            f"{coverage.symbol_count} symbols · {coverage.path_count} bounded paths · "
            f"{traversal} · "
            f"{_base_coverage(coverage)} · uncovered change relations retained"
        )
    if coverage.state == "partial":
        return (
            "Structural mapping: partial · "
            f"{coverage.indexed_files}/{coverage.requested_files} changed files indexed · "
            f"{_base_coverage(coverage)} · "
            "change-relation fallback used for uncovered changes"
        )
    reason = {
        "stale": "Codegraph index is stale",
        "invalid": "Codegraph index schema is incompatible",
        "error": "Codegraph index could not be read",
        "missing": (
            "Codegraph index not found"
            if coverage.missing_reason == "index_absent"
            else "no changed files are present in the Codegraph index"
        ),
    }[coverage.state]
    return f"Structural mapping: skipped · {reason} · change-relation fallback used"


def _base_coverage(coverage: StructuralCoverage) -> str:
    if coverage.base_state in {"available", "partial"}:
        return (
            f"base {coverage.base_mapped_hunk_count}/"
            f"{coverage.base_hunk_count} hunks mapped to "
            f"{coverage.base_symbol_count} symbols"
        )
    return f"base {coverage.base_state}"


def format_provider_coverage(coverage: ProviderCoverage) -> str:
    """One line per provider: state, examined files, gaps and declared capabilities."""

    if coverage.state == "not_requested":
        scope = "no changed files dispatched"
    else:
        examined = sum(1 for item in coverage.files if item.state != "unavailable")
        declined = len(coverage.files) - examined
        gaps = sum(len(item.gaps) for item in coverage.files)
        scope = (
            f"{examined}/{len(coverage.files)} files examined"
            + (f", {declined} unavailable" if declined else "")
            + (f", {gaps} uninterpreted" if gaps else "")
            + f" · {coverage.fact_count} facts"
        )
    return (
        f"Evidence provider {coverage.provider}: {coverage.state} · {scope} · "
        f"capabilities: {', '.join(coverage.capabilities)}"
    )


def format_unclaimed_files(paths: tuple[str, ...]) -> str | None:
    if not paths:
        return None
    return (
        f"Evidence providers: {len(paths)} changed files claimed by no provider · "
        + ", ".join(paths)
    )
