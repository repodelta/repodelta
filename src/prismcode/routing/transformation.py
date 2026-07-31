from __future__ import annotations

from prismcode.facts.lexical import merge_signatures
from prismcode.model.contracts import (
    AssociationReason,
    AssociationSignature,
    EvidenceCatalog,
    EvidenceItem,
    ObservedTransformation,
    TransformationAlignment,
    TransformationAlignmentDiagnostic,
    TransformationClaim,
    TransformationContract,
    TransformationEvidenceBinding,
)
from prismcode.routing.association import (
    distinctive_signature_terms,
    distinctive_text_terms,
    evidence_reasons,
)


def build_transformation_alignment(
    contract: TransformationContract,
    observed: ObservedTransformation,
    evidence_catalog: EvidenceCatalog,
) -> TransformationAlignment:
    """Bind authored T/CC claims to eligible observed facts without assessment."""

    evidence = evidence_catalog.by_id()
    observed_items = tuple(
        evidence[item_id]
        for item_id in observed.evidence_ids()
        if item_id in evidence
    )
    closure_by_statement = {
        item.associated_statement_ids[0]: item
        for item in evidence.values()
        if item.role == "closure_fact"
        and len(item.associated_statement_ids) == 1
    }
    distinctive = distinctive_text_terms(
        tuple((item.id, item.text) for item in contract.claims)
    )
    bindings: list[TransformationEvidenceBinding] = []
    diagnostics: list[TransformationAlignmentDiagnostic] = []

    for claim in contract.claims:
        claim_bindings: list[TransformationEvidenceBinding] = []
        closure = closure_by_statement.get(claim.id)
        if closure is not None:
            claim_bindings.append(
                _binding(
                    claim,
                    closure,
                    (
                        AssociationReason(
                            kind="provided_association",
                            detail=(
                                "The closure provider explicitly associates this "
                                "revision-aware observation with the typed claim."
                            ),
                        ),
                    ),
                )
            )

        eligible = tuple(
            item for item in observed_items if _eligible(claim, item)
        )
        signatures = tuple(
            (item, _signature(claim, item)) for item in eligible
        )
        evidence_distinctive = distinctive_signature_terms(
            tuple(
                (item.id, signature)
                for item, signature in signatures
                if signature.identifiers or signature.tokens
            )
        )
        for item, signature in signatures:
            reasons = evidence_reasons(
                claim,
                signature,
                distinctive_terms=(
                    distinctive.get(claim.id, frozenset())
                    & evidence_distinctive.get(item.id, frozenset())
                ),
            )
            if reasons:
                claim_bindings.append(_binding(claim, item, reasons))

        claim_bindings = list(
            {item.evidence_id: item for item in claim_bindings}.values()
        )
        bindings.extend(sorted(claim_bindings, key=lambda item: item.evidence_id))
        if not claim_bindings:
            state = "no_eligible_fact" if not eligible else "no_association"
            diagnostics.append(
                TransformationAlignmentDiagnostic(
                    id=f"TAD:{claim.id}",
                    claim_id=claim.id,
                    state=state,
                    message=(
                        "No observed fact is eligible for this transformation "
                        "claim kind."
                        if state == "no_eligible_fact"
                        else "Eligible observed facts exist, but no deterministic "
                        "identifier or distinctive-phrase association was found."
                    ),
                )
            )

    result = TransformationAlignment(
        bindings=tuple(bindings),
        diagnostics=tuple(diagnostics),
    )
    result.validate_consistency(contract, observed, evidence_catalog)
    return result


def _eligible(claim: TransformationClaim, item: EvidenceItem) -> bool:
    role = item.transformation_evidence_role()
    if role is None or claim.kind == "uncertainty":
        return False
    if claim.kind == "test_migration":
        return item.profile == "test" and role in {"change", "structural_path"}
    if claim.kind == "production_path":
        return item.profile == "production" or role in {
            "relation_change",
            "ownership_change",
            "structural_path",
        }
    if claim.kind == "before_topology":
        return bool(item.base_signature.identifiers or item.base_signature.tokens)
    if claim.kind == "after_topology":
        return bool(item.head_signature.identifiers or item.head_signature.tokens)
    if claim.kind == "removal":
        return role in {"change", "relation_change", "ownership_change"} and (
            item.operation in {"removed", "replaced", "unresolved"}
            or bool(item.base_signature.identifiers or item.base_signature.tokens)
        )
    if claim.kind == "completion_condition":
        return role in {
            "change",
            "relation_change",
            "ownership_change",
            "structural_path",
            "verification",
        }
    if claim.kind == "authority":
        return role in {"change", "relation_change", "ownership_change"}
    return role in {
        "change",
        "relation_change",
        "ownership_change",
        "structural_path",
    }


def _signature(
    claim: TransformationClaim,
    item: EvidenceItem,
) -> AssociationSignature:
    if claim.kind in {"before_topology", "removal"}:
        return item.base_signature
    if claim.kind == "after_topology":
        return item.head_signature
    return merge_signatures(item.head_signature, item.base_signature)


def _binding(
    claim: TransformationClaim,
    item: EvidenceItem,
    reasons: tuple[AssociationReason, ...],
) -> TransformationEvidenceBinding:
    role = item.transformation_evidence_role()
    if role is None:
        raise ValueError(f"{item.id}: ineligible transformation evidence role")
    return TransformationEvidenceBinding(
        id=f"TAB:{claim.id}:{item.id}",
        claim_id=claim.id,
        evidence_id=item.id,
        evidence_role=role,
        association=reasons[0].kind,
        reasons=reasons,
    )
