from __future__ import annotations

from prismcode.model.contracts import ProjectionDiagnostic
from prismcode.providers.structural import StructuralGraphResult


def review_provider_diagnostics(
    graph: StructuralGraphResult | None,
) -> tuple[ProjectionDiagnostic, ...]:
    """Describe provider coverage once per review, never once per requirement."""

    if graph is None:
        return ()
    affected = tuple(sorted({item.hunk_id for item in graph.overlaps}))
    result = []
    if graph.index.state == "stale":
        result.append(
            ProjectionDiagnostic(
                focus_statement_id="review",
                slot="structural_path",
                state="stale_source",
                provider=graph.index.provider,
                message=(
                    "Structural facts were not used because the provider index "
                    "does not correspond to the reviewed revision."
                ),
                scope="review",
            )
        )
    elif not graph.index.usable:
        result.append(
            ProjectionDiagnostic(
                focus_statement_id="review",
                slot="structural_path",
                state="provider_unavailable",
                provider=graph.index.provider,
                message=(
                    "Structural facts were not available because the provider "
                    f"index state is {graph.index.state}."
                ),
                scope="review",
            )
        )
    if graph.index.state == "partial":
        result.append(
            ProjectionDiagnostic(
                focus_statement_id="review",
                slot="structural_path",
                state="partial_coverage",
                provider=graph.index.provider,
                message=(
                    "Structural facts come from a partial index; selected paths "
                    "do not represent complete repository coverage."
                ),
                affected_ids=affected,
                scope="review",
            )
        )
    truncated = tuple(
        item for item in graph.traversal_coverage if item.state == "truncated"
    )
    if truncated:
        limiting_dimensions = tuple(
            dict.fromkeys(
                dimension
                for item in truncated
                for dimension in item.limiting_dimensions
            )
        )
        result.append(
            ProjectionDiagnostic(
                focus_statement_id="review",
                slot="structural_path",
                state="budget_truncated",
                provider=graph.index.provider,
                message=(
                    f"Structural traversal completed for "
                    f"{len(graph.traversal_coverage) - len(truncated)}/"
                    f"{len(graph.traversal_coverage)} changed-symbol seeds; "
                    f"{len(truncated)} reached the provider "
                    f"{' and '.join(item.replace('_', ' ') for item in limiting_dimensions)} "
                    "safety boundary."
                ),
                affected_ids=tuple(item.seed_symbol_id for item in truncated),
                scope="review",
                sources=tuple(
                    dict.fromkeys(
                        source for item in truncated for source in item.sources
                    )
                ),
            )
        )
    return tuple(result)
