from __future__ import annotations

from dataclasses import replace

import pytest

from repodelta.evaluation.focus_provenance import (
    ProducerCounterfactualReport,
    StructuralFocusProvenanceObservation,
    ProvenanceFocus,
    load_focus_provenance,
    replay_producer_counterfactual,
    write_provenance_json,
)
from repodelta.evaluation.structural_correctness import (
    ObservedFocus,
    ReferenceFocusLabel,
    StructuralSubject,
)
from repodelta.model.contracts import (
    StructuralFocusMembership,
    StructuralFocusProvenance,
)

from test_structural_correctness import _labels, _observation, _packet


def _provenance(packet):
    return StructuralFocusProvenanceObservation(
        packet_digest=packet.digest,
        focuses=(
            ProvenanceFocus(
                "R1",
                (
                    StructuralFocusMembership(
                        "node",
                        "S:a",
                        "asserted",
                        "changed_anchor",
                        (
                            StructuralFocusProvenance(
                                "exact_identifier",
                                "asserted",
                                ("S:a",),
                            ),
                        ),
                    ),
                    StructuralFocusMembership(
                        "node",
                        "S:b",
                        "context",
                        "runtime_context",
                        (
                            StructuralFocusProvenance(
                                "structural_path",
                                "context",
                                ("S:a", "S:b"),
                            ),
                        ),
                    ),
                    StructuralFocusMembership(
                        "relation_group",
                        "REL:1",
                        "context",
                        "relation_endpoint",
                        (
                            StructuralFocusProvenance(
                                "relation_endpoint",
                                "context",
                                ("REL:1",),
                            ),
                        ),
                    ),
                ),
            ),
            ProvenanceFocus("G1"),
        ),
    )


def _tcc_inputs(packet):
    packet = replace(
        packet,
        subjects=packet.subjects
        + (
            StructuralSubject("T1", "transformation", "Route the change."),
            StructuralSubject("CC1", "completion_condition", "Keep it tested."),
        ),
    )
    source_observation = _observation(_packet())
    base_observation = replace(
        source_observation,
        focuses=(
            replace(
                source_observation.focuses[0],
                direct_node_ids=("S:a",),
                context_node_ids=("S:b",),
                exact_relation_ids=("REL:1",),
            ),
            source_observation.focuses[1],
        ),
    )
    observation = replace(
        base_observation,
        packet_digest=packet.digest,
        focuses=base_observation.focuses
        + (
            ObservedFocus(
                "T1",
                (),
                (),
                ("REL:1",),
                "mapped",
                ("S:a",),
                ("S:b",),
                ("REL:1",),
                (),
                (),
                ("S:c",),
                (),
            ),
            ObservedFocus(
                "CC1",
                (),
                (),
                (),
                "mapped",
                (),
                (),
                (),
                (),
                (),
                (),
                ("S:c",),
            ),
        ),
    )
    labels = replace(
        _labels(_packet()),
        packet_digest=packet.digest,
        focuses=_labels(_packet()).focuses
        + (
            ReferenceFocusLabel(
                "T1",
                direct_node_ids=("S:a",),
                context_node_ids=("S:b",),
                relation_ids=("REL:1",),
            ),
            ReferenceFocusLabel("CC1", unresolved=True),
        ),
    )
    provenance = replace(
        _provenance(_packet()),
        packet_digest=packet.digest,
        focuses=_provenance(_packet()).focuses
        + (
            ProvenanceFocus(
                "T1",
                (
                    StructuralFocusMembership(
                        "node", "S:a", "matched", "changed_anchor",
                        (
                            StructuralFocusProvenance(
                                "transformation_selector", "matched", ("S:a",)
                            ),
                        ),
                    ),
                    StructuralFocusMembership(
                        "node", "S:b", "context", "runtime_context",
                        (StructuralFocusProvenance("structural_path", "context", ("S:a", "S:b")),),
                    ),
                    StructuralFocusMembership(
                        "node", "S:c", "suggested", "changed_anchor",
                        (
                            StructuralFocusProvenance(
                                "transformation_selector", "suggested", ("S:c",)
                            ),
                        ),
                    ),
                    StructuralFocusMembership(
                        "relation_group", "REL:1", "context", "relation_endpoint",
                        (StructuralFocusProvenance("relation_endpoint", "context", ("REL:1",)),),
                    ),
                ),
            ),
            ProvenanceFocus(
                "CC1",
                (
                    StructuralFocusMembership(
                        "node", "S:c", "unresolved", "unresolved",
                        (StructuralFocusProvenance("coverage", "unresolved", ("S:c",)),),
                    ),
                ),
            ),
        ),
    )
    return packet, observation, labels, provenance


