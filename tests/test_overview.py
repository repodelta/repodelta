from __future__ import annotations

from dataclasses import asdict

from prismcode.model.contracts import ProjectionDiagnostic, SourceRef
from prismcode.projection.overview import _projection_attention
from prismcode.providers.structural import (
    StructuralGraphCollection,
    StructuralGraphIndexStatus,
    StructuralGraphResult,
    StructuralSeedCoverage,
)
from prismcode.routing.coverage import review_provider_diagnostics


def _head_graph(**values) -> StructuralGraphCollection:
    return StructuralGraphCollection(
        revisions=(StructuralGraphResult(**values),)
    )


def _diagnostic(
    focus: str,
    *,
    scope: str = "focus",
    provider: str = "",
    slot: str = "structural_path",
    state: str = "budget_truncated",
    message: str,
    sources: tuple[SourceRef, ...] = (),
) -> ProjectionDiagnostic:
    return ProjectionDiagnostic(
        focus_statement_id=focus,
        slot=slot,
        state=state,
        message=message,
        provider=provider,
        sources=sources,
        scope=scope,
    )


def test_attention_separates_provider_and_convergence_truncation() -> None:
    attention = _projection_attention(
        (
            _diagnostic(
                "review",
                scope="review",
                provider="codegraph",
                message="Provider traversal stopped at its path budget.",
            ),
            _diagnostic("R1", message="R1 retained a bounded path set."),
            _diagnostic("R2", message="R2 retained a bounded path set."),
        )
    )

    assert len(attention) == 2
    assert attention[0].label == (
        "Structural coverage · codegraph · budget truncated"
    )
    assert attention[0].scope == "review"
    assert attention[0].provider == "codegraph"
    assert attention[0].focus_statement_ids == ()
    assert attention[1].label == "structural path · budget truncated"
    assert attention[1].scope == "focus"
    assert attention[1].provider == ""
    assert attention[1].focus_statement_ids == ("R1", "R2")


def test_provider_traversal_coverage_is_review_level_and_seed_specific() -> None:
    graph = _head_graph(
        index=StructuralGraphIndexStatus(
            state="available",
            provider="codegraph",
        ),
        traversal_coverage=(
            StructuralSeedCoverage(
                seed_symbol_id="symbol:A",
                state="truncated",
                node_count=80,
                path_count=42,
                limiting_dimensions=("seed_node_budget",),
            ),
            StructuralSeedCoverage(
                seed_symbol_id="symbol:B",
                state="complete",
                node_count=4,
                path_count=3,
            ),
        ),
    )

    diagnostics = review_provider_diagnostics(graph)

    assert len(diagnostics) == 1
    assert diagnostics[0].scope == "review"
    assert diagnostics[0].focus_statement_id == "review"
    assert diagnostics[0].affected_ids == ("symbol:A",)
    assert diagnostics[0].message == (
        "Head structural traversal completed for 1/2 changed-symbol seeds; "
        "1 reached the provider seed node budget safety boundary."
    )


def test_attention_separates_review_providers_and_preserves_sources() -> None:
    codegraph_source = SourceRef(label="Codegraph")
    other_source = SourceRef(label="Other graph")
    attention = _projection_attention(
        (
            _diagnostic(
                "review",
                scope="review",
                provider="other",
                message="Other provider stopped.",
                sources=(other_source,),
            ),
            _diagnostic(
                "review",
                scope="review",
                provider="codegraph",
                message="Codegraph stopped.",
                sources=(codegraph_source,),
            ),
        )
    )

    assert [item.provider for item in attention] == ["codegraph", "other"]
    assert [item.sources for item in attention] == [
        (codegraph_source,),
        (other_source,),
    ]
    assert asdict(attention[0])["scope"] == "review"
    assert asdict(attention[0])["provider"] == "codegraph"


def test_attention_order_is_independent_of_diagnostic_input_order() -> None:
    diagnostics = (
        _diagnostic("R10", message="Tenth focus."),
        _diagnostic("R2", message="Second focus."),
        _diagnostic(
            "review",
            scope="review",
            provider="codegraph",
            message="Review coverage.",
        ),
        _diagnostic("R1", message="First focus."),
    )

    first = _projection_attention(diagnostics)
    assert first == _projection_attention(
        tuple(reversed(diagnostics))
    )
    assert first[1].focus_statement_ids == ("R1", "R2", "R10")


def test_acceptance_basis_label_remains_unchanged() -> None:
    attention = _projection_attention(
        (
            _diagnostic(
                "I1",
                slot="claim",
                state="source_absent",
                message="No explicit acceptance basis.",
            ),
        )
    )

    assert len(attention) == 1
    assert attention[0].label == "Acceptance basis"
