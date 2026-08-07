from __future__ import annotations

from prismcode.model.contracts import (
    EvidenceCatalog,
    EvidenceItem,
    ProjectionRelation,
    ObservedTransformation,
    ProjectionCandidateSet,
    Requirement,
    ReviewSlice,
    ReviewStructuralGraph,
    StructuralFocusNode,
    StructuralFocusOverlay,
    TransformationAlignment,
    TransformationAssessment,
    TransformationEvidenceBinding,
    TransformationContract,
    TransformationStructuralClosure,
    TransformationStructuralClosureGroup,
    TransformationStructuralTopology,
    TransformationSummaryProjection,
    VerificationEvidenceInspection,
    VerificationMatrixEntry,
    VerificationStatusCount,
    VerificationWorkspace,
)
def project_verification_workspace(
    focus_statements: tuple[Requirement, ...],
    contract: TransformationContract,
    observed: ObservedTransformation,
    alignment: TransformationAlignment,
    assessment: TransformationAssessment,
    evidence_catalog: EvidenceCatalog,
    candidates: ProjectionCandidateSet,
    slices: tuple[ReviewSlice, ...],
    review_graph: ReviewStructuralGraph,
    *,
    transformation_structural_topology: TransformationStructuralTopology,
    transformation_structural_closure: TransformationStructuralClosure,
) -> VerificationWorkspace:
    """Project all review subjects onto one matrix and inspector boundary."""

    relations = candidates.by_id()
    evidence = evidence_catalog.by_id()
    slices_by_focus = {
        item.change_map.focus_statement_id: item for item in slices
    }
    alignment_by_claim = alignment.by_claim_id()
    all_bindings = alignment.bindings
    assessment_by_claim = assessment.by_claim_id()
    topology_by_claim = transformation_structural_topology.by_claim_id()
    matrix: list[VerificationMatrixEntry] = []
    inspections: list[VerificationEvidenceInspection] = []

    for statement in focus_statements:
        review_slice = slices_by_focus[statement.id]
        relation_ids = _slice_relation_ids(review_slice)
        observed_ids = tuple(
            dict.fromkeys(
                (
                    *(
                        relations[item].target_id
                        for item in relation_ids
                        if relations[item].target_type == "evidence"
                    ),
                    *_overlay_evidence_ids(
                        review_slice.change_map.structural_overlay,
                        review_graph,
                    ),
                )
            )
        )
        inspection = VerificationEvidenceInspection(
            id=f"VEI:{statement.id}",
            subject_id=statement.id,
            observed_evidence_ids=observed_ids,
            projection_relation_ids=relation_ids,
            diagnostic_ids=review_slice.diagnostic_ids,
            structural_overlay=review_slice.change_map.structural_overlay,
        )
        inspections.append(inspection)
        matrix.append(
            VerificationMatrixEntry(
                id=f"VME:{statement.id}",
                subject_id=statement.id,
                subject_kind=(
                    "guardrail" if statement.kind == "guardrail" else "requirement"
                ),
                text=statement.text,
                authority=statement.authority,
                status="not_assessed",
                inspector_id=inspection.id,
                sources=statement.sources,
            )
        )

    for claim in contract.claims:
        claim_bindings = alignment_by_claim.get(claim.id, ())
        claim_assessment = assessment_by_claim[claim.id]
        closure_group = transformation_structural_closure.by_claim_id().get(
            claim.id
        )
        topology_group = topology_by_claim.get(claim.id)
        structural_overlay = (
            topology_group.structural_overlay
            if topology_group is not None
            else StructuralFocusOverlay()
        )
        supporting_ids = _binding_evidence_ids(
            claim_assessment.supporting_binding_ids,
            all_bindings,
        )
        contradicting_ids = _binding_evidence_ids(
            claim_assessment.contradicting_binding_ids,
            all_bindings,
        )
        observed_ids = tuple(
            dict.fromkeys(
                (
                    *(item.evidence_id for item in claim_bindings),
                    *supporting_ids,
                    *contradicting_ids,
                    *_transformation_closure_evidence_ids(closure_group),
                    *_overlay_evidence_ids(structural_overlay, review_graph),
                )
            )
        )
        inspection_binding_ids = tuple(
            dict.fromkeys(
                (
                    *(item.id for item in claim_bindings),
                    *claim_assessment.supporting_binding_ids,
                    *claim_assessment.contradicting_binding_ids,
                )
            )
        )
        inspection = VerificationEvidenceInspection(
            id=f"VEI:{claim.id}",
            subject_id=claim.id,
            observed_evidence_ids=observed_ids,
            supporting_evidence_ids=supporting_ids,
            contradicting_evidence_ids=contradicting_ids,
            transformation_binding_ids=inspection_binding_ids,
            diagnostic_ids=(
                topology_group.diagnostic_ids
                if topology_group is not None
                else ()
            ),
            structural_overlay=structural_overlay,
            assessment_reasons=claim_assessment.reasons,
        )
        inspections.append(inspection)
        matrix.append(
            VerificationMatrixEntry(
                id=f"VME:{claim.id}",
                subject_id=claim.id,
                subject_kind=(
                    "completion_condition"
                    if claim.kind == "completion_condition"
                    else "transformation_claim"
                ),
                text=claim.text,
                authority=claim.authority,
                status=claim_assessment.status,
                inspector_id=inspection.id,
                sources=claim.sources,
            )
        )

    workspace = VerificationWorkspace(
        transformation_summary=_transformation_summary(
            contract,
            observed,
            alignment,
            assessment,
        ),
        transformation_structural_topology=transformation_structural_topology,
        matrix=tuple(matrix),
        inspections=tuple(inspections),
    )
    _validate_workspace(
        workspace,
        focus_statements,
        contract,
        observed,
        alignment,
        assessment,
        evidence,
        relations,
        review_graph,
        transformation_structural_topology,
        transformation_structural_closure,
    )
    return workspace


