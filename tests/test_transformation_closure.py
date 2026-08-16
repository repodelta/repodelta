from __future__ import annotations

from repodelta.convergence.transformation import (
    TransformationClosurePolicy,
    converge_transformation_closure,
)
from repodelta.model.contracts import (
    AnalysisInput,
    CandidateConvergence,
    DiagnosticPresentation,
    EvidenceCatalog,
    EvidenceItem,
    ObservedTransformation,
    ProjectionCandidateSet,
    ReviewSourcePacket,
    TransformationAlignment,
    TransformationAssessment,
    TransformationAssessmentReason,
    TransformationClaimAssessment,
    SourceRef,
    StructuralChangeIdentity,
    StructuralOwnershipChangeIdentity,
    StructuralRelationChangeIdentity,
    TransformationSubjectMatch,
    TransformationSubjectSelection,
)
from repodelta.pipeline import DeterministicAnalyzer
from repodelta.projection.build import build_review_projection
from repodelta.semantics.criteria import extract_review_semantics


def _contract():
    return extract_review_semantics(
        issue_body=None,
        issue_source=None,
        pr_body=(
            "## Selected region\n- `Adapter`\n\n"
            "## Uncertainty\n- External behavior is unknown.\n"
        ),
        pr_source=SourceRef(label="PR #10"),
        pr_title="Close transformation structure",
    ).transformation_contract


def _symbol(identity: str) -> EvidenceItem:
    return EvidenceItem(
        id=f"E:symbol:{identity}",
        summary=identity,
        kind="symbol",
        classification="code",
        profile="production",
        authority="structural_provider",
        revision_side="head",
        operation="unchanged",
        role="runtime_context",
        metadata={"review_symbol_id": identity},
    )


def _path(identity: str, *review_ids: str) -> EvidenceItem:
    return EvidenceItem(
        id=identity,
        summary=identity,
        kind="structural_path",
        classification="code",
        profile="structural_path",
        authority="structural_provider",
        revision_side="head",
        operation="observed",
        role="structural_path",
        structural_path_ids=(identity,),
        metadata={
            "depth": len(review_ids) - 1,
            "steps": tuple(
                {
                    "source_evidence_id": f"E:symbol:{source}",
                    "target_evidence_id": f"E:symbol:{target}",
                    "relation": "calls",
                    "direction": "outgoing",
                }
                for source, target in zip(
                    review_ids,
                    review_ids[1:],
                    strict=False,
                )
            ),
        },
    )


def _fixture():
    contract = _contract()
    predicate = contract.predicates.predicates[0]
    seed = EvidenceItem(
        id="E:change:adapter",
        summary="Modified Adapter",
        kind="structural_change",
        classification="code",
        profile="production",
        authority="structural_provider",
        revision_side="review",
        operation="modified",
        role="changed_anchor",
        changed=True,
        structural_path_ids=("E:path:service", "E:path:store", "E:path:deep"),
        structural_change=StructuralChangeIdentity(review_symbol_id="adapter"),
    )
    paths = (
        _path("E:path:service", "adapter", "service"),
        _path("E:path:store", "adapter", "service", "store"),
        _path("E:path:deep", "adapter", "one", "two", "three", "four"),
    )
    relation_service = EvidenceItem(
        id="E:relation:adapter-service",
        summary="adapter calls service",
        kind="structural_relation_change",
        classification="code",
        profile="structural_path",
        authority="structural_provider",
        revision_side="review",
        operation="retained",
        role="structural_relation",
        structural_path_ids=("E:path:service",),
        structural_relation_change=StructuralRelationChangeIdentity(
            source_review_symbol_id="adapter",
            target_review_symbol_id="service",
            relation="calls",
            head_path_evidence_ids=("E:path:service",),
        ),
    )
    relation_store = EvidenceItem(
        id="E:relation:service-store",
        summary="service calls store",
        kind="structural_relation_change",
        classification="code",
        profile="structural_path",
        authority="structural_provider",
        revision_side="review",
        operation="retained",
        role="structural_relation",
        structural_path_ids=("E:path:store",),
        structural_relation_change=StructuralRelationChangeIdentity(
            source_review_symbol_id="service",
            target_review_symbol_id="store",
            relation="calls",
            head_path_evidence_ids=("E:path:store",),
        ),
    )
    ownership = EvidenceItem(
        id="E:ownership:module-adapter",
        summary="module contains adapter",
        kind="structural_ownership_change",
        classification="code",
        profile="production",
        authority="structural_provider",
        revision_side="review",
        operation="retained",
        role="structural_ownership",
        structural_ownership_change=StructuralOwnershipChangeIdentity(
            parent_review_symbol_id="module",
            child_review_symbol_id="adapter",
            head_ownership_evidence_id="E:ownership:head",
        ),
    )
    symbols = tuple(
        _symbol(identity)
        for identity in (
            "adapter",
            "service",
            "store",
            "one",
            "two",
            "three",
            "four",
            "module",
        )
    )
    catalog = EvidenceCatalog(
        items=(
            seed,
            *symbols,
            *paths,
            relation_service,
            relation_store,
            ownership,
        )
    )
    match = TransformationSubjectMatch(
        id=f"TSM:{predicate.id}:1:{seed.id}",
        claim_id=predicate.claim_id,
        predicate_id=predicate.id,
        selector_index=1,
        selector_value=predicate.values[0],
        evidence_id=seed.id,
    )
    return contract, TransformationSubjectSelection(matches=(match,)), catalog


