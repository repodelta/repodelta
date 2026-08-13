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
    StructuralRelationCandidate,
    StructuralSymbolCandidate,
    StructuralCorrectnessLabels,
    StructuralCorrectnessObservation,
    StructuralCorrectnessPacket,
    StructuralCoverageSnapshot,
    StructuralSubject,
    load_labels,
    prepare_structural_correctness_packet,
    prepare_structural_correctness_label_template,
    write_comparison_html,
    write_json_artifact,
)
from repodelta.model.contracts import (
    ChangedFile,
    EvidenceCatalog,
    EvidenceItem,
    ReviewBrief,
    ReviewOverview,
    ReviewProjection,
    ReviewSourcePacket,
    ReviewStatement,
    ReviewStructuralGraph,
    StructuralCoverage,
    StructuralGraphEdge,
    StructuralGraphNode,
    StructuralRelationGroup,
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
        symbols=(
            StructuralSymbolCandidate(
                "S:a", "F:a", "src/a.py", "run", "function", "modified"
            ),
            StructuralSymbolCandidate(
                "S:b", "F:b", "src/b.py", "bridge", "function", "retained"
            ),
            StructuralSymbolCandidate(
                "S:c", "F:c", "src/c.py", "other", "function", "modified"
            ),
        ),
        relations=(
            StructuralRelationCandidate(
                "REL:1", "S:a", "S:b", "calls", "retained"
            ),
        ),
        changed_surfaces=(),
        subjects=(
            StructuralSubject("R1", "requirement", "Keep the path continuous."),
            StructuralSubject("G1", "guardrail", "Do not change c."),
        ),
        relation_ids=("REL:1",),
        coverage=StructuralCoverageSnapshot(
            "available", "codegraph", 3, 3, 3, 2, 2, 1, 1, 3, 3, "",
            "available", 2, 2, 2,
        ),
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
    serialized = json.dumps(packet, default=lambda value: value.__dict__)
    assert "retained_bridge" not in serialized
    assert '"source_node_id": "S:a"' in serialized
    assert '"qualified_name": "run"' in serialized
    assert packet.coverage.complete_seed_count == 1


def test_packet_exposes_bounded_structural_facts_without_projected_answers() -> None:
    file_fact = EvidenceItem(
        id="EV:file",
        summary="src/a.py",
        kind="symbol",
        classification="code",
        metadata={
            "path": "src/a.py",
            "qualified_name": "src/a.py",
            "symbol_kind": "file",
        },
    )
    symbol_fact = EvidenceItem(
        id="EV:symbol",
        summary="run",
        kind="symbol",
        classification="code",
        metadata={
            "path": "src/a.py",
            "qualified_name": "run",
            "symbol_kind": "function",
        },
    )
    file_node = StructuralGraphNode(
        "F:a", "file:a", "modified", ("EV:file",), "EV:file"
    )
    symbol_node = StructuralGraphNode(
        "S:a", "symbol:a", "modified", ("EV:symbol",), "EV:symbol"
    )
    edge = StructuralGraphEdge(
        "E:1", "F:a", "S:a", "contains", "added", "EV:relation"
    )
    relation = StructuralRelationGroup(
        "REL:1", "F:a", "S:a", "contains", "added", ("E:1",)
    )
    source_packet = ReviewSourcePacket(
        repository="repodelta/repodelta",
        pull_request=1,
        title="Change run",
        source_records=(),
        changed_files=(
            ChangedFile(
                "src/a.py",
                "src/a.py",
                additions=3,
                deletions=1,
                patch="@@ -1,2 +1,4 @@\n-secret implementation line\n",
            ),
        ),
        base_sha="base",
        head_sha="head",
    )
    brief = ReviewBrief(
        packet=source_packet,
        intent=ReviewStatement("O1", "Change run"),
        requirements=(),
        evidence_catalog=EvidenceCatalog((file_fact, symbol_fact)),
        projection=ReviewProjection(
            review_graph=ReviewStructuralGraph(
                nodes=(file_node, symbol_node),
                edges=(edge,),
                relation_groups=(relation,),
            )
        ),
        overview=ReviewOverview(
            "open", "not_observed", 1, StructuralCoverage("available")
        ),
    )

    packet = prepare_structural_correctness_packet(brief)
    serialized = json.dumps(packet, default=lambda value: value.__dict__)

    assert packet.symbols[0].qualified_name == "run"
    assert packet.relations[0].source_node_id == "F:a"
    assert packet.changed_surfaces[0].hunk_headers == ("@@ -1,2 +1,4 @@",)
    assert packet.coverage.mapped_hunk_count == 0
    assert "secret implementation line" not in serialized
    assert "direct_file_node_ids" not in serialized
    assert "retained_bridge" not in serialized


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
    assert "Packet-bound reference labels" in html
    assert "campaign record owns whether those labels are proposed" in html


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
