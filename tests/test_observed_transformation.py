from __future__ import annotations

from dataclasses import replace

import pytest

from prismcode.changes.hunks import parse_changed_files
from prismcode.facts.catalog import build_evidence_catalog
from prismcode.facts.transformation import reconstruct_observed_transformation
from prismcode.model.contracts import (
    AnalysisInput,
    ChangedFile,
    ObservedTransformation,
    ReviewSourcePacket,
    SourceRecord,
    VerificationObservation,
)
from prismcode.pipeline import DeterministicAnalyzer


def _packet(pr_body: str) -> ReviewSourcePacket:
    return ReviewSourcePacket(
        repository="acme/widget",
        pull_request=8,
        title="Reconstruct observed state",
        source_records=(
            SourceRecord(
                id="pr:8",
                kind="pull_request",
                repository="acme/widget",
                url="https://github.com/acme/widget/pull/8",
                title="Reconstruct observed state",
                body=pr_body,
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
                id="check:test",
                name="test",
                kind="check_run",
                status="completed",
                conclusion="success",
                head_sha="head123",
            ),
        ),
        source_url="https://github.com/acme/widget/pull/8",
        head_sha="head123",
    ).with_revision()


def test_observed_transformation_references_canonical_fallback_and_verification() -> None:
    packet = _packet("## Change\n- Replace the service call.\n")
    catalog = build_evidence_catalog(
        packet,
        parse_changed_files(packet.changed_files),
    )

    observed = reconstruct_observed_transformation(catalog)

    assert observed.structural_change_evidence_ids == ()
    assert len(observed.fallback_change_evidence_ids) == 1
    assert observed.relation_change_evidence_ids == ()
    assert observed.ownership_change_evidence_ids == ()
    assert observed.structural_path_evidence_ids == ()
    assert len(observed.verification_evidence_ids) == 1
    assert observed.topology.base_symbol_change_evidence_ids == ()
    assert observed.topology.head_symbol_change_evidence_ids == ()


def test_observed_reconstruction_is_independent_of_authored_contract() -> None:
    first = DeterministicAnalyzer().analyze(
        AnalysisInput(
            packet=_packet(
                "## Change\n- Replace the service call.\n\n"
                "## Canonical authority\n- Service owns the call.\n"
            )
        )
    )
    second = DeterministicAnalyzer().analyze(
        AnalysisInput(
            packet=_packet(
                "## Change\n- A completely different authored claim.\n\n"
                "## Completion conditions\n- Everything is migrated.\n"
            )
        )
    )

    assert first.transformation_contract != second.transformation_contract
    assert first.observed_transformation == second.observed_transformation
    assert first.to_dict()["observed_transformation"] == (
        second.to_dict()["observed_transformation"]
    )


def test_observed_transformation_rejects_a_missing_canonical_lane_member() -> None:
    packet = _packet("")
    catalog = build_evidence_catalog(
        packet,
        parse_changed_files(packet.changed_files),
    )
    observed = reconstruct_observed_transformation(catalog)

    with pytest.raises(ValueError, match="fallback_change_evidence_ids"):
        replace(observed, fallback_change_evidence_ids=()).validate_consistency(
            catalog
        )


def test_pipeline_reconstructs_observed_state_once(monkeypatch) -> None:
    import prismcode.pipeline as pipeline

    calls = 0
    real_reconstruct = pipeline.reconstruct_observed_transformation

    def counting_reconstruct(catalog):
        nonlocal calls
        calls += 1
        return real_reconstruct(catalog)

    monkeypatch.setattr(
        pipeline,
        "reconstruct_observed_transformation",
        counting_reconstruct,
    )
    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=_packet("")))

    assert calls == 1
    assert isinstance(brief.observed_transformation, ObservedTransformation)
