from __future__ import annotations

import json
from dataclasses import replace

import pytest

from repodelta.evaluation.structural_correctness import (
    HumanFileLabel,
    HumanFocusLabel,
    ObservedFile,
    ObservedFocus,
    StructuralCandidate,
    StructuralCorrectnessLabels,
    StructuralCorrectnessObservation,
    StructuralCorrectnessPacket,
    StructuralSubject,
    load_labels,
    prepare_structural_correctness_label_template,
    write_comparison_html,
    write_json_artifact,
)


def _packet() -> StructuralCorrectnessPacket:
    return StructuralCorrectnessPacket(
        repository="repodelta/repodelta",
        pull_request=267,
        base_sha="base",
        head_sha="head",
        candidates=(
            StructuralCandidate("F:a", "src/a.py", "modified", ("S:a",)),
            StructuralCandidate("F:b", "src/b.py", "retained", ("S:b",)),
            StructuralCandidate("F:c", "src/c.py", "modified", ("S:c",)),
        ),
        subjects=(
            StructuralSubject("R1", "requirement", "Keep the path continuous."),
            StructuralSubject("G1", "guardrail", "Do not change c."),
        ),
        relation_ids=("REL:1",),
        coverage_state="available",
    )


def _labels(packet: StructuralCorrectnessPacket) -> StructuralCorrectnessLabels:
    return StructuralCorrectnessLabels(
        packet_digest=packet.digest,
        files=(
            HumanFileLabel("F:a", "included", "changed"),
            HumanFileLabel("F:b", "included", "retained_bridge"),
            HumanFileLabel("F:c", "excluded"),
        ),
        focuses=(
            HumanFocusLabel("R1", ("F:a",), ("F:b",)),
            HumanFocusLabel("G1", unresolved=True),
        ),
    )


def _observation(packet: StructuralCorrectnessPacket):
    return StructuralCorrectnessObservation(
        packet_digest=packet.digest,
        files=(
            ObservedFile("F:a", "changed"),
            ObservedFile("F:b", "retained_context"),
            ObservedFile("F:c", "changed"),
        ),
        focuses=(
            ObservedFocus("R1", ("F:a", "F:c"), ("F:b",), ("REL:1",), "mapped"),
            ObservedFocus("G1", (), (), (), "not_applicable"),
        ),
    )


def _write_inputs(tmp_path):
    packet = _packet()
    packet_path = write_json_artifact(packet, tmp_path / "packet.json")
    observation_path = write_json_artifact(
        _observation(packet), tmp_path / "observation.json"
    )
    labels_path = write_json_artifact(_labels(packet), tmp_path / "labels.json")
    return packet, packet_path, observation_path, labels_path


def test_label_template_is_complete_but_blind() -> None:
    packet = _packet()
    template = prepare_structural_correctness_label_template(packet)

    assert {item.disposition for item in template.files} == {"unresolved"}
    assert all(item.unresolved for item in template.focuses)
    assert "retained_bridge" not in json.dumps(packet, default=lambda value: value.__dict__)


def test_comparison_exposes_false_inclusion_role_disagreement_and_focus_error(
    tmp_path,
) -> None:
    _, packet_path, observation_path, labels_path = _write_inputs(tmp_path)

    output = write_comparison_html(
        packet_path, observation_path, labels_path, tmp_path / "comparison.html"
    )
    html = output.read_text()

    assert "role disagreement" in html
    assert "false inclusion" in html
    assert "F:c" in html
    assert "Non-authoritative evaluation" in html
    assert "does not change assessment or mergeability" in html


def test_labels_reject_stale_packet_identity(tmp_path) -> None:
    packet, _, _, labels_path = _write_inputs(tmp_path)
    raw = json.loads(labels_path.read_text())
    raw["packet_digest"] = "stale"
    labels_path.write_text(json.dumps(raw))

    with pytest.raises(ValueError, match="do not match frozen packet"):
        load_labels(labels_path, packet)


def test_labels_reject_incomplete_candidate_dispositions(tmp_path) -> None:
    packet, _, _, labels_path = _write_inputs(tmp_path)
    raw = json.loads(labels_path.read_text())
    raw["files"].pop()
    labels_path.write_text(json.dumps(raw))

    with pytest.raises(ValueError, match="dispose every candidate"):
        load_labels(labels_path, packet)


def test_labels_reject_unknown_subject_and_file(tmp_path) -> None:
    packet, _, _, labels_path = _write_inputs(tmp_path)
    raw = json.loads(labels_path.read_text())
    raw["focuses"][0]["direct_file_node_ids"] = ["F:unknown"]
    labels_path.write_text(json.dumps(raw))

    with pytest.raises(ValueError, match="unknown candidate"):
        load_labels(labels_path, packet)


def test_labels_reject_false_equivalent_projection_claim(tmp_path) -> None:
    packet, _, _, labels_path = _write_inputs(tmp_path)
    raw = json.loads(labels_path.read_text())
    raw["focuses"][0]["equivalent_to"] = ["G1"]
    labels_path.write_text(json.dumps(raw))

    with pytest.raises(ValueError, match="equal human memberships"):
        load_labels(labels_path, packet)


def test_comparison_rejects_observation_for_another_packet(tmp_path) -> None:
    packet, packet_path, observation_path, labels_path = _write_inputs(tmp_path)
    observation = replace(_observation(packet), packet_digest="other")
    write_json_artifact(observation, observation_path)

    with pytest.raises(ValueError, match="does not match frozen packet"):
        write_comparison_html(
            packet_path, observation_path, labels_path, tmp_path / "comparison.html"
        )


def test_comparison_rejects_structurally_incompatible_observation(tmp_path) -> None:
    packet, packet_path, observation_path, labels_path = _write_inputs(tmp_path)
    observation = replace(
        _observation(packet),
        focuses=(
            replace(_observation(packet).focuses[0], relation_ids=("REL:unknown",)),
            _observation(packet).focuses[1],
        ),
    )
    write_json_artifact(observation, observation_path)

    with pytest.raises(ValueError, match="unknown relations"):
        write_comparison_html(
            packet_path, observation_path, labels_path, tmp_path / "comparison.html"
        )