def test_provenance_round_trip_preserves_membership_classes(tmp_path) -> None:
    packet = _packet()
    value = _provenance(packet)

    path = write_provenance_json(value, tmp_path / "provenance.json")
    loaded = load_focus_provenance(path)

    assert loaded == value
    assert loaded.focuses[0].memberships[0].membership_class == "asserted"
    assert loaded.focuses[0].memberships[1].membership_class == "context"


def test_counterfactual_replays_recorded_producer_contribution_only() -> None:
    packet = _packet()
    observation = replace(
        _observation(packet),
        focuses=(
            replace(
                _observation(packet).focuses[0],
                direct_node_ids=("S:a",),
                context_node_ids=("S:b",),
                exact_relation_ids=("REL:1",),
            ),
            _observation(packet).focuses[1],
        ),
    )
    report = replay_producer_counterfactual(
        packet,
        observation,
        _provenance(packet),
        _labels(packet),
        disabled_producers=("structural_path",),
    )

    assert isinstance(report, ProducerCounterfactualReport)
    requirement = next(
        item for item in report.outcomes if item.subject_kind == "requirement"
    )
    assert requirement.memberships_removed == 1
    assert requirement.node_false_exclusions == 1
    assert requirement.relation_false_exclusions == 0
    assert requirement.node_false_inclusions == 0


def test_counterfactual_fails_closed_when_sidecar_buckets_differ() -> None:
    packet = _packet()
    observation = replace(
        _observation(packet),
        focuses=(
            replace(_observation(packet).focuses[0], direct_node_ids=("S:b",)),
            _observation(packet).focuses[1],
        ),
    )

    with pytest.raises(ValueError, match="buckets diverge"):
        replay_producer_counterfactual(
            packet,
            observation,
            _provenance(packet),
            _labels(packet),
            disabled_producers=(),
        )


def test_routing_preserves_tcc_and_unresolved_provenance() -> None:
    packet, observation, labels, provenance = _tcc_inputs(_packet())

    report = replay_producer_counterfactual(
        packet,
        observation,
        provenance,
        labels,
        disabled_producers=(),
    )

    assert {item.subject_kind for item in report.outcomes} == {
        "requirement",
        "guardrail",
        "transformation",
        "completion_condition",
    }
    assert any(
        membership.membership_class == "suggested"
        for focus in provenance.focuses
        for membership in focus.memberships
    )
    assert any(
        membership.membership_class == "unresolved"
        for focus in provenance.focuses
        for membership in focus.memberships
    )


def test_loading_rejects_empty_source_identity(tmp_path) -> None:
    packet = _packet()
    path = tmp_path / "invalid.json"
    path.write_text(
        '{"schema_version":"structural_focus_provenance_observation.v1",'
        f'"packet_digest":"{packet.digest}","focuses":[{{"subject_id":"R1",'
        '"memberships":[{"member_kind":"node","member_id":"S:a",'
        '"membership_class":"asserted","structural_role":"changed_anchor",'
        '"provenance":[{"producer":"x","admission_class":"asserted",'
        '"source_ids":[]}]}]} ,{"subject_id":"G1","memberships":[]}]}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="requires producer sources"):
        load_focus_provenance(path)


def test_replay_rejects_unknown_canonical_member_identity() -> None:
    packet = _packet()
    value = _provenance(packet)
    unknown_node = StructuralFocusMembership(
        "node",
        "S:unknown",
        "context",
        "runtime_context",
        (StructuralFocusProvenance("structural_path", "context", ("S:unknown",)),),
    )
    invalid = replace(
        value,
        focuses=(
            replace(
                value.focuses[0],
                memberships=value.focuses[0].memberships + (unknown_node,),
            ),
            value.focuses[1],
        ),
    )

    with pytest.raises(ValueError, match="unknown node"):
        replay_producer_counterfactual(
            packet,
            replace(
                _observation(packet),
                focuses=(
                    replace(
                        _observation(packet).focuses[0],
                        direct_node_ids=("S:a",),
                        context_node_ids=("S:b",),
                        exact_relation_ids=("REL:1",),
                    ),
                    _observation(packet).focuses[1],
                ),
            ),
            invalid,
            _labels(packet),
            disabled_producers=(),
        )


def test_duplicate_membership_is_rejected() -> None:
    packet = _packet()
    membership = _provenance(packet).focuses[0].memberships[0]

    with pytest.raises(ValueError, match="duplicate memberships"):
        ProvenanceFocus("R1", (membership, membership))
