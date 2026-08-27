from __future__ import annotations

import json
from dataclasses import replace

import pytest

from repodelta.evaluation.focus_provenance import (
    ProducerCounterfactualReport,
    StructuralFocusProvenanceObservation,
    ProvenanceFocus,
    load_focus_provenance,
    observe_focus_provenance,
    replay_producer_counterfactual,
    write_provenance_json,
)
from repodelta.evaluation.association_attribution import (
    load_association_attribution,
    observe_association_attribution,
    write_association_attribution,
)
from repodelta.evaluation.structural_correctness import (
    OBSERVATION_SCHEMA,
    PREVIOUS_OBSERVATION_SCHEMA,
    ObservedFocus,
    ReferenceFocusLabel,
    StructuralSubject,
    observe_structural_correctness,
    prepare_structural_correctness_packet,
)
from repodelta.model.contracts import (
    AssociationReason,
    CandidateConvergence,
    ChangedFile,
    ConvergenceGroup,
    EvidenceCatalog,
    EvidenceItem,
    ReviewBrief,
    ReviewOverview,
    ReviewProjection,
    ReviewSourcePacket,
    ReviewStatement,
    ReviewStructuralGraph,
    StructuralCoverage,
    StructuralFocusDisposition,
    StructuralFocusMembership,
    StructuralFocusOverlay,
    StructuralFocusProvenance,
    StructuralGraphEdge,
    StructuralGraphNode,
    StructuralGraphOwnershipEdge,
    StructuralGraphPlacement,
    StructuralOverviewFile,
    StructuralOverviewFocus,
    StructuralOverviewProjection,
    StructuralRelationGroup,
    ProjectionCandidateGroup,
    ProjectionCandidateSet,
    ProjectionRelation,
    Requirement,
    VerificationEvidenceInspection,
    VerificationMatrixEntry,
    VerificationWorkspace,
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
                        "matched",
                        "changed_anchor",
                        (
                            StructuralFocusProvenance(
                                "requirement_association",
                                "matched",
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
            ProvenanceFocus(
                "G1",
                (
                    StructuralFocusMembership(
                        "node",
                        "S:c",
                        "suggested",
                        "changed_anchor",
                        (
                            StructuralFocusProvenance(
                                "requirement_association",
                                "suggested",
                                ("G1:S:c",),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def _aligned_observation(packet):
    source = _observation(packet)
    provenance = _provenance(packet)
    return replace(
        source,
        focuses=(
            replace(
                source.focuses[0],
                direct_node_ids=("S:a",),
                context_node_ids=("S:b",),
                exact_relation_ids=("REL:1",),
                canonical_membership_digest=(
                    provenance.focuses[0].canonical_membership_digest
                ),
            ),
            replace(
                source.focuses[1],
                suggested_node_ids=("S:c",),
                canonical_membership_digest=(
                    provenance.focuses[1].canonical_membership_digest
                ),
            ),
        ),
    )


def _tcc_inputs(packet):
    packet = replace(
        packet,
        subjects=packet.subjects
        + (
            StructuralSubject(
                "T1", "transformation_claim", "Route the change."
            ),
            StructuralSubject("CC1", "completion_condition", "Keep it tested."),
        ),
    )
    base_observation = _aligned_observation(_packet())
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
                (),
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
                        "node", "S:a", "asserted", "changed_anchor",
                        (
                            StructuralFocusProvenance(
                                "transformation_selector", "asserted", ("S:a",)
                            ),
                        ),
                    ),
                    StructuralFocusMembership(
                        "node", "S:b", "context", "runtime_context",
                        (StructuralFocusProvenance("structural_path", "context", ("S:a", "S:b")),),
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
    provenance_by_subject = {
        item.subject_id: item for item in provenance.focuses
    }
    observation = replace(
        observation,
        focuses=tuple(
            replace(
                focus,
                canonical_membership_digest=provenance_by_subject[
                    focus.subject_id
                ].canonical_membership_digest,
            )
            for focus in observation.focuses
        ),
    )
    return packet, observation, labels, provenance


def _production_brief() -> ReviewBrief:
    evidence = []
    for file_id, path in (("F:a", "src/a.py"), ("F:b", "src/b.py"), ("F:c", "src/c.py")):
        evidence.append(
            EvidenceItem(
                id=f"EV:{file_id}",
                summary=path,
                kind="symbol",
                classification="code",
                metadata={
                    "path": path,
                    "qualified_name": path,
                    "symbol_kind": "file",
                },
            )
        )
    for node_id, path, changed in (
        ("N:a", "src/a.py", True),
        ("N:b", "src/b.py", False),
        ("N:c", "src/c.py", True),
    ):
        evidence.append(
            EvidenceItem(
                id=f"EV:{node_id}",
                summary=node_id,
                kind="symbol",
                classification="code",
                revision_side="head",
                operation="modified" if changed else "observed",
                changed=changed,
                metadata={
                    "path": path,
                    "qualified_name": node_id,
                    "symbol_kind": "function",
                    "symbol_id": f"provider:{node_id}",
                    "review_symbol_id": node_id,
                },
            )
        )
    graph_nodes = tuple(
        StructuralGraphNode(
            file_id,
            file_id,
            "modified" if file_id != "F:b" else "retained",
            (f"EV:{file_id}",),
            f"EV:{file_id}",
        )
        for file_id in ("F:a", "F:b", "F:c")
    ) + tuple(
        StructuralGraphNode(
            node_id,
            node_id,
            "modified" if node_id != "N:b" else "retained",
            (f"EV:{node_id}",),
            f"EV:{node_id}",
        )
        for node_id in ("N:a", "N:b", "N:c")
    )
    edge = StructuralGraphEdge(
        "E:1", "N:a", "N:b", "calls", "retained", "EV:REL:1"
    )
    relation_group = StructuralRelationGroup(
        "REL:1", "N:a", "N:b", "calls", "retained", ("E:1",)
    )
    graph = ReviewStructuralGraph(
        nodes=graph_nodes,
        edges=(edge,),
        relation_groups=(relation_group,),
        ownership_edges=(
            StructuralGraphOwnershipEdge(
                "OWN:1", "N:b", "N:a", "added", "EV:OWN:1"
            ),
        ),
        placements=(
            StructuralGraphPlacement(
                "PLC:1", "N:b", "N:a", head_ownership_evidence_ids=("EV:PLC:1",)
            ),
        ),
    )

    def member(kind, identity, membership_class, role, producer, admission):
        return StructuralFocusMembership(
            kind,
            identity,
            membership_class,
            role,
            (StructuralFocusProvenance(producer, admission, (identity,)),),
        )

    workspace = VerificationWorkspace(
        matrix=tuple(
            VerificationMatrixEntry(
                f"VM:{subject_id}",
                subject_id,
                subject_kind,
                subject_id,
                "issue",
                "unverified",
                f"VEI:{subject_id}",
            )
            for subject_id, subject_kind in (
                ("R1", "requirement"),
                ("G1", "guardrail"),
                ("T1", "transformation_claim"),
                ("CC1", "completion_condition"),
            )
        ),
        inspections=(
            VerificationEvidenceInspection(
                "VEI:R1",
                "R1",
                structural_overlay=StructuralFocusOverlay(
                    memberships=(
                        member("node", "N:a", "matched", "changed_anchor", "requirement_association", "matched"),
                        member("node", "N:b", "context", "runtime_context", "structural_path", "context"),
                        member("edge", "E:1", "context", "relation_endpoint", "relation_endpoint", "context"),
                        member("relation_group", "REL:1", "context", "relation_endpoint", "relation_group", "context"),
                        member("ownership_edge", "OWN:1", "context", "ownership_ancestor", "ownership_ancestor", "context"),
                        member("placement", "PLC:1", "context", "placement_ancestor", "placement_ancestor", "context"),
                    )
                ),
                structural_disposition=StructuralFocusDisposition(state="projected"),
            ),
            VerificationEvidenceInspection(
                "VEI:G1",
                "G1",
                structural_overlay=StructuralFocusOverlay(
                    memberships=(
                        member("node", "N:b", "suggested", "changed_anchor", "requirement_association", "suggested"),
                    )
                ),
                structural_disposition=StructuralFocusDisposition(state="projected"),
            ),
            VerificationEvidenceInspection(
                "VEI:T1",
                "T1",
                structural_overlay=StructuralFocusOverlay(
                    memberships=(
                        member("node", "N:c", "asserted", "changed_anchor", "transformation_selector", "asserted"),
                    )
                ),
                structural_disposition=StructuralFocusDisposition(state="projected"),
            ),
            VerificationEvidenceInspection(
                "VEI:CC1",
                "CC1",
                structural_overlay=StructuralFocusOverlay(
                    memberships=(
                        member("node", "N:c", "unresolved", "unresolved", "unresolved", "unresolved"),
                    )
                ),
                structural_disposition=StructuralFocusDisposition(state="unavailable"),
            ),
        ),
    )
    overview = StructuralOverviewProjection(
        files=(
            StructuralOverviewFile("F:a", ("N:a",), "changed", "production", "unclassified"),
            StructuralOverviewFile("F:b", ("N:b",), "retained_bridge", "production", "unclassified"),
            StructuralOverviewFile("F:c", ("N:c",), "changed", "production", "unclassified"),
        ),
        focuses=(
            StructuralOverviewFocus("R1", ("F:a",), context_file_node_ids=("F:b",), relation_ids=("REL:1",), structural_disposition=StructuralFocusDisposition(state="projected")),
            StructuralOverviewFocus("G1", suggested_file_node_ids=("F:b",), structural_disposition=StructuralFocusDisposition(state="projected")),
            StructuralOverviewFocus("T1", ("F:c",), structural_disposition=StructuralFocusDisposition(state="projected")),
            StructuralOverviewFocus("CC1", unresolved_file_node_ids=("F:c",), structural_disposition=StructuralFocusDisposition(state="unavailable")),
        ),
    )
    packet = ReviewSourcePacket(
        repository="repodelta/repodelta",
        pull_request=295,
        title="Provenance",
        source_records=(),
        changed_files=(
            ChangedFile("src/a.py", "src/a.py", additions=1, deletions=0, patch="@@ -1 +1 @@"),
            ChangedFile("src/b.py", "src/b.py", additions=0, deletions=0, patch=""),
            ChangedFile("src/c.py", "src/c.py", additions=1, deletions=0, patch="@@ -1 +1 @@"),
        ),
        base_sha="base",
        head_sha="head",
    ).with_revision()
    return ReviewBrief(
        packet=packet,
        intent=ReviewStatement("O1", "Provenance"),
        requirements=(),
        evidence_catalog=EvidenceCatalog(tuple(evidence)),
        projection=ReviewProjection(
            review_graph=graph,
            verification_workspace=workspace,
            structural_overview=overview,
        ),
        overview=ReviewOverview(
            "open",
            "not_observed",
            3,
            StructuralCoverage(
                "available",
                provider="test",
                hunk_count=2,
                mapped_hunk_count=2,
                symbol_count=3,
                seed_count=2,
                complete_seed_count=2,
                requested_files=3,
                indexed_files=3,
            ),
        ),
    )


def _association_brief() -> ReviewBrief:
    """Add canonical R/G candidate and convergence data to the fixture brief."""

    source = _production_brief()
    relations = (
        ProjectionRelation(
            id="G1:anchor:b",
            focus_statement_id="G1",
            slot="changed_anchor",
            target_type="evidence",
            target_id="EV:N:b",
            association="distinctive_phrase",
            reasons=(
                AssociationReason(
                    "distinctive_phrase",
                    "guardrail phrase overlaps changed symbol",
                    ("bridge", "boundary"),
                ),
            ),
            evidence_role="primary",
        ),
        ProjectionRelation(
            id="R1:anchor:a",
            focus_statement_id="R1",
            slot="changed_anchor",
            target_type="evidence",
            target_id="EV:N:a",
            association="exact_identifier",
            reasons=(
                AssociationReason(
                    "exact_identifier",
                    "canonical symbol identifier matched",
                    ("N:a",),
                ),
            ),
            evidence_role="primary",
        ),
    )
    candidates = ProjectionCandidateSet(
        relations=relations,
        groups=(
            ProjectionCandidateGroup("G1", "guardrail", ("G1:anchor:b",)),
            ProjectionCandidateGroup("R1", "behavior", ("R1:anchor:a",)),
        ),
    )
    convergence = CandidateConvergence(
        groups=(
            ConvergenceGroup(
                "G1",
                selected_relation_ids=("G1:anchor:b",),
            ),
            ConvergenceGroup(
                "R1",
                deferred_relation_ids=("R1:anchor:a",),
            ),
        )
    )
    workspace = source.projection.verification_workspace
    updated_inspections = []
    for inspection in workspace.inspections:
        if inspection.subject_id not in {"G1", "R1"}:
            updated_inspections.append(inspection)
            continue
        memberships = tuple(
            replace(
                membership,
                relation_ids=(
                    ("G1:anchor:b",)
                    if inspection.subject_id == "G1"
                    and membership.member_id == "N:b"
                    else ("R1:anchor:a",)
                    if inspection.subject_id == "R1"
                    and membership.member_id == "N:a"
                    else membership.relation_ids
                ),
            )
            for membership in inspection.structural_overlay.memberships
        )
        updated_inspections.append(
            replace(
                inspection,
                structural_overlay=replace(
                    inspection.structural_overlay,
                    memberships=memberships,
                ),
            )
        )
    updated_projection = replace(
        source.projection,
        verification_workspace=replace(
            workspace,
            inspections=tuple(updated_inspections),
        ),
    )
    return replace(
        source,
        requirements=(Requirement("R1", "Keep the changed anchor."),),
        guardrails=(
            Requirement(
                "G1",
                "Keep the bridge boundary stable.",
                purpose="guardrail",
                kind="guardrail",
            ),
        ),
        projection_candidates=candidates,
        candidate_convergence=convergence,
        projection=updated_projection,
    )


def test_provenance_round_trip_preserves_membership_classes(tmp_path) -> None:
    packet = _packet()
    value = _provenance(packet)

    path = write_provenance_json(value, tmp_path / "provenance.json")
    loaded = load_focus_provenance(path)

    assert loaded == value
    assert loaded.focuses[0].memberships[0].membership_class == "matched"
    assert loaded.focuses[0].memberships[1].membership_class == "context"


def test_association_attribution_copies_candidates_and_observed_membership(
    tmp_path,
) -> None:
    brief = _association_brief()
    packet = prepare_structural_correctness_packet(brief)

    attribution = observe_association_attribution(brief, packet)

    assert [item.relation_id for item in attribution.rows] == [
        "G1:anchor:b",
        "R1:anchor:a",
    ]
    guardrail, requirement = attribution.rows
    assert guardrail.association == "distinctive_phrase"
    assert guardrail.source_channel == "evidence"
    assert guardrail.matched_terms == ("bridge", "boundary")
    assert guardrail.candidate_state == "selected"
    assert guardrail.structural_member_id == "N:b"
    assert guardrail.structural_membership_class == "suggested"
    assert requirement.association == "exact_identifier"
    assert requirement.candidate_state == "deferred"
    assert requirement.structural_member_id == "N:a"
    assert requirement.structural_membership_class == "matched"

    path = write_association_attribution(attribution, tmp_path / "association.json")
    assert load_association_attribution(path) == attribution


def test_association_attribution_rejects_packet_or_reason_drift() -> None:
    brief = _association_brief()
    packet = prepare_structural_correctness_packet(brief)

    with pytest.raises(ValueError, match="does not match current review"):
        observe_association_attribution(
            brief,
            replace(packet, head_sha="different"),
        )

    with pytest.raises(ValueError, match="matched terms are not canonical"):
        replace(
            # Keep this a focused contract test without invoking the producer.
            # The reason's terms are the canonical source for the flattened field.
            observe_association_attribution(brief, packet).rows[0],
            matched_terms=("not-canonical",),
        )


def test_observation_copies_real_review_brief_overlay_for_all_subject_paths(
    tmp_path,
) -> None:
    brief = _production_brief()
    packet = prepare_structural_correctness_packet(brief)

    observation = observe_structural_correctness(brief, packet)
    provenance = observe_focus_provenance(brief, packet, observation)
    by_subject = {item.subject_id: item for item in provenance.focuses}

    r1_kinds = {
        (item.member_kind, item.structural_role)
        for item in by_subject["R1"].memberships
    }
    assert ("ownership_edge", "ownership_ancestor") in r1_kinds
    assert ("placement", "placement_ancestor") in r1_kinds
    assert ("relation_group", "relation_endpoint") in r1_kinds
    assert by_subject["G1"].memberships[0].membership_class == "suggested"
    assert by_subject["T1"].memberships[0].membership_class == "asserted"
    assert by_subject["CC1"].memberships[0].membership_class == "unresolved"
    assert observation.schema_version == OBSERVATION_SCHEMA
    assert all(
        focus.canonical_membership_digest
        == by_subject[focus.subject_id].canonical_membership_digest
        for focus in observation.focuses
    )

    path = write_provenance_json(provenance, tmp_path / "production.json")
    assert load_focus_provenance(path) == provenance


def test_loading_rejects_producer_source_drift(tmp_path) -> None:
    packet = _packet()
    path = write_provenance_json(_provenance(packet), tmp_path / "provenance.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["focuses"][0]["memberships"][0]["provenance"][0][
        "producer"
    ] = "tampered_producer"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="canonical membership digest"):
        load_focus_provenance(path)


def test_replay_rejects_recomputed_sidecar_drift() -> None:
    packet = _packet()
    observation = _aligned_observation(packet)
    source = _provenance(packet)
    tampered_membership = replace(
        source.focuses[0].memberships[0],
        provenance=(
            StructuralFocusProvenance(
                "tampered_producer", "matched", ("S:a",)
            ),
        ),
    )
    tampered = replace(
        source,
        focuses=(
            replace(
                source.focuses[0],
                memberships=(
                    tampered_membership,
                    *source.focuses[0].memberships[1:],
                ),
                canonical_membership_digest="",
            ),
            source.focuses[1],
        ),
    )

    with pytest.raises(ValueError, match="canonical provenance digest differs"):
        replay_producer_counterfactual(
            packet,
            observation,
            tampered,
            _labels(packet),
            disabled_producers=(),
        )


def test_replay_requires_provenance_bound_observation() -> None:
    packet = _packet()

    with pytest.raises(
        ValueError, match="requires a provenance-bound structural observation"
    ):
        replay_producer_counterfactual(
            packet,
            replace(
                _aligned_observation(packet),
                schema_version=PREVIOUS_OBSERVATION_SCHEMA,
            ),
            _provenance(packet),
            _labels(packet),
            disabled_producers=(),
        )


def test_counterfactual_replays_recorded_producer_contribution_only() -> None:
    packet = _packet()
    observation = _aligned_observation(packet)
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
    assert requirement.comparison.selected_nodes.false_exclusions == 1
    assert requirement.comparison.exact_relations.false_exclusions == 0
    assert requirement.comparison.selected_nodes.false_inclusions == 0


def test_zero_intervention_reproduces_observed_dimensions() -> None:
    packet = _packet()
    report = replay_producer_counterfactual(
        packet,
        _aligned_observation(packet),
        _provenance(packet),
        _labels(packet),
        disabled_producers=(),
    )

    requirement = next(
        item for item in report.outcomes if item.subject_kind == "requirement"
    )
    assert requirement.memberships_removed == 0
    assert report.provider_coverage_state == packet.coverage.state
    assert report.provider_seed_mapping_state == packet.coverage.seed_mapping_state
    assert requirement.baseline_focus_dispositions == {"mapped": 1}
    assert requirement.observed.selected_nodes == 2
    assert requirement.observed.claimed_direct_nodes == 1
    assert requirement.observed.suggested_nodes == 0
    assert requirement.observed.structural_context_nodes == 1
    assert requirement.observed.unresolved_nodes == 0
    assert requirement.observed.exact_relations == 1
    assert requirement.comparison.selected_nodes.false_inclusions == 0
    assert requirement.comparison.selected_nodes.false_exclusions == 0
    assert requirement.comparison.claimed_direct_nodes.false_inclusions == 0
    assert requirement.comparison.claimed_direct_nodes.false_exclusions == 0
    assert requirement.comparison.exact_relations.false_inclusions == 0
    assert requirement.comparison.exact_relations.false_exclusions == 0


def test_counterfactual_fails_closed_when_sidecar_buckets_differ() -> None:
    packet = _packet()
    source = _aligned_observation(packet)
    observation = replace(
        source,
        focuses=(replace(source.focuses[0], direct_node_ids=("S:b",)), source.focuses[1]),
    )

    with pytest.raises(ValueError, match="buckets diverge"):
        replay_producer_counterfactual(
            packet,
            observation,
            _provenance(packet),
            _labels(packet),
            disabled_producers=(),
        )


def test_counterfactual_rejects_packet_and_subject_mismatch() -> None:
    packet = _packet()
    with pytest.raises(ValueError, match="structural observation does not match"):
        replay_producer_counterfactual(
            packet,
            replace(_aligned_observation(packet), packet_digest="wrong"),
            _provenance(packet),
            _labels(packet),
            disabled_producers=(),
        )

    with pytest.raises(ValueError, match="must dispose every subject"):
        replay_producer_counterfactual(
            packet,
            _aligned_observation(packet),
            replace(
                _provenance(packet),
                focuses=(_provenance(packet).focuses[0],),
            ),
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
        "transformation_claim",
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
        '{"schema_version":"structural_focus_provenance_observation.v2",'
        f'"packet_digest":"{packet.digest}","focuses":[{{"subject_id":"R1",'
        '"canonical_membership_digest":"invalid",'
        '"memberships":[{"member_kind":"node","member_id":"S:a",'
        '"membership_class":"asserted","structural_role":"changed_anchor",'
        '"provenance":[{"producer":"x","admission_class":"asserted",'
        '"source_ids":[]}]}]}]}',
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
    with pytest.raises(ValueError, match="canonical membership digest"):
        replace(
            value,
            focuses=(
                replace(
                    value.focuses[0],
                    memberships=value.focuses[0].memberships + (unknown_node,),
                ),
                value.focuses[1],
            ),
        )


def test_duplicate_membership_is_rejected() -> None:
    packet = _packet()
    membership = _provenance(packet).focuses[0].memberships[0]

    with pytest.raises(ValueError, match="duplicate memberships"):
        ProvenanceFocus("R1", (membership, membership))


def test_unknown_disabled_producer_is_rejected() -> None:
    packet = _packet()

    with pytest.raises(ValueError, match="unknown disabled producer"):
        replay_producer_counterfactual(
            packet,
            _aligned_observation(packet),
            _provenance(packet),
            _labels(packet),
            disabled_producers=("not_recorded",),
        )


def test_disabling_one_admission_recomputes_surviving_class() -> None:
    packet = _packet()
    source = _provenance(packet)
    dual = StructuralFocusMembership(
        "node",
        "S:a",
        "matched",
        "changed_anchor",
        (
            StructuralFocusProvenance(
                "requirement_association", "matched", ("matched:S:a",)
            ),
            StructuralFocusProvenance(
                "requirement_association", "suggested", ("suggested:S:a",)
            ),
        ),
    )
    provenance = replace(
        source,
        focuses=(
            replace(
                source.focuses[0],
                memberships=(dual, *source.focuses[0].memberships[1:]),
                canonical_membership_digest="",
            ),
            source.focuses[1],
        ),
    )
    source_observation = _aligned_observation(packet)
    bound_observation = replace(
        source_observation,
        focuses=(
            replace(
                source_observation.focuses[0],
                canonical_membership_digest=(
                    provenance.focuses[0].canonical_membership_digest
                ),
            ),
            source_observation.focuses[1],
        ),
    )
    report = replay_producer_counterfactual(
        packet,
        bound_observation,
        provenance,
        _labels(packet),
        disabled_producers=("requirement_association:matched",),
    )

    requirement = next(
        item for item in report.outcomes if item.subject_kind == "requirement"
    )
    assert requirement.observed.claimed_direct_nodes == 0
    assert requirement.observed.suggested_nodes == 1
