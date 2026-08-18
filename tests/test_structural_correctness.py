from __future__ import annotations

import json
from dataclasses import replace

import pytest

from repodelta.evaluation.structural_correctness import (
    ReferenceFileLabel,
    ReferenceFocusLabel,
    ObservedFile,
    ObservedFocus,
    ReferenceAuthority,
    StructuralCandidate,
    StructuralCoverageSnapshot,
    StructuralRelationCandidate,
    StructuralSeedCoverage,
    StructuralSymbolCandidate,
    StructuralCorrectnessLabels,
    StructuralCorrectnessObservation,
    StructuralCorrectnessPacket,
    StructuralSubject,
    verify_structural_correctness_labels,
    load_labels,
    prepare_structural_correctness_packet,
    prepare_structural_correctness_label_template,
    write_comparison_html,
    write_json_artifact,
)
from repodelta.cli import build_parser
from repodelta.model.contracts import (
    ChangedFile,
    EvidenceCatalog,
    EvidenceItem,
    ProjectionCandidateSet,
    ProjectionDiagnostic,
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
            "available",
            "codegraph",
            1,
            1,
            3,
            1,
            1,
            1,
            0,
            3,
            3,
            "",
            "available",
            1,
            1,
            3,
            "complete",
            (StructuralSeedCoverage("provider:a", "S:a", "complete"),),
        ),
    )