def _transformation_summary(
    contract: TransformationContract,
    observed: ObservedTransformation,
    alignment: TransformationAlignment,
    assessment: TransformationAssessment,
) -> TransformationSummaryProjection:
    status_order = (
        "demonstrated",
        "partial",
        "contradicted",
        "unverified",
    )
    bound_claim_ids = {item.claim_id for item in alignment.bindings}
    topology = observed.topology
    return TransformationSummaryProjection(
        source_state=contract.source_state,
        claim_ids=tuple(item.id for item in contract.claims),
        change_claim_ids=contract.change_claim_ids,
        before_state_claim_ids=contract.state_transition.before_claim_ids,
        after_state_claim_ids=contract.state_transition.after_claim_ids,
        selected_region_claim_ids=contract.region.selected_claim_ids,
        boundary_claim_ids=tuple(
            dict.fromkeys(
                (
                    *contract.region.input_boundary_claim_ids,
                    *contract.region.output_boundary_claim_ids,
                    *contract.region.boundary_claim_ids,
                )
            )
        ),
        before_topology_claim_ids=contract.topology.before_claim_ids,
        after_topology_claim_ids=contract.topology.after_claim_ids,
        authority_claim_ids=contract.authority_claim_ids,
        production_path_claim_ids=contract.production_path_claim_ids,
        migration_claim_ids=contract.migration.general_claim_ids,
        migration_component_claim_ids=tuple(
            dict.fromkeys(
                (
                    *contract.migration.producer_claim_ids,
                    *contract.migration.consumer_claim_ids,
                    *contract.migration.test_claim_ids,
                )
            )
        ),
        removal_claim_ids=contract.removal_claim_ids,
        completion_condition_claim_ids=contract.completion_condition_claim_ids,
        uncertainty_claim_ids=contract.uncertainty_claim_ids,
        observed_evidence_ids=observed.evidence_ids(),
        base_topology_evidence_ids=tuple(
            dict.fromkeys(
                (
                    *topology.base_symbol_change_evidence_ids,
                    *topology.base_relation_change_evidence_ids,
                    *topology.base_ownership_change_evidence_ids,
                )
            )
        ),
        head_topology_evidence_ids=tuple(
            dict.fromkeys(
                (
                    *topology.head_symbol_change_evidence_ids,
                    *topology.head_relation_change_evidence_ids,
                    *topology.head_ownership_change_evidence_ids,
                )
            )
        ),
        aligned_claim_ids=tuple(
            item.id for item in contract.claims if item.id in bound_claim_ids
        ),
        unassociated_claim_ids=tuple(
            item.id for item in contract.claims if item.id not in bound_claim_ids
        ),
        status_counts=tuple(
            VerificationStatusCount(
                status=status,
                count=sum(item.status == status for item in assessment.claims),
            )
            for status in status_order
        ),
    )


