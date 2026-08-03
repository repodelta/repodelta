from __future__ import annotations

from dataclasses import replace

import pytest

from prismcode.model.contracts import (
    AnalysisInput,
    ChangedFile,
    ReviewSourcePacket,
    SourceRecord,
    TransformationAlignment,
    VerificationObservation,
)
from prismcode.pipeline import DeterministicAnalyzer


def _packet() -> ReviewSourcePacket:
    body = (
        "## Change\n- Replace `old_call` with `new_call`.\n\n"
        "## After topology\n- `new_call` is the canonical entry point.\n\n"
        "## Removal\n- Remove `old_call`.\n\n"
        "## Completion conditions\n- The `test_suite` check runs.\n\n"
        "## Uncertainty\n- External deployment behavior is unknown.\n"
    )
    return ReviewSourcePacket(
        repository="acme/widget",
        pull_request=9,
        title="Align transformation claims",
        source_records=(
            SourceRecord(
                id="pr:9",
                kind="pull_request",
                repository="acme/widget",
                title="Align transformation claims",
                body=body,
            ),
        ),
        changed_files=(
            ChangedFile(
                base_path="src/service.py",
                head_path="src/service.py",
                patch="@@ -1 +1 @@\n-old_call()\n+new_call()\n",
            ),
        ),
        verification_observations=(
            VerificationObservation(
                id="check:test_suite",
                name="test_suite",
                kind="check_run",
                status="completed",
                conclusion="success",
                head_sha="head123",
                provider="github",
            ),
        ),
        head_sha="head123",
    ).with_revision()


def test_pipeline_aligns_typed_claims_to_revision_appropriate_facts() -> None:
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=_packet()))
    claims = {item.kind: item for item in brief.transformation_contract.claims}
    bindings = brief.transformation_alignment.by_claim_id()
    evidence = brief.evidence_catalog.by_id()

    removal = bindings[claims["removal"].id]
    assert len(removal) == 1
    assert removal[0].association == "exact_identifier"
    assert evidence[removal[0].evidence_id].operation == "replaced"
    assert "oldcall" in removal[0].reasons[0].matched_terms

    after = bindings[claims["after_topology"].id]
    assert len(after) == 1
    assert "newcall" in after[0].reasons[0].matched_terms

    completion = bindings[claims["completion_condition"].id]
    assert len(completion) == 1
    assert completion[0].evidence_role == "verification"
    assert "testsuite" in completion[0].reasons[0].matched_terms

    uncertainty = claims["uncertainty"]
    diagnostic = next(
        item
        for item in brief.transformation_alignment.diagnostics
        if item.claim_id == uncertainty.id
    )
    assert diagnostic.state == "no_eligible_fact"


def test_alignment_is_serialized_but_carries_no_assessment_state() -> None:
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=_packet()))
    serialized = brief.to_dict()["transformation_alignment"]

    assert serialized["schema_version"] == "transformation_alignment.v1"
    assert serialized["bindings"]
    assert not any(
        key in binding
        for binding in serialized["bindings"]
        for key in ("status", "assessment", "conclusion", "selected")
    )


def test_alignment_validation_rejects_unknown_or_duplicate_truth() -> None:
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=_packet()))
    alignment = brief.transformation_alignment
    binding = alignment.bindings[0]

    with pytest.raises(ValueError, match="unknown identity"):
        replace(
            alignment,
            bindings=(replace(binding, evidence_id="E:missing"),),
            diagnostics=(),
        ).validate_consistency(
            brief.transformation_contract,
            brief.observed_transformation,
            brief.evidence_catalog,
        )
    with pytest.raises(ValueError, match="duplicate bindings"):
        TransformationAlignment(
            bindings=(binding, binding),
            diagnostics=alignment.diagnostics,
        ).validate_consistency(
            brief.transformation_contract,
            brief.observed_transformation,
            brief.evidence_catalog,
        )


def test_pipeline_builds_transformation_alignment_once(monkeypatch) -> None:
    import prismcode.pipeline as pipeline

    calls = 0
    real_build = pipeline.build_transformation_alignment

    def counting_build(contract, observed, catalog, structural_closure=None):
        nonlocal calls
        calls += 1
        return real_build(contract, observed, catalog, structural_closure)

    monkeypatch.setattr(
        pipeline,
        "build_transformation_alignment",
        counting_build,
    )

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=_packet()))

    assert calls == 1
    assert isinstance(brief.transformation_alignment, TransformationAlignment)


def test_phrase_alignment_requires_claim_and_evidence_corpus_distinctiveness() -> None:
    body = "## Change\n- Update common special behavior.\n"
    files = tuple(
        ChangedFile(
            base_path=f"src/{name}.py",
            head_path=f"src/{name}.py",
            patch=f"@@ -1 +1 @@\n-old common {text} behavior\n+new common {text} behavior\n",
        )
        for name, text in (
            ("target", "special"),
            ("first", "alpha"),
            ("second", "beta"),
            ("third", "gamma"),
        )
    )
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=10,
        title="Align one distinctive change",
        source_records=(
            SourceRecord(
                id="pr:10",
                kind="pull_request",
                repository="acme/widget",
                title="Align one distinctive change",
                body=body,
            ),
        ),
        changed_files=files,
    ).with_revision()

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    claim = brief.transformation_contract.claims[0]
    bindings = brief.transformation_alignment.by_claim_id()[claim.id]

    assert len(bindings) == 1
    assert bindings[0].association == "distinctive_phrase"
    assert bindings[0].reasons[0].matched_terms == ("special",)
