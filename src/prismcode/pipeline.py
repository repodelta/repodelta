from __future__ import annotations

from typing import Protocol

from prismcode.model.contracts import (
    AnalysisInput,
    ReviewBrief,
)
from prismcode.semantics.review import extract_packet_semantics
from prismcode.changes.hunks import parse_changed_files
from prismcode.facts.catalog import build_evidence_catalog
from prismcode.facts.transformation import reconstruct_observed_transformation
from prismcode.guardrails.planning import compile_guardrail_scan_plans
from prismcode.guardrails.scanning import (
    GuardrailScanner,
    unavailable_scan_results,
)
from prismcode.routing.candidates import build_projection_candidates
from prismcode.convergence.core import converge_candidates
from prismcode.projection.build import build_review_projection
from prismcode.projection.overview import (
    build_review_overview,
    project_diagnostic_presentation,
)


class ReviewAnalyzer(Protocol):
    def analyze(self, analysis_input: AnalysisInput) -> ReviewBrief: ...


class DeterministicAnalyzer:
    """Build one conclusion-free requirement-to-evidence candidate graph."""

    def __init__(self, *, guardrail_scanner: GuardrailScanner | None = None) -> None:
        self.guardrail_scanner = guardrail_scanner

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
        guardrail_scan_plans = compile_guardrail_scan_plans(guardrails)
        guardrail_scan_results = (
            self.guardrail_scanner.scan(guardrail_scan_plans)
            if self.guardrail_scanner is not None
            else unavailable_scan_results(guardrail_scan_plans)
        )
        evidence_catalog = build_evidence_catalog(
            packet,
            changes,
            analysis_input.structural_graph,
            supplied=analysis_input.supplied_evidence,
            guardrail_scan_results=guardrail_scan_results,
        )
        observed_transformation = reconstruct_observed_transformation(
            evidence_catalog
        )
        projection_candidates = build_projection_candidates(
            requirements=requirements,
            claims=semantics.claims,
            evidence_catalog=evidence_catalog,
            structural_graph=analysis_input.structural_graph,
            head_sha=packet.head_sha,
            claim_source_state=extracted.claim_source_state,
            guardrail_scan_plans=guardrail_scan_plans,
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
            guardrail_scan_plans=guardrail_scan_plans,
            packet=packet,
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
            guardrail_scan_plans=guardrail_scan_plans,
            evidence_catalog=evidence_catalog,
            projection_candidates=projection_candidates,
            candidate_convergence=candidate_convergence,
            projection=projection,
            overview=overview,
        )
