from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

from prismcode.cli import main
from prismcode.evaluation.comparison import (
    load_shadow_comparison_inputs,
    write_shadow_comparison_html,
)
from prismcode.llm import (
    ShadowCandidateAdmission,
    ShadowLabelingPacket,
    load_shadow_execution,
    write_shadow_execution,
    write_shadow_labeling_packet,
)


CORPUS = Path("fixtures/llm-shadow/campaign-v1")
EXECUTION = CORPUS / "pr-203.observation.json"
LABELS = CORPUS / "pr-203.human-labels.json"


def _packet() -> ShadowLabelingPacket:
    bundle = load_shadow_execution(EXECUTION)
    return ShadowLabelingPacket(
        repository="prismcode-ai/prismcode",
        pull_request=203,
        head_sha="head203",
        base_sha="base203",
        admissions=tuple(
            ShadowCandidateAdmission(
                claim_id=item.claim_id,
                state=item.admission_state,
                eligible_count=item.eligible_count,
                deterministic_evidence_ids=item.deterministic_evidence_ids,
                request=item.request,
                diagnostics=item.diagnostics,
            )
            for item in bundle.observations
        ),
    )


def test_comparison_html_is_stable_and_exposes_semantic_recovery(
    tmp_path: Path,
) -> None:
    packet = write_shadow_labeling_packet(_packet(), tmp_path / "packet.json")
    first = write_shadow_comparison_html(
        packet,
        EXECUTION,
        LABELS,
        tmp_path / "first.html",
    )
    second = write_shadow_comparison_html(
        packet,
        EXECUTION,
        LABELS,
        tmp_path / "second.html",
    )

    html = first.read_text(encoding="utf-8")
    assert first.read_bytes() == second.read_bytes()
    assert "Non-authoritative evaluation" in html
    assert "LLM shadow comparison" in html
    assert "llm-only" in html
    assert "selection precision" in html
    assert "1.0000" in html
    assert "documentation" in html
    assert "E:change_relation:" in html
    assert "does not change PrismCode assessment or mergeability" in html


def test_comparison_rejects_execution_that_did_not_use_frozen_admission(
    tmp_path: Path,
) -> None:
    packet = _packet()
    first = packet.admissions[0]
    assert first.request is not None
    drifted = replace(
        packet,
        admissions=(
            replace(
                first,
                deterministic_evidence_ids=(
                    first.request.candidates[0].evidence_id,
                ),
            ),
            *packet.admissions[1:],
        ),
    )
    packet_path = write_shadow_labeling_packet(
        drifted,
        tmp_path / "drifted-packet.json",
    )

    with pytest.raises(ValueError, match="does not match frozen"):
        load_shadow_comparison_inputs(packet_path, EXECUTION, LABELS)


def test_compare_shadow_cli_renders_offline_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = write_shadow_labeling_packet(_packet(), tmp_path / "packet.json")
    output = tmp_path / "comparison.html"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prismcode",
            "compare-shadow",
            "--labeling-packet",
            str(packet),
            "--execution",
            str(EXECUTION),
            "--human-labels",
            str(LABELS),
            "--output",
            str(output),
        ],
    )

    assert main() == 0
    assert output.exists()


def test_comparison_does_not_report_empty_accepted_metrics_as_perfect(
    tmp_path: Path,
) -> None:
    bundle = load_shadow_execution(EXECUTION)
    failed_bundle = replace(
        bundle,
        summary=replace(
            bundle.summary,
            state="failed",
            completed_count=0,
            failed_count=2,
        ),
        observations=tuple(
            replace(
                item,
                execution_state="provider_error",
                run=replace(
                    item.run,
                    state="provider_error",
                    selection=None,
                    comparison=None,
                ),
            )
            for item in bundle.observations
        ),
    )
    execution = tmp_path / "failed-execution.json"
    write_shadow_execution(failed_bundle, execution)
    packet = write_shadow_labeling_packet(_packet(), tmp_path / "packet.json")

    output = write_shadow_comparison_html(
        packet,
        execution,
        LABELS,
        tmp_path / "comparison.html",
    )

    html = output.read_text(encoding="utf-8")
    accepted = html.split("<h2>Accepted labeled requests</h2>", 1)[1].split(
        "</section>", 1
    )[0]
    assert "n/a" in accepted
    assert "1.0000" not in accepted