def _slice_relation_ids(review_slice: ReviewSlice) -> tuple[str, ...]:
    overlay = review_slice.change_map.structural_overlay
    return tuple(
        dict.fromkeys(
            (
                *review_slice.change_map.claim_relation_ids,
                *(
                    relation_id
                    for node in overlay.nodes
                    for relation_id in node.relation_ids
                ),
                *overlay.path_relation_ids,
                *review_slice.standalone_changed_fact_relation_ids,
                *review_slice.standalone_test_support_relation_ids,
                *review_slice.standalone_document_support_relation_ids,
                *review_slice.standalone_runtime_relation_ids,
                *review_slice.standalone_test_relation_ids,
                *review_slice.verification_relation_ids,
                *review_slice.closure_fact_relation_ids,
            )
        )
    )


def _binding_evidence_ids(
    binding_ids: tuple[str, ...],
    bindings: tuple[TransformationEvidenceBinding, ...],
) -> tuple[str, ...]:
    evidence_by_binding = {item.id: item.evidence_id for item in bindings}
    return tuple(evidence_by_binding[item] for item in binding_ids)


def _transformation_closure_evidence_ids(
    closure_group: TransformationStructuralClosureGroup | None,
) -> tuple[str, ...]:
    if closure_group is None:
        return ()
    return tuple(
        dict.fromkeys(
            (
                *closure_group.seed_evidence_ids,
                *closure_group.path_evidence_ids,
                *closure_group.relation_change_evidence_ids,
                *closure_group.ownership_change_evidence_ids,
            )
        )
    )


def _overlay_evidence_ids(
    overlay: StructuralFocusOverlay,
    graph: ReviewStructuralGraph,
) -> tuple[str, ...]:
    node_ids = {item.node_id for item in overlay.nodes}
    edge_ids = set(overlay.edge_ids)
    ownership_ids = set(overlay.ownership_edge_ids)
    placement_ids = set(overlay.placement_ids)
    return tuple(
        dict.fromkeys(
            (
                *(
                    evidence_id
                    for node in graph.nodes
                    if node.id in node_ids
                    for evidence_id in node.evidence_ids
                ),
                *(
                    edge.relation_change_evidence_id
                    for edge in graph.edges
                    if edge.id in edge_ids
                ),
                *(
                    edge.ownership_change_evidence_id
                    for edge in graph.ownership_edges
                    if edge.id in ownership_ids
                ),
                *(
                    evidence_id
                    for placement in graph.placements
                    if placement.id in placement_ids
                    for evidence_id in (
                        *placement.base_ownership_evidence_ids,
                        *placement.head_ownership_evidence_ids,
                    )
                ),
            )
        )
    )


