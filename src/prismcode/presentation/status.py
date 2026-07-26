from __future__ import annotations

from prismcode.model.contracts import StructuralCoverage


def format_structural_coverage(coverage: StructuralCoverage) -> str:
    """Format canonical coverage without inspecting provider diagnostics."""

    if coverage.state == "disabled":
        return "Structural mapping: disabled · changed-span fallback used"
    if coverage.state == "unavailable":
        return "Structural mapping: unavailable · changed-span fallback used"
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
            "uncovered change spans retained"
        )
    if coverage.state == "partial":
        return (
            "Structural mapping: partial · "
            f"{coverage.indexed_files}/{coverage.requested_files} changed files indexed · "
            "changed-span fallback used for uncovered changes"
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
    return f"Structural mapping: skipped · {reason} · changed-span fallback used"