def _labels(packet: StructuralCorrectnessPacket) -> StructuralCorrectnessLabels:
    return StructuralCorrectnessLabels(
        packet_digest=packet.digest,
        files=(
            ReferenceFileLabel("F:a", "included", "changed"),
            ReferenceFileLabel("F:b", "included", "retained_bridge"),
            ReferenceFileLabel("F:c", "excluded"),
        ),
        focuses=(
            ReferenceFocusLabel(
                "R1",
                ("F:a",),
                ("F:b",),
                direct_node_ids=("S:a",),
                context_node_ids=("S:b",),
                relation_ids=("REL:1",),
            ),
            ReferenceFocusLabel("G1", unresolved=True),
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
            ObservedFocus(
                "R1",
                ("F:a", "F:c"),
                ("F:b",),
                ("REL:1",),
                "mapped",
                ("S:a", "S:c"),
                ("S:b",),
                ("REL:1",),
            ),
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


def test_structural_comparison_names_reference_authority_without_breaking_alias() -> None:
    parser = build_parser()
    current = parser.parse_args(
        [
            "compare-structural-correctness",
            "--labeling-packet",
            "packet.json",
            "--observation",
            "observation.json",
            "--reference-labels",
            "labels.json",
            "--output",
            "comparison.html",
        ]
    )
    legacy = parser.parse_args(
        [
            "compare-structural-correctness",
            "--labeling-packet",
            "packet.json",
            "--observation",
            "observation.json",
            "--human-labels",
            "labels.json",
            "--output",
            "comparison.html",
        ]
    )

    assert current.reference_labels == "labels.json"
    assert legacy.reference_labels == "labels.json"


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
        revision_side="head",
        operation="modified",
        role="revision_fact",
        changed=True,
        metadata={
            "symbol_id": "provider:a",
            "review_symbol_id": "symbol:a",
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
        projection_candidates=ProjectionCandidateSet(
            diagnostics=(
                ProjectionDiagnostic(
                    focus_statement_id="review",
                    slot="structural_path",
                    state="budget_truncated",
                    message="Traversal stopped at the bounded seed limit.",
                    affected_ids=("provider:a",),
                    scope="review",
                ),
            )
        ),
        overview=ReviewOverview(
            "open",
            "not_observed",
            1,
            StructuralCoverage(
                "available",
                provider="codegraph",
                hunk_count=1,
                mapped_hunk_count=1,
                symbol_count=1,
                seed_count=1,
                truncated_seed_count=1,
                requested_files=1,
                indexed_files=1,
            ),
        ),
    )

    packet = prepare_structural_correctness_packet(brief)
    serialized = json.dumps(packet, default=lambda value: value.__dict__)

    assert packet.symbols[0].qualified_name == "run"
    assert packet.relations[0].source_node_id == "F:a"
    assert packet.changed_surfaces[0].hunk_headers == ("@@ -1,2 +1,4 @@",)
    assert packet.coverage.seed_mapping_state == "complete"
    assert packet.coverage.seeds == (
        StructuralSeedCoverage("provider:a", "S:a", "truncated"),
    )
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
    assert "S:c" in html
    assert "Nodes and roles" in html
    assert "Exact relations" in html
    assert "Non-authoritative evaluation" in html
    assert "does not change assessment or mergeability" in html
    assert "proposed reference" in html
    assert "complete for admitted direct seeds" in html


def test_comparison_exposes_observed_unresolved_membership_separately(
    tmp_path,
) -> None:
    packet = _packet()
    labels = _labels(packet)
    observation = _observation(packet)
    observation = replace(
        observation,
        focuses=(
            observation.focuses[0],
            replace(
                observation.focuses[1],
                unresolved_file_node_ids=("F:c",),
                unresolved_node_ids=("S:c",),
            ),
        ),
    )
    packet_path = write_json_artifact(packet, tmp_path / "packet.json")
    observation_path = write_json_artifact(
        observation, tmp_path / "observation.json"
    )
    labels_path = write_json_artifact(labels, tmp_path / "labels.json")

    html = write_comparison_html(
        packet_path, observation_path, labels_path, tmp_path / "comparison.html"
    ).read_text()

    assert "<b>Unresolved</b>" in html
    assert "F:c" in html
    assert "S:c" in html


def test_independent_verification_binds_the_exact_proposed_decision() -> None:
    proposed = _labels(_packet())
    verified = verify_structural_correctness_labels(
        proposed,
        verified_by="independent-review-agent",
        verification_method="source-and-relation counterexample review",
        verification_evidence=("evidence://source-review/1",),
        system_under_test_isolated=True,
    )

    assert verified.authority.status == "verified"

    with pytest.raises(ValueError, match="exact proposed decision"):
        replace(
            proposed,
            authority=ReferenceAuthority(
                status="verified",
                proposed_by="other-proposer",
                verified_by="independent-review-agent",
                verification_method="source review",
                verification_evidence=("evidence://source-review/1",),
                system_under_test_isolated=True,
                proposal_digest=proposed.proposal_digest,
            ),
        )


def test_verification_requires_evidence_and_system_isolation() -> None:
    proposed = _labels(_packet())

    with pytest.raises(ValueError, match="independently bind"):
        verify_structural_correctness_labels(
            proposed,
            verified_by="review-agent",
            verification_method="source review",
            verification_evidence=(),
            system_under_test_isolated=True,
        )
    with pytest.raises(ValueError, match="independently bind"):
        verify_structural_correctness_labels(
            proposed,
            verified_by="review-agent",
            verification_method="source review",
            verification_evidence=("evidence://source-review/1",),
            system_under_test_isolated=False,
        )


def test_coverage_rejects_inconsistent_and_unknown_seed_identity() -> None:
    packet = _packet()
    with pytest.raises(ValueError, match="disposed seed coverage"):
        replace(
            packet.coverage,
            seed_count=0,
        )
    with pytest.raises(ValueError, match="unknown seed node"):
        replace(
            packet,
            coverage=replace(
                packet.coverage,
                seeds=(
                    StructuralSeedCoverage(
                        "provider:unknown", "S:unknown", "complete"
                    ),
                ),
            ),
        )


def test_focus_coverage_does_not_apply_review_wide_truncation_to_empty_focus(
    tmp_path,
) -> None:
    packet = _packet()
    packet = replace(
        packet,
        coverage=replace(
            packet.coverage,
            seed_count=2,
            complete_seed_count=1,
            truncated_seed_count=1,
            seeds=(
                StructuralSeedCoverage("provider:a", "S:a", "truncated"),
                StructuralSeedCoverage("provider:c", "S:c", "complete"),
            ),
        ),
    )
    labels = replace(
        _labels(packet),
        focuses=(
            _labels(packet).focuses[0],
            replace(_labels(packet).focuses[1], unresolved=False),
        ),
    )
    packet_path = write_json_artifact(packet, tmp_path / "packet.json")
    labels_path = write_json_artifact(labels, tmp_path / "labels.json")
    observation_path = write_json_artifact(
        _observation(packet), tmp_path / "observation.json"
    )

    html = write_comparison_html(
        packet_path, observation_path, labels_path, tmp_path / "comparison.html"
    ).read_text()

    assert "limited · admitted seed truncated" in html
    assert "not required for empty reference" in html

    complete_focus_labels = replace(
        labels,
        focuses=(
            replace(
                labels.focuses[0],
                direct_file_node_ids=("F:c",),
                context_file_node_ids=(),
                direct_node_ids=("S:c",),
                context_node_ids=(),
                relation_ids=(),
            ),
            labels.focuses[1],
        ),
    )
    write_json_artifact(complete_focus_labels, labels_path)
    complete_html = write_comparison_html(
        packet_path,
        observation_path,
        labels_path,
        tmp_path / "complete-comparison.html",
    ).read_text()

    assert "complete for admitted direct seeds" in complete_html


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


def test_labels_reject_unknown_focus_node_and_relation(tmp_path) -> None:
    packet, _, _, labels_path = _write_inputs(tmp_path)
    raw = json.loads(labels_path.read_text())
    raw["focuses"][0]["direct_node_ids"] = ["S:unknown"]
    labels_path.write_text(json.dumps(raw))

    with pytest.raises(ValueError, match="unknown candidate nodes"):
        load_labels(labels_path, packet)

    raw = json.loads(write_json_artifact(_labels(packet), labels_path).read_text())
    raw["focuses"][0]["relation_ids"] = ["REL:unknown"]
    labels_path.write_text(json.dumps(raw))

    with pytest.raises(ValueError, match="unknown candidate relations"):
        load_labels(labels_path, packet)


def test_comparison_does_not_hide_node_role_or_relation_errors_behind_file_agreement(
    tmp_path,
) -> None:
    packet, packet_path, observation_path, labels_path = _write_inputs(tmp_path)
    observation = replace(
        _observation(packet),
        focuses=(
            ObservedFocus(
                "R1",
                ("F:a",),
                ("F:b",),
                ("REL:1",),
                "mapped",
                ("S:b",),
                ("S:a",),
                (),
            ),
            _observation(packet).focuses[1],
        ),
    )
    write_json_artifact(observation, observation_path)

    html = write_comparison_html(
        packet_path, observation_path, labels_path, tmp_path / "comparison.html"
    ).read_text()

    assert "S:a (context→direct)" in html
    assert "S:b (direct→context)" in html
    assert "false exclusion: REL:1" in html


def test_labels_reject_false_equivalent_projection_claim(tmp_path) -> None:
    packet, _, _, labels_path = _write_inputs(tmp_path)
    raw = json.loads(labels_path.read_text())
    raw["focuses"][0]["equivalent_to"] = ["G1"]
    labels_path.write_text(json.dumps(raw))

    with pytest.raises(ValueError, match="equal reference memberships"):
        load_labels(labels_path, packet)


def test_labels_reject_exact_relation_without_both_reference_endpoints(
    tmp_path,
) -> None:
    packet = _packet()
    labels = _labels(packet)
    invalid = replace(
        labels,
        focuses=(
            replace(labels.focuses[0], context_node_ids=()),
            labels.focuses[1],
        ),
    )
    labels_path = write_json_artifact(invalid, tmp_path / "labels.json")

    with pytest.raises(ValueError, match="both reference endpoints"):
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
