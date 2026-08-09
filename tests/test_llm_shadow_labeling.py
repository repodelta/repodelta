from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from prismcode.evaluation.shadow import load_human_shadow_labels_from_packet
from prismcode.llm import (
    ShadowCandidateAdmission,
    ShadowLabelingPacket,
    execute_shadow_admissions,
    load_shadow_labeling_packet,
    load_shadow_replay,
    load_shadow_replay_provider,
    write_shadow_labeling_packet,
)


REPLAY = Path("fixtures/llm-shadow/evidence-selection.json")


def _packet(*, second_request: bool = False) -> ShadowLabelingPacket:
    request, validation = load_shadow_replay(REPLAY)
    assert validation.accepted
    admissions = [
        ShadowCandidateAdmission(
            claim_id=request.subject_id,
            state="ready",
            eligible_count=len(request.candidates),
            deterministic_evidence_ids=(request.candidates[0].evidence_id,),
            request=request,
        )
    ]
    if second_request:
        second = replace(
            request,
            request_id="shadow:T2:second",
            subject_id="T2",
        )
        admissions.append(
            ShadowCandidateAdmission(
                claim_id="T2",
                state="ready",
                eligible_count=len(second.candidates),
                deterministic_evidence_ids=(second.candidates[0].evidence_id,),
                request=second,
            )
        )
    return ShadowLabelingPacket(
        repository="acme/widget",
        pull_request=12,
        head_sha="head123",
        base_sha="base123",
        admissions=tuple(admissions),
    )


def _write_labels(path: Path) -> Path:
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    path.write_text(
        json.dumps(
            {
                "schema_version": "llm_shadow_human_labels.v1",
                "authority": "human_review",
                "rubric_version": "shadow-evidence-disposition.v1",
                "labels": [
                    {"claim_id": "T1", "response": replay["response"]}
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_labeling_packet_round_trips_before_execution_and_reuses_admissions(
    tmp_path: Path,
) -> None:
    packet = _packet()
    first = write_shadow_labeling_packet(packet, tmp_path / "first.json")
    second = write_shadow_labeling_packet(packet, tmp_path / "second.json")

    loaded = load_shadow_labeling_packet(first)
    execution = execute_shadow_admissions(
        loaded.admission_set,
        load_shadow_replay_provider(REPLAY),
    )

    assert first.read_bytes() == second.read_bytes()
    assert loaded == packet
    assert execution.summary.state == "completed"
    assert execution.observations[0].request == loaded.admissions[0].request


def test_pre_execution_labels_validate_without_model_output(tmp_path: Path) -> None:
    packet = _packet()
    labels = load_human_shadow_labels_from_packet(
        _write_labels(tmp_path / "labels.json"),
        packet,
    )

    assert tuple(item.claim_id for item in labels.labels) == ("T1",)


def test_pre_execution_labels_must_cover_every_frozen_request(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="must cover every request; missing: T2"):
        load_human_shadow_labels_from_packet(
            _write_labels(tmp_path / "labels.json"),
            _packet(second_request=True),
        )


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            lambda raw: raw.update({"model_selection": {}}),
            "unsupported fields: model_selection",
        ),
        (
            lambda raw: raw["admissions"][0]["request"]["candidates"][0].update(
                {"model_rationale": "leak"}
            ),
            "unsupported fields: model_rationale",
        ),
        (
            lambda raw: raw["admissions"][0].update(
                {
                    "deterministic_evidence_ids": (
                        *raw["admissions"][0]["deterministic_evidence_ids"],
                        "invented:evidence",
                    )
                }
            ),
            "must be admitted candidates",
        ),
    ),
)
def test_labeling_packet_loading_rejects_tampered_or_model_shaped_fields(
    tmp_path: Path,
    mutate,
    message: str,
) -> None:
    raw = _packet().to_dict()
    mutate(raw)
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_shadow_labeling_packet(path)
