from __future__ import annotations

from repodelta.model.contracts import (
    EvidenceCatalog,
    EvidenceItem,
    ObservedTransformation,
    TransformationContract,
    TransformationPredicate,
    TransformationSubjectDiagnostic,
    TransformationSubjectMatch,
    TransformationSubjectSelection,
)
from repodelta.model.predicate_refs import resolve_transformation_selector


def select_transformation_subjects(
    contract: TransformationContract,
    observed: ObservedTransformation,
    evidence_catalog: EvidenceCatalog,
) -> TransformationSubjectSelection:
    """Resolve explicit selectors only to canonical changed structural facts."""

    evidence = evidence_catalog.by_id()
    candidates = tuple(
        evidence[item_id]
        for item_id in observed.structural_change_evidence_ids
        if item_id in evidence
    )
    matches: list[TransformationSubjectMatch] = []
    diagnostics: list[TransformationSubjectDiagnostic] = []

    for predicate in contract.predicates.predicates:
        if predicate.role != "target":
            continue
        for selector_index, selector_value in enumerate(predicate.values, start=1):
            selected, resolution, match_kind = resolve_transformation_selector(
                predicate,
                selector_value,
                candidates,
            )
            if not selected:
                if resolution == "ambiguous":
                    state = "ambiguous_structural_match"
                    message = (
                        f"Explicit selector {selector_value!r} matched multiple "
                        "canonical changed structural identities on its expected "
                        "revision side; direct structural admission is refused. "
                        "Use a qualified symbol or repository path."
                    )
                else:
                    state = "no_structural_match"
                    message = (
                        f"Explicit selector {selector_value!r} did not match a "
                        "canonical changed structural identity on its expected "
                        "revision side."
                    )
                diagnostics.append(
                    TransformationSubjectDiagnostic(
                        id=(
                            f"TSD:{predicate.id}:{selector_index}:"
                            f"{state}"
                        ),
                        claim_id=predicate.claim_id,
                        predicate_id=predicate.id,
                        selector_index=selector_index,
                        state=state,
                        message=message,
                    )
                )
                continue
            matches.extend(
                TransformationSubjectMatch(
                    id=(
                        f"TSM:{predicate.id}:{selector_index}:{item.id}"
                    ),
                    claim_id=predicate.claim_id,
                    predicate_id=predicate.id,
                    selector_index=selector_index,
                    selector_value=selector_value,
                    evidence_id=item.id,
                    selector_match_kind=match_kind or "symbol_name",
                )
                for item in sorted(selected, key=lambda candidate: candidate.id)
            )

    result = TransformationSubjectSelection(
        matches=tuple(matches),
        diagnostics=tuple(diagnostics),
    )
    result.validate_consistency(contract, observed, evidence_catalog)
    return result