def test_closure_reuses_collected_two_to_three_hop_paths_and_ownership() -> None:
    contract, selection, catalog = _fixture()

    closure = converge_transformation_closure(contract, selection, catalog)
    group = closure.by_claim_id()["T1"]

    assert group.seed_evidence_ids == ("E:change:adapter",)
    assert group.path_evidence_ids == ("E:path:service", "E:path:store")
    assert group.deferred_path_evidence_ids == ("E:path:deep",)
    assert group.relation_change_evidence_ids == (
        "E:relation:adapter-service",
        "E:relation:service-store",
    )
    assert group.ownership_change_evidence_ids == (
        "E:ownership:module-adapter",
    )
    assert set(group.review_symbol_ids) == {"adapter", "service", "store", "module"}
    assert closure.diagnostics[0].affected_evidence_ids == ("E:path:deep",)
    assert closure.by_claim_id()["T2"].seed_evidence_ids == ()


def test_closure_truncates_only_at_complete_path_identity_boundaries() -> None:
    contract, selection, catalog = _fixture()

    closure = converge_transformation_closure(
        contract,
        selection,
        catalog,
        policy=TransformationClosurePolicy(max_path_identities=1),
    )
    group = closure.by_claim_id()["T1"]

    assert group.path_evidence_ids == ("E:path:service",)
    assert group.deferred_path_evidence_ids == (
        "E:path:store",
        "E:path:deep",
    )
    assert group.relation_change_evidence_ids == (
        "E:relation:adapter-service",
    )
    assert closure.diagnostics[0].state == "budget_truncated"


def test_pipeline_builds_transformation_closure_once(monkeypatch) -> None:
    import repodelta.pipeline as pipeline

    calls = 0
    real_converge = pipeline.converge_transformation_closure

    def counting_converge(contract, selection, catalog):
        nonlocal calls
        calls += 1
        return real_converge(contract, selection, catalog)

    monkeypatch.setattr(
        pipeline,
        "converge_transformation_closure",
        counting_converge,
    )
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=10,
        title="Close transformation structure",
        source_records=(),
    ).with_revision()

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))

    assert calls == 1
    assert brief.transformation_structural_closure.schema_version == (
        "transformation_structural_closure.v1"
    )


def test_closure_projection_is_the_shared_graph_authority() -> None:
    contract, selection, catalog = _fixture()
    closure = converge_transformation_closure(contract, selection, catalog)
    assessment = TransformationAssessment(
        claims=tuple(
            TransformationClaimAssessment(
                id=f"TAS:{claim.id}",
                claim_id=claim.id,
                status="unverified",
                reasons=(
                    TransformationAssessmentReason(
                        kind="no_structural_match",
                        detail="Fixture leaves assessment unresolved.",
                    ),
                ),
            )
            for claim in contract.claims
        )
    )
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=10,
        title="Close transformation structure",
        source_records=(),
    ).with_revision()

    projection = build_review_projection(
        ProjectionCandidateSet(),
        CandidateConvergence(),
        catalog,
        diagnostic_presentation=DiagnosticPresentation(),
        packet=packet,
        focus_statements=(),
        transformation_contract=contract,
        transformation_subject_selection=selection,
        observed_transformation=ObservedTransformation(),
        transformation_structural_closure=closure,
        transformation_alignment=TransformationAlignment(),
        transformation_assessment=assessment,
    )
    graph = projection.review_graph
    topology = projection.verification_workspace.transformation_structural_topology
    overlay = topology.by_claim_id()["T1"].structural_overlay

    assert {node.review_symbol_id for node in graph.nodes} >= {
        "adapter",
        "service",
        "store",
        "module",
    }
    overlay_review_ids = {
        node.review_symbol_id
        for node in graph.nodes
        if node.id in {item.node_id for item in overlay.nodes}
    }
    assert overlay_review_ids >= {
        "adapter",
        "service",
        "store",
        "module",
    }
    assert set(overlay.edge_ids) == {
        "E:relation:adapter-service",
        "E:relation:service-store",
    }
    assert set(overlay.ownership_edge_ids) == {"E:ownership:module-adapter"}
    memberships_by_review_id = {
        node.review_symbol_id: next(
            membership
            for membership in overlay.nodes
            if membership.node_id == node.id
        )
        for node in graph.nodes
        if node.id in {item.node_id for item in overlay.nodes}
    }
    assert memberships_by_review_id["adapter"].membership_class == "asserted"
    assert {
        item.producer
        for item in memberships_by_review_id["adapter"].provenance
    } == {"transformation_selector", "relation_endpoint"}
    assert memberships_by_review_id["adapter"].structural_role == (
        "changed_anchor"
    )
    assert {
        memberships_by_review_id[review_id].membership_class
        for review_id in ("service", "store", "module")
    } == {"context"}
    assert projection.verification_workspace.inspections_by_subject_id()[
        "T1"
    ].structural_overlay == overlay