def _validate_workspace(
    workspace: VerificationWorkspace,
    focus_statements: tuple[Requirement, ...],
    contract: TransformationContract,
    observed: ObservedTransformation,
    alignment: TransformationAlignment,
    assessment: TransformationAssessment,
    evidence: dict[str, EvidenceItem],
    relations: dict[str, ProjectionRelation],
    graph: ReviewStructuralGraph,
    transformation_structural_topology: TransformationStructuralTopology,
    transformation_structural_closure: TransformationStructuralClosure,
) -> None:
    if workspace.schema_version != "verification_workspace.v6":
        raise ValueError("unsupported verification workspace schema")
    if workspace.transformation_structural_topology != (
        transformation_structural_topology
    ):
        raise ValueError("verification workspace changed transformation topology")
    if workspace.transformation_summary != _transformation_summary(
        contract,
        observed,
        alignment,
        assessment,
    ):
        raise ValueError("verification workspace changed transformation summary")
    expected_ids = (
        *(item.id for item in focus_statements),
        *(item.id for item in contract.claims),
    )
    if tuple(item.subject_id for item in workspace.matrix) != expected_ids:
        raise ValueError("verification matrix must preserve every subject once")
    if tuple(item.subject_id for item in workspace.inspections) != expected_ids:
        raise ValueError("evidence inspector must preserve every subject once")
    inspections = {item.id: item for item in workspace.inspections}
    if len({item.id for item in workspace.matrix}) != len(workspace.matrix):
        raise ValueError("verification workspace contains duplicate matrix entries")
    if len(inspections) != len(workspace.inspections):
        raise ValueError("verification workspace contains duplicate inspectors")
    assessment_by_claim = assessment.by_claim_id()
    alignment_by_claim = alignment.by_claim_id()
    binding_ids = {item.id for item in alignment.bindings}
    graph_node_ids = {item.id for item in graph.nodes}
    graph_edge_ids = {item.id for item in graph.edges}
    graph_group_ids = {item.id for item in graph.relation_groups}
    graph_ownership_ids = {item.id for item in graph.ownership_edges}
    graph_placement_ids = {item.id for item in graph.placements}
    closure_by_claim = transformation_structural_closure.by_claim_id()
    topology_by_claim = transformation_structural_topology.by_claim_id()
    if transformation_structural_topology.schema_version != (
        "transformation_structural_topology.v1"
    ):
        raise ValueError("unsupported transformation structural topology schema")
    if tuple(
        item.claim_id for item in transformation_structural_topology.groups
    ) != tuple(item.id for item in contract.claims):
        raise ValueError("transformation topology must preserve every claim once")
    closure_diagnostic_ids = {
        item.id for item in transformation_structural_closure.diagnostics
    }
    for topology_group in transformation_structural_topology.groups:
        closure_group = closure_by_claim.get(topology_group.claim_id)
        if closure_group is None:
            raise ValueError(
                f"{topology_group.claim_id}: topology has no closure group"
            )
        expected_diagnostics = tuple(
            item.id
            for item in transformation_structural_closure.diagnostics
            if item.claim_id == topology_group.claim_id
        )
        if topology_group.diagnostic_ids != expected_diagnostics:
            raise ValueError(
                f"{topology_group.claim_id}: topology diagnostics diverge from closure"
            )
        overlay = topology_group.structural_overlay
        overlay_review_ids = {
            item.review_symbol_id
            for item in graph.nodes
            if item.id in {node.node_id for node in overlay.nodes}
        }
        if not set(closure_group.review_symbol_ids) <= overlay_review_ids:
            raise ValueError(
                f"{topology_group.claim_id}: closure symbols were dropped"
            )
        overlay_relation_ids = {
            edge.relation_change_evidence_id
            for edge in graph.edges
            if edge.id in set(overlay.edge_ids)
        }
        if overlay_relation_ids != set(closure_group.relation_change_evidence_ids):
            raise ValueError(
                f"{topology_group.claim_id}: closure relation membership changed"
            )
        overlay_ownership_ids = {
            edge.ownership_change_evidence_id
            for edge in graph.ownership_edges
            if edge.id in set(overlay.ownership_edge_ids)
        }
        if overlay_ownership_ids != set(closure_group.ownership_change_evidence_ids):
            raise ValueError(
                f"{topology_group.claim_id}: closure ownership membership changed"
            )
        if not set(topology_group.diagnostic_ids) <= closure_diagnostic_ids:
            raise ValueError(
                f"{topology_group.claim_id}: topology references unknown closure diagnostic"
            )
    for entry in workspace.matrix:
        if entry.id != f"VME:{entry.subject_id}":
            raise ValueError("verification matrix entry has non-canonical ID")
        inspection = inspections.get(entry.inspector_id)
        if inspection is None or inspection.subject_id != entry.subject_id:
            raise ValueError("verification matrix references invalid inspector")
        if entry.subject_id in assessment_by_claim:
            claim_assessment = assessment_by_claim[entry.subject_id]
            if entry.status != claim_assessment.status:
                raise ValueError("verification projection changed assessment status")
            if inspection.assessment_reasons != claim_assessment.reasons:
                raise ValueError("verification projection changed assessment reasons")
        elif entry.status != "not_assessed":
            raise ValueError("R/G projection cannot invent an assessment")
    for inspection in workspace.inspections:
        if inspection.id != f"VEI:{inspection.subject_id}":
            raise ValueError("verification inspection has non-canonical ID")
        if not set(inspection.observed_evidence_ids) <= set(evidence):
            raise ValueError("verification inspector references unknown evidence")
        if not set(inspection.projection_relation_ids) <= set(relations):
            raise ValueError("verification inspector references unknown relation")
        if not set(inspection.transformation_binding_ids) <= binding_ids:
            raise ValueError("verification inspector references unknown binding")
        if inspection.subject_id in assessment_by_claim:
            claim_assessment = assessment_by_claim[inspection.subject_id]
            expected_bindings = tuple(
                dict.fromkeys(
                    (
                        *(
                            item.id
                            for item in alignment_by_claim.get(
                                inspection.subject_id, ()
                            )
                        ),
                        *claim_assessment.supporting_binding_ids,
                        *claim_assessment.contradicting_binding_ids,
                    )
                )
            )
            if inspection.transformation_binding_ids != expected_bindings:
                raise ValueError(
                    "verification inspector changed transformation bindings"
                )
        elif inspection.transformation_binding_ids:
            raise ValueError("R/G inspector cannot reference T/CC bindings")
        if inspection.subject_id in topology_by_claim:
            topology_group = topology_by_claim[inspection.subject_id]
            closure_group = closure_by_claim[inspection.subject_id]
            closure_evidence_ids = set(
                _transformation_closure_evidence_ids(closure_group)
            )
            if not closure_evidence_ids <= set(inspection.observed_evidence_ids):
                raise ValueError(
                    "transformation inspector dropped closure evidence"
                )
            if inspection.structural_overlay != topology_group.structural_overlay:
                raise ValueError(
                    "transformation inspector diverges from canonical topology"
                )
            if inspection.diagnostic_ids != topology_group.diagnostic_ids:
                raise ValueError(
                    "transformation inspector changed closure diagnostics"
                )
        if not set(inspection.supporting_evidence_ids) <= set(
            inspection.observed_evidence_ids
        ) or not set(inspection.contradicting_evidence_ids) <= set(
            inspection.observed_evidence_ids
        ):
            raise ValueError(
                "verification inspector assessment evidence is not observed"
            )
        if any(
            relations[relation_id].focus_statement_id != inspection.subject_id
            for relation_id in inspection.projection_relation_ids
        ):
            raise ValueError("verification inspector relation belongs to another focus")
        overlay = inspection.structural_overlay
        if not {item.node_id for item in overlay.nodes} <= graph_node_ids:
            raise ValueError("verification inspector references unknown graph node")
        if not set(overlay.edge_ids) <= graph_edge_ids:
            raise ValueError("verification inspector references unknown graph edge")
        if not set(overlay.relation_group_ids) <= graph_group_ids:
            raise ValueError("verification inspector references unknown graph group")
        if not set(overlay.ownership_edge_ids) <= graph_ownership_ids:
            raise ValueError("verification inspector references unknown ownership")
        if not set(overlay.placement_ids) <= graph_placement_ids:
            raise ValueError("verification inspector references unknown placement")
