from __future__ import annotations

from repodelta.model.contracts import ProjectionDiagnostic
from repodelta.providers.structural import StructuralGraphCollection


def review_provider_diagnostics(
    graph: StructuralGraphCollection | None,
) -> tuple[ProjectionDiagnostic, ...]:
    """Describe provider coverage once per review, never once per requirement."""

    if graph is None:
        return ()
    result = []
    result.extend(
        ProjectionDiagnostic(
            focus_statement_id="review",
            slot="structural_path",
            state="source_absent",
            provider="codegraph",
            message=diagnostic.message,
            scope="review",
            sources=diagnostic.sources,
        )
        for diagnostic in graph.diagnostics
        if diagnostic.code == "structural_graph_base_input_missing"
    )
    for revision in graph.revisions:
        affected = tuple(
            sorted({item.hunk_id for item in revision.overlaps})
        )
        result.extend(_revision_diagnostics(revision, affected))
    return tuple(result)


def _revision_diagnostics(revision, affected) -> list[ProjectionDiagnostic]:
    result = []
    side = revision.revision_side
    if revision.index.state == "stale":
        result.append(
            ProjectionDiagnostic(
                focus_statement_id="review",
                slot="structural_path",
                state="stale_source",
                provider=revision.index.provider,
                message=(
                    f"{side.title()} structural facts were not used because "
                    "the provider index does not correspond to the reviewed "
                    "revision."
                ),
                scope="review",
            )
        )
    elif not revision.index.usable:
        result.append(
            ProjectionDiagnostic(
                focus_statement_id="review",
                slot="structural_path",
                state="provider_unavailable",
                provider=revision.index.provider,
                message=(
                    f"{side.title()} structural facts were not available "
                    f"because the provider index state is {revision.index.state}."
                ),
                scope="review",
            )
        )
    if revision.index.state == "partial":
        result.append(
            ProjectionDiagnostic(
                focus_statement_id="review",
                slot="structural_path",
                state="partial_coverage",
                provider=revision.index.provider,
                message=(
                    f"{side.title()} structural facts come from a partial "
                    "index; selected paths do not represent complete "
                    "repository coverage."
                ),
                affected_ids=affected,
                scope="review",
            )
        )
    truncated = tuple(
        item for item in revision.traversal_coverage if item.state == "truncated"
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
                provider=revision.index.provider,
                message=(
                    f"{side.title()} structural traversal completed for "
                    f"{len(revision.traversal_coverage) - len(truncated)}/"
                    f"{len(revision.traversal_coverage)} changed-symbol seeds; "
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
    return result
