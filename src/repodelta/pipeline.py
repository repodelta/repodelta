from __future__ import annotations

from typing import Protocol

from repodelta.model.contracts import (
    AnalysisInput,
    ReviewBrief,
)
from repodelta.semantics.review import extract_packet_semantics
from repodelta.changes.hunks import parse_changed_files
from repodelta.facts.catalog import build_evidence_catalog
from repodelta.facts.transformation import reconstruct_observed_transformation
from repodelta.closure.planning import compile_closure_scan_plans
from repodelta.closure.scanning import (
    ClosureScanner,
    unavailable_scan_results,
)
from repodelta.providers.sql_schema import (
    SqlSchemaProvider,
    unavailable_sql_schema_result,
)
from repodelta.routing.candidates import build_projection_candidates
from repodelta.routing.transformation import build_transformation_alignment
from repodelta.routing.transformation_subjects import select_transformation_subjects
from repodelta.assessment.transformation import assess_transformation
from repodelta.convergence.core import converge_candidates
from repodelta.convergence.transformation import converge_transformation_closure
from repodelta.projection.build import build_review_projection
from repodelta.projection.overview import (
    build_review_overview,
    project_diagnostic_presentation,
)


class ReviewAnalyzer(Protocol):
    def analyze(self, analysis_input: AnalysisInput) -> ReviewBrief: ...


class DeterministicAnalyzer:
    """Build one conclusion-free requirement-to-evidence candidate graph."""

    def __init__(
        self,
        *,
        closure_scanner: ClosureScanner | None = None,
        sql_schema_provider: SqlSchemaProvider | None = None,
    ) -> None:
        self.closure_scanner = closure_scanner
        self.sql_schema_provider = sql_schema_provider

    def analyze(self, analysis_input: AnalysisInput) -> ReviewBrief:
        packet = analysis_input.packet
        packet.validate_consistency()
        changes = analysis_input.changes or parse_changed_files(packet.changed_files)
        extracted = extract_packet_semantics(packet)
        semantics = extracted.statements
        semantics.transformation_contract.validate_consistency()
        requirements = analysis_input.requirements or semantics.obligations
        for requirement in requirements:
            requirement.validate_consistency()
        deliverables = tuple(item for item in requirements if item.kind != "guardrail")
        guardrails = tuple(item for item in requirements if item.kind == "guardrail")
        closure_scan_plans = compile_closure_scan_plans(
            guardrails,
            semantics.transformation_contract,
        )
        closure_scan_results = (
            self.closure_scanner.scan(closure_scan_plans)
            if self.closure_scanner is not None
            else unavailable_scan_results(closure_scan_plans)
        )
        sql_head_paths = tuple(
            changed_file.head_path
            for changed_file in packet.changed_files
            if changed_file.head_path
            and changed_file.head_path.lower().endswith(".sql")
        )
        sql_base_paths = tuple(
            changed_file.base_path
            for changed_file in packet.changed_files
            if changed_file.base_path
            and changed_file.base_path.lower().endswith(".sql")
        )
        sql_schema_result = (
            self.sql_schema_provider.observe(
                head_paths=sql_head_paths, base_paths=sql_base_paths
            )
            if self.sql_schema_provider is not None
            else unavailable_sql_schema_result(
                head_paths=sql_head_paths, base_paths=sql_base_paths
            )
        )
        evidence_catalog = build_evidence_catalog(
            packet,
            changes,
            analysis_input.structural_graph,
            supplied=analysis_input.supplied_evidence,
            closure_scan_results=closure_scan_results,
            sql_schema_result=sql_schema_result,
        )
        observed_transformation = reconstruct_observed_transformation(
            evidence_catalog
        )
        transformation_subject_selection = select_transformation_subjects(
            semantics.transformation_contract,
            observed_transformation,
            evidence_catalog,
        )
        transformation_structural_closure = converge_transformation_closure(
            semantics.transformation_contract,
            transformation_subject_selection,
            evidence_catalog,
        )
        transformation_alignment = build_transformation_alignment(
            semantics.transformation_contract,
            observed_transformation,
            evidence_catalog,
            transformation_structural_closure,
        )
        transformation_assessment = assess_transformation(
            semantics.transformation_contract,
            transformation_alignment,
            evidence_catalog,
            closure_scan_plans,
            head_sha=packet.head_sha,
            subject_selection=transformation_subject_selection,
            structural_closure=transformation_structural_closure,
        )
        projection_candidates = build_projection_candidates(
            requirements=requirements,
            claims=semantics.claims,
            evidence_catalog=evidence_catalog,
            structural_graph=analysis_input.structural_graph,
            head_sha=packet.head_sha,
            claim_source_state=extracted.claim_source_state,
            closure_scan_plans=closure_scan_plans,
        )
        projection_candidates.validate_consistency()
        candidate_convergence = converge_candidates(
            projection_candidates,
            evidence_catalog=evidence_catalog,
        )
        candidate_convergence.validate_consistency(
            projection_candidates,
            evidence_catalog,
        )
        diagnostic_presentation = project_diagnostic_presentation(
            projection_candidates,
            candidate_convergence,
        )
        projection = build_review_projection(
            projection_candidates,
            candidate_convergence,
            evidence_catalog,
            diagnostic_presentation=diagnostic_presentation,
            changed_files=packet.changed_files,
            closure_scan_plans=closure_scan_plans,
            packet=packet,
            focus_statements=requirements,
            transformation_contract=semantics.transformation_contract,
            transformation_subject_selection=transformation_subject_selection,
            observed_transformation=observed_transformation,
            transformation_structural_closure=transformation_structural_closure,
            transformation_alignment=transformation_alignment,
            transformation_assessment=transformation_assessment,
        )
        overview = build_review_overview(
            packet,
            requirements,
            evidence_catalog,
            analysis_input.structural_graph,
            diagnostic_presentation=diagnostic_presentation,
            structural_graph_disabled=analysis_input.structural_graph_disabled,
        )
        return ReviewBrief(
            packet=packet,
            intent=semantics.intent,
            requirements=deliverables,
            guardrails=guardrails,
            objectives=semantics.objectives,
            scope=semantics.scope,
            verification_expectations=semantics.verification_expectations,
            claims=semantics.claims,
            transformation_contract=semantics.transformation_contract,
            observed_transformation=observed_transformation,
            transformation_subject_selection=transformation_subject_selection,
            transformation_structural_closure=transformation_structural_closure,
            transformation_alignment=transformation_alignment,
            transformation_assessment=transformation_assessment,
            closure_scan_plans=closure_scan_plans,
            evidence_catalog=evidence_catalog,
            projection_candidates=projection_candidates,
            candidate_convergence=candidate_convergence,
            projection=projection,
            overview=overview,
        )
