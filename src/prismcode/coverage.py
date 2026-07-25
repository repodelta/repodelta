from __future__ import annotations

from .contracts import ProjectionDiagnostic
from .structural_graph import StructuralGraphResult


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
    if any(
        item.code == "structural_graph_traversal_budget_reached"
        for item in graph.diagnostics
    ):
        result.append(
            ProjectionDiagnostic(
                focus_statement_id="review",
                slot="structural_path",
                state="budget_truncated",
                provider=graph.index.provider,
                message=(
                    "Structural path collection reached the provider traversal "
                    "budget before projection selection."
                ),
                affected_ids=affected,
                scope="review",
            )
        )
    return tuple(result)
