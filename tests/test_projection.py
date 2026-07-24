from __future__ import annotations

from dataclasses import asdict

from prismcode.contracts import (
    BindingReason,
    CandidateBinding,
    CandidateBindingKind,
    CandidateBindingSet,
    EvidenceCatalog,
    EvidenceItem,
    Requirement,
)
from prismcode.projection import ProjectionPolicy, build_review_projection
from prismcode.structural_graph import (
    StructuralGraphIndexStatus,
    StructuralGraphResult,
)


def _binding(
    binding_id: str,
    *,
    kind: CandidateBindingKind,
    source: str,
    target: str,
    score: int,
    paths: tuple[str, ...] = (),
) -> CandidateBinding:
    return CandidateBinding(
        id=binding_id,
        kind=kind,
        source_id=source,
        target_id=target,
        score=score,
        reasons=(
            BindingReason(
                feature="fixture",
                detail="Golden candidate relation.",
                weight=score,
            ),
        ),
        structural_path_ids=paths,
    )


def _graph_catalog() -> EvidenceCatalog:
    return EvidenceCatalog(
        items=(
            EvidenceItem(
                id="E:symbol:Y",
                kind="symbol",
                summary="Changed adapter Y",
                classification="code",
                changed=True,
                structural_path_ids=("E:path:runtime", "E:path:test"),
                metadata={"path": "src/adapter.py", "qualified_name": "adapter.Y"},
            ),
            EvidenceItem(
                id="E:symbol:X",
                kind="symbol",
                summary="Unchanged runtime X",
                classification="code",
                structural_path_ids=("E:path:runtime",),
                metadata={"path": "src/core.py", "qualified_name": "core.X"},
            ),
            EvidenceItem(
                id="E:symbol:Z",
                kind="symbol",
                summary="Unchanged test Z",
                classification="test",
                structural_path_ids=("E:path:test",),
                metadata={"path": "tests/test_core.py", "qualified_name": "tests.Z"},
            ),
            EvidenceItem(
                id="E:path:runtime",
                kind="structural_path",
                summary="adapter.Y →[calls] core.X",
                classification="runtime",
                structural_path_ids=("E:path:runtime",),
                metadata={"depth": 1},
            ),
            EvidenceItem(
                id="E:path:test",
                kind="structural_path",
                summary="adapter.Y →[calls] core.X ←[references] tests.Z",
                classification="mixed",
                structural_path_ids=("E:path:test",),
                metadata={"depth": 2},
            ),
            EvidenceItem(
                id="E:ci:test",
                kind="check_run",
                summary="test: completed/success",
                classification="ci",
                metadata={"observation_id": "check:test"},
            ),
        )
    )


def test_graph_projection_selects_bounded_canonical_references() -> None:
    bindings = CandidateBindingSet(
        items=(
            _binding(
                "B:claim",
                kind="requirement_claim",
                source="R1",
                target="C1",
                score=28,
            ),
            _binding(
                "B:Y",
                kind="statement_evidence",
                source="R1",
                target="E:symbol:Y",
                score=40,
                paths=("E:path:runtime", "E:path:test"),
            ),
            _binding(
                "B:X",
                kind="statement_evidence",
                source="R1",
                target="E:symbol:X",
                score=20,
                paths=("E:path:runtime",),
            ),
            _binding(
                "B:Z",
                kind="statement_evidence",
                source="R1",
                target="E:symbol:Z",
                score=18,
                paths=("E:path:test",),
            ),
            _binding(
                "B:CI",
                kind="statement_evidence",
                source="R1",
                target="E:ci:test",
                score=7,
            ),
            _binding(
                "B:path:runtime",
                kind="statement_evidence",
                source="R1",
                target="E:path:runtime",
                score=14,
                paths=("E:path:runtime",),
            ),
            _binding(
                "B:path:test",
                kind="statement_evidence",
                source="R1",
                target="E:path:test",
                score=12,
                paths=("E:path:test",),
            ),
        )
    )
    graph = StructuralGraphResult(
        index=StructuralGraphIndexStatus(
            state="available",
            provider="codegraph",
        )
    )

    projection = build_review_projection(
        requirements=(Requirement(id="R1", text="Adapter calls core and has tests."),),
        evidence_catalog=_graph_catalog(),
        candidate_bindings=bindings,
        structural_graph=graph,
    )

    assert projection.schema_version == "review_projection.v1"
    assert projection.diagnostics == ()
    assert len(projection.slices) == 1
    review_slice = projection.slices[0]
    assert review_slice.focus_statement_id == "R1"
    assert review_slice.claim_binding_ids == ("B:claim",)
    assert review_slice.changed_evidence_ids == ("E:symbol:Y",)
    assert review_slice.runtime_evidence_ids == ("E:symbol:X",)
    assert review_slice.test_evidence_ids == ("E:symbol:Z",)
    assert review_slice.ci_evidence_ids == ("E:ci:test",)
    assert review_slice.structural_path_evidence_ids == (
        "E:path:runtime",
        "E:path:test",
    )
    serialized = asdict(review_slice)
    assert "claim_ids" not in serialized
    assert "evidence" not in serialized
    assert "text" not in serialized


def test_hunk_fallback_uses_the_same_projection_contract() -> None:
    catalog = EvidenceCatalog(
        items=(
            EvidenceItem(
                id="E:hunk:Y",
                kind="changed_hunk",
                summary="Changed hunk: src/adapter.py:1-3",
                classification="code",
                changed=True,
                metadata={"path": "src/adapter.py"},
            ),
        )
    )
    bindings = CandidateBindingSet(
        items=(
            _binding(
                "B:hunk",
                kind="statement_evidence",
                source="R1",
                target="E:hunk:Y",
                score=21,
            ),
        )
    )

    projection = build_review_projection(
        requirements=(Requirement(id="R1", text="Change the adapter."),),
        evidence_catalog=catalog,
        candidate_bindings=bindings,
        structural_graph=None,
    )

    review_slice = projection.slices[0]
    assert review_slice.changed_evidence_ids == ("E:hunk:Y",)
    assert review_slice.runtime_evidence_ids == ()
    assert review_slice.test_evidence_ids == ()
    assert review_slice.structural_path_evidence_ids == ()
    assert [item.code for item in projection.diagnostics] == [
        "projection_structure_unavailable"
    ]


def test_projection_is_deterministic_and_bounded_per_requirement() -> None:
    catalog = EvidenceCatalog(
        items=tuple(
            EvidenceItem(
                id=f"E:hunk:{index}",
                kind="changed_hunk",
                summary=f"Changed hunk {index}",
                classification="code",
                changed=True,
            )
            for index in range(4)
        )
    )
    bindings = CandidateBindingSet(
        items=tuple(
            _binding(
                f"B:{index}",
                kind="statement_evidence",
                source="R1",
                target=f"E:hunk:{index}",
                score=10,
            )
            for index in reversed(range(4))
        )
    )
    arguments = {
        "requirements": (Requirement(id="R1", text="Bound projection."),),
        "evidence_catalog": catalog,
        "candidate_bindings": bindings,
        "structural_graph": None,
        "policy": ProjectionPolicy(max_changed=2),
    }

    first = build_review_projection(**arguments)
    second = build_review_projection(**arguments)

    assert first == second
    assert first.slices[0].changed_evidence_ids == ("E:hunk:0", "E:hunk:1")
