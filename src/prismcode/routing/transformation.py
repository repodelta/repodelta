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
    TransformationStructuralClosure,
    TransformationStructuralClosureGroup,
)
from prismcode.model.structural_refs import (
    is_outgoing_executable_head_path,
    ordered_path_review_ids,
    review_symbol_id,
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
    structural_closure: TransformationStructuralClosure | None = None,
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
    structural_group_by_claim = (
        {group.claim_id: group for group in structural_closure.groups}
        if structural_closure is not None
        else {}
    )
    selected_structural_evidence_by_claim = {
            group.claim_id: (
                *group.seed_evidence_ids,
                *group.path_evidence_ids,
            )
            for group in structural_group_by_claim.values()
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

        for evidence_id in selected_structural_evidence_by_claim.get(claim.id, ()):
            selected = evidence.get(evidence_id)
            if selected is None or selected.kind not in {
                "structural_change",
                "structural_path",
            }:
                continue
            claim_bindings.append(
                _binding(
                    claim,
                    selected,
                    (
                        AssociationReason(
                            kind="provided_association",
                            detail=(
                                "Canonical transformation subject selection and "
                                "closure associate this structural evidence with "
                                "the claim."
                            ),
                        ),
                    ),
                )
            )

        eligible = tuple(
            item
            for item in observed_items
            if eligible_transformation_evidence(claim, item)
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
        provider_evidence_ids = {
            binding.evidence_id for binding in claim_bindings
        }
        for item, signature in signatures:
            if item.id in provider_evidence_ids:
                continue
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

        if claim.kind == "authority":
            claim_bindings.extend(
                _authority_bypass_bindings(
                    claim,
                    structural_group_by_claim.get(claim.id),
                    claim_bindings,
                    observed_items,
                    evidence,
                )
            )

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


def _authority_bypass_bindings(
    claim: TransformationClaim,
    structural_group: TransformationStructuralClosureGroup | None,
    claim_bindings: list[TransformationEvidenceBinding],
    observed_items: tuple[EvidenceItem, ...],
    evidence: dict[str, EvidenceItem],
) -> tuple[TransformationEvidenceBinding, ...]:
    """Bind observed paths that reach an authority-controlled sink without it."""

    if structural_group is None:
        return ()
    authority_ids = {
        review_id
        for evidence_id in structural_group.seed_evidence_ids
        if (review_id := review_symbol_id(evidence.get(evidence_id))) is not None
    }
    if not authority_ids:
        return ()
    controlling_paths = tuple(
        evidence[binding.evidence_id]
        for binding in claim_bindings
        if binding.evidence_id in evidence
        and evidence[binding.evidence_id].kind == "structural_path"
        and is_outgoing_executable_head_path(evidence[binding.evidence_id])
        and authority_ids & set(
            ordered_path_review_ids(evidence[binding.evidence_id], evidence)[:-1]
        )
    )
    sink_ids = {
        path_ids[-1]
        for path in controlling_paths
        if (path_ids := ordered_path_review_ids(path, evidence))
    }
    existing_ids = {item.evidence_id for item in claim_bindings}
    return tuple(
        _binding(
            claim,
            item,
            (
                AssociationReason(
                    kind="structural_bridge",
                    detail=(
                        "This observed executable path reaches the same canonical "
                        "sink as an authority-controlled path without traversing "
                        "the declared authority."
                    ),
                ),
            ),
        )
        for item in observed_items
        if item.id not in existing_ids
        and item.kind == "structural_path"
        and is_outgoing_executable_head_path(item)
        and (path_ids := ordered_path_review_ids(item, evidence))
        and path_ids[-1] in sink_ids
    )


def eligible_transformation_evidence(
    claim: TransformationClaim, item: EvidenceItem
) -> bool:
    """Canonical claim-kind eligibility shared by deterministic consumers."""

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
