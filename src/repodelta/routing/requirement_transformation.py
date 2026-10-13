from __future__ import annotations

import re

from repodelta.model.contracts import (
    AssociationReason,
    Requirement,
    RequirementTransformationAssociation,
    RequirementTransformationTrace,
    RequirementTransformationTraceDiagnostic,
    RequirementTransformationTraceGroup,
    TransformationAlignment,
    TransformationAssessment,
    TransformationContract,
    TransformationEvidenceSlice,
    TransformationStructuralClosure,
    TransformationSubjectSelection,
)


_FOCUS_REFERENCE_RE = re.compile(r"\b(?:R|G)[-_ ]?\d+\b", re.IGNORECASE)


def build_requirement_transformation_trace(
    focus_statements: tuple[Requirement, ...],
    contract: TransformationContract,
    subject_selection: TransformationSubjectSelection,
    structural_closure: TransformationStructuralClosure,
    alignment: TransformationAlignment,
    assessment: TransformationAssessment,
) -> RequirementTransformationTrace:
    """Join explicit authored R/G references to canonical T/CC artifacts."""

    focus_ids = {item.id for item in focus_statements}
    selection_by_claim = subject_selection.by_claim_id()
    bindings_by_claim = alignment.by_claim_id()
    assessments_by_claim = assessment.by_claim_id()
    diagnostic_ids_by_claim: dict[str, list[str]] = {}
    for diagnostic in (
        *subject_selection.diagnostics,
        *structural_closure.diagnostics,
        *alignment.diagnostics,
    ):
        diagnostic_ids_by_claim.setdefault(diagnostic.claim_id, []).append(
            diagnostic.id
        )

    claim_references: dict[str, tuple[str, ...]] = {}
    diagnostics: list[RequirementTransformationTraceDiagnostic] = []
    for claim in contract.claims:
        references = _focus_references(claim.text)
        claim_references[claim.id] = references
        for reference in references:
            if reference in focus_ids:
                continue
            diagnostics.append(
                RequirementTransformationTraceDiagnostic(
                    id=f"RTD:{claim.id}:{reference}",
                    claim_id=claim.id,
                    referenced_focus_statement_id=reference,
                    state="unknown_focus_reference",
                    message=(
                        f"The authored transformation claim references {reference}, "
                        "but no formal requirement or guardrail owns that identity."
                    ),
                    sources=claim.sources,
                )
            )

    associations: list[RequirementTransformationAssociation] = []
    groups: list[RequirementTransformationTraceGroup] = []
    associated_claim_ids: list[str] = []
    for focus in focus_statements:
        group_association_ids: list[str] = []
        for claim in contract.claims:
            if focus.id not in claim_references[claim.id]:
                continue
            association_id = f"RTA:{focus.id}:{claim.id}"
            associations.append(
                RequirementTransformationAssociation(
                    id=association_id,
                    focus_statement_id=focus.id,
                    transformation_claim_id=claim.id,
                    evidence_slice_id=f"TES:{claim.id}",
                    reasons=(
                        AssociationReason(
                            kind="explicit_reference",
                            detail=(
                                "The authored transformation claim explicitly "
                                f"references {focus.id}."
                            ),
                            matched_terms=(focus.id,),
                        ),
                    ),
                )
            )
            group_association_ids.append(association_id)
            if claim.id not in associated_claim_ids:
                associated_claim_ids.append(claim.id)
        groups.append(
            RequirementTransformationTraceGroup(
                focus_statement_id=focus.id,
                association_ids=tuple(group_association_ids),
                coverage_state=(
                    "transformation_source_absent"
                    if contract.source_state != "available"
                    else "associated"
                    if group_association_ids
                    else "no_explicit_association"
                ),
            )
        )

    evidence_slices = tuple(
        TransformationEvidenceSlice(
            id=f"TES:{claim.id}",
            claim_id=claim.id,
            structural_closure_claim_id=claim.id,
            subject_match_ids=tuple(
                item.id for item in selection_by_claim.get(claim.id, ())
            ),
            transformation_binding_ids=tuple(
                item.id for item in bindings_by_claim.get(claim.id, ())
            ),
            assessment_id=assessments_by_claim[claim.id].id,
            diagnostic_ids=tuple(diagnostic_ids_by_claim.get(claim.id, ())),
        )
        for claim in contract.claims
        if claim.id in associated_claim_ids
    )
    trace = RequirementTransformationTrace(
        groups=tuple(groups),
        associations=tuple(associations),
        evidence_slices=evidence_slices,
        diagnostics=tuple(diagnostics),
        requirement_source_state=(
            "available" if focus_statements else "source_absent"
        ),
    )
    trace.validate_consistency(
        focus_statements,
        contract,
        subject_selection,
        structural_closure,
        alignment,
        assessment,
    )
    return trace


def _focus_references(text: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            value.replace("_", "").replace("-", "").replace(" ", "").upper()
            for value in _FOCUS_REFERENCE_RE.findall(text)
        )
    )
