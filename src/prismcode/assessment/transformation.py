from __future__ import annotations

import re
from dataclasses import replace

from prismcode.assessment.migration import close_migration_assessments
from prismcode.model.contracts import (
    ClosureScanPlan,
    ClosureScanPlanSet,
    EvidenceCatalog,
    EvidenceItem,
    TransformationAlignment,
    TransformationAssessment,
    TransformationAssessmentReason,
    TransformationPredicate,
    TransformationPredicateAssessment,
    TransformationClaim,
    TransformationClaimAssessment,
    TransformationContract,
    TransformationEvidenceBinding,
    TransformationStructuralClosure,
    TransformationStructuralClosureGroup,
    TransformationSubjectSelection,
)
from prismcode.model.predicate_refs import matches_transformation_selector
from prismcode.model.structural_refs import (
    is_executable_head_path,
    is_outgoing_executable_head_path,
    ordered_path_evidence_ids,
    ordered_path_review_ids,
    review_symbol_id,
)

_SURFACE_PRESENCE_CLAIM_KINDS = frozenset({"change"})
_SUCCESS_CONCLUSIONS = frozenset({"success"})
_FAILURE_CONCLUSIONS = frozenset(
    {"failure", "cancelled", "timed_out", "action_required", "startup_failure"}
)


def assess_transformation(
    contract: TransformationContract,
    alignment: TransformationAlignment,
    evidence_catalog: EvidenceCatalog,
    closure_scan_plans: ClosureScanPlanSet,
    *,
    head_sha: str,
    subject_selection: TransformationSubjectSelection | None = None,
    structural_closure: TransformationStructuralClosure | None = None,
) -> TransformationAssessment:
    """Assess aligned facts without inferring acceptance or mergeability."""

    evidence = evidence_catalog.by_id()
    bindings = alignment.by_claim_id()
    plans = closure_scan_plans.by_statement_id()
    structural_groups = (
        structural_closure.by_claim_id() if structural_closure is not None else {}
    )
    uncertainty_claim_ids = {
        item.id for item in contract.claims if item.kind == "uncertainty"
    }
    uncertainty_evidence_ids = frozenset(
        {
        item.evidence_id
        for item in (subject_selection.matches if subject_selection else ())
        if item.claim_id in uncertainty_claim_ids
        }
    )
    component_assessments = tuple(
        _assess_claim(
            claim,
            bindings.get(claim.id, ()),
            evidence,
            plans.get(claim.id),
            head_sha=head_sha,
            predicates=contract.predicates.by_claim_id().get(claim.id, ()),
            subject_selection=subject_selection,
            structural_group=structural_groups.get(claim.id),
            uncertainty_evidence_ids=uncertainty_evidence_ids,
        )
        for claim in contract.claims
    )
    assessments = close_migration_assessments(contract, component_assessments)
    result = TransformationAssessment(claims=assessments)
    result.validate_consistency(contract, alignment, evidence_catalog)
    return result


def _assess_claim(
    claim: TransformationClaim,
    bindings: tuple[TransformationEvidenceBinding, ...],
    evidence: dict[str, EvidenceItem],
    closure_plan: ClosureScanPlan | None,
    *,
    head_sha: str,
    predicates: tuple[TransformationPredicate, ...] = (),
    subject_selection: TransformationSubjectSelection | None = None,
    structural_group: TransformationStructuralClosureGroup | None = None,
    uncertainty_evidence_ids: frozenset[str] = frozenset(),
) -> TransformationClaimAssessment:
    if claim.kind in {"before_state", "after_state"}:
        return _result(
            claim,
            "unverified",
            (),
            (),
            (
                _reason(
                    "generic_transition_context",
                    "Authored before/after state is preserved without inferring "
                    "topology, authority, migration, or completion semantics.",
                ),
            ),
        )
    if claim.kind == "uncertainty":
        predicate_assessments = tuple(
            _predicate_result(
                claim,
                predicate,
                "unverified",
                (),
                (),
                (
                    _reason(
                        "uncertainty_context",
                        "Authored uncertainty is review context, not a fact claim.",
                    ),
                ),
            )
            for predicate in predicates
            if predicate.role == "target"
        )
        if predicate_assessments:
            return _aggregate_predicate_assessments(
                claim,
                predicate_assessments,
            )
        return _result(
            claim,
            "unverified",
            (),
            (),
            (
                _reason(
                    "uncertainty_context",
                    "Authored uncertainty is review context, not a fact claim.",
                ),
            ),
        )
    target_predicates = tuple(
        item for item in predicates if item.role == "target"
    )
    if target_predicates:
        predicate_assessments = tuple(
            _assess_predicate(
                claim,
                predicate,
                bindings,
                evidence,
                closure_plan,
                head_sha=head_sha,
                subject_selection=subject_selection,
                structural_group=structural_group,
                uncertainty_evidence_ids=uncertainty_evidence_ids,
            )
            for predicate in target_predicates
        )
        return _aggregate_predicate_assessments(
            claim,
            predicate_assessments,
        )
    if not bindings:
        return _result(
            claim,
            "unverified",
            (),
            (),
            (
                _reason(
                    "no_binding",
                    "No eligible observed fact was deterministically associated.",
                ),
            ),
        )

    closure = tuple(item for item in bindings if item.evidence_role == "closure")
    if closure:
        return _assess_closure(
            claim,
            closure[0],
            evidence[closure[0].evidence_id],
            closure_plan,
        )
    if closure_plan is not None:
        return _result(
            claim,
            "partial",
            bindings,
            (),
            (
                _reason(
                    "coverage_incomplete",
                    "Local aligned changes do not replace the required "
                    "revision-aware repository closure observation.",
                    bindings,
                ),
            ),
        )

    verification = tuple(
        item for item in bindings if item.evidence_role == "verification"
    )
    if verification:
        assessed = _assess_verification(claim, verification, evidence, head_sha)
        if claim.kind == "completion_condition" or assessed.status in {
            "demonstrated",
            "contradicted",
        }:
            return assessed

    exact = tuple(
        item for item in bindings
        if item.association in {"provided_association", "exact_identifier"}
    )
    if (
        exact
        and claim.kind in _SURFACE_PRESENCE_CLAIM_KINDS
    ):
        return _result(
            claim,
            "demonstrated",
            exact,
            (),
            (
                _reason(
                    "exact_fact_observed",
                    "An exact identifier or provider-owned observed fact "
                    "demonstrates the positive claim surface.",
                    exact,
                ),
            ),
        )
    selected = exact or bindings
    return _result(
        claim,
        "partial",
        selected,
        (),
        (
            _reason(
                "association_only",
                "Related observed facts support the claim, but do not prove its "
                "full boundary or completion semantics.",
                selected,
            ),
        ),
    )


def _assess_predicate(
    claim: TransformationClaim,
    predicate: TransformationPredicate,
    bindings: tuple[TransformationEvidenceBinding, ...],
    evidence: dict[str, EvidenceItem],
    closure_plan: ClosureScanPlan | None,
    *,
    head_sha: str,
    subject_selection: TransformationSubjectSelection | None,
    structural_group: TransformationStructuralClosureGroup | None,
    uncertainty_evidence_ids: frozenset[str],
) -> TransformationPredicateAssessment:
    predicate_bindings = _predicate_bindings(
        claim,
        predicate,
        bindings,
        evidence,
        closure_plan,
        subject_selection=subject_selection,
        structural_group=structural_group,
    )
    if claim.kind == "authority":
        return _assess_authority_predicate(
            claim,
            predicate,
            predicate_bindings,
            evidence,
            subject_selection,
            structural_group,
            uncertainty_evidence_ids,
        )
    if predicate.selector_kind == "ordered_path":
        return _assess_ordered_path_predicate(
            claim,
            predicate,
            predicate_bindings,
            evidence,
            structural_group,
            head_sha=head_sha,
        )
    closure_binding = next(
        (item for item in predicate_bindings if item.evidence_role == "closure"),
        None,
    )
    if closure_binding is not None and closure_plan is not None:
        fact = evidence[closure_binding.evidence_id]
        return _assess_closure_predicate(
            claim,
            predicate,
            closure_binding,
            fact,
            closure_plan,
        )

    if predicate.expectation == "verified_head":
        verification = tuple(
            item
            for item in predicate_bindings
            if item.evidence_role == "verification"
        )
        if verification:
            assessed = _assess_verification(
                claim,
                verification,
                evidence,
                head_sha,
                require_success=True,
            )
            return _predicate_result(
                claim,
                predicate,
                assessed.status,
                assessed.supporting_binding_ids,
                assessed.contradicting_binding_ids,
                assessed.reasons,
            )

    exact = tuple(
        item
        for item in predicate_bindings
        if item.association in {"provided_association", "exact_identifier"}
    )
    if exact:
        status = (
            "demonstrated"
            if claim.kind in _SURFACE_PRESENCE_CLAIM_KINDS
            and predicate.expectation == "reference"
            else "partial"
        )
        reason_kind = (
            "association_only"
            if status == "partial"
            else "exact_fact_observed"
        )
        return _predicate_result(
            claim,
            predicate,
            status,
            tuple(item.id for item in exact),
            (),
            (
                _reason(
                    reason_kind,
                    (
                        "The exact predicate surface is observed, but the claim's "
                        "role, topology, boundary, migration, absence, or completion "
                        "semantics require stronger typed proof."
                        if status == "partial"
                        else "An exact predicate surface is observed on the declared revision."
                    ),
                    exact,
                ),
            ),
        )
    if predicate_bindings:
        return _predicate_result(
            claim,
            predicate,
            "partial",
            tuple(item.id for item in predicate_bindings),
            (),
            (
                _reason(
                    "association_only",
                    "Related evidence is present, but no exact predicate binding was observed.",
                    predicate_bindings,
                ),
            ),
        )
    return _predicate_result(
        claim,
        predicate,
        "unverified",
        (),
        (),
        (
            _reason(
                "no_binding",
                "No observed fact was deterministically associated with this predicate.",
            ),
        ),
    )


def _predicate_bindings(
    claim: TransformationClaim,
    predicate: TransformationPredicate,
    bindings: tuple[TransformationEvidenceBinding, ...],
    evidence: dict[str, EvidenceItem],
    closure_plan: ClosureScanPlan | None,
    *,
    subject_selection: TransformationSubjectSelection | None,
    structural_group: TransformationStructuralClosureGroup | None,
) -> tuple[TransformationEvidenceBinding, ...]:
    selected_ids = {
        item.evidence_id
        for item in (subject_selection.matches if subject_selection else ())
        if item.predicate_id == predicate.id
    }
    closure_ids = {
        item.evidence_id
        for item in bindings
        if item.evidence_role == "closure"
        and predicate.expectation == "absent_head"
        and _closure_fact_has_predicate(
            evidence[item.evidence_id],
            predicate,
            closure_plan,
        )
    }
    predicate_specific_ids = {
        item.evidence_id
        for item in bindings
        if item.evidence_role != "closure"
        and any(
            matches_transformation_selector(
                predicate,
                selector_value,
                evidence[item.evidence_id],
            )
            for selector_value in predicate.values
        )
    }
    structural_bridge_ids = {
        item.evidence_id
        for item in bindings
        if item.association == "structural_bridge"
    }
    authority_path_ids = {
        item.evidence_id
        for item in bindings
        if claim.kind == "authority"
        and item.evidence_role == "structural_path"
        and item.association == "provided_association"
    }
    ordered_path_ids = (
        set(structural_group.path_evidence_ids)
        if predicate.selector_kind == "ordered_path"
        and structural_group is not None
        else set()
    )
    ordered_verification_ids = {
        item.evidence_id
        for item in bindings
        if item.evidence_role == "verification"
        and item.evidence_id in predicate_specific_ids
    }
    admitted_ids = (
        ordered_path_ids | ordered_verification_ids
        if predicate.selector_kind == "ordered_path"
        else selected_ids
        | closure_ids
        | predicate_specific_ids
        | structural_bridge_ids
        | authority_path_ids
    )
    return tuple(item for item in bindings if item.evidence_id in admitted_ids)


def _assess_authority_predicate(
    claim: TransformationClaim,
    predicate: TransformationPredicate,
    bindings: tuple[TransformationEvidenceBinding, ...],
    evidence: dict[str, EvidenceItem],
    subject_selection: TransformationSubjectSelection | None,
    structural_group: TransformationStructuralClosureGroup | None,
    uncertainty_evidence_ids: frozenset[str],
) -> TransformationPredicateAssessment:
    """Require an executable consumer path and reject observed shared-sink bypasses."""

    authority_ids = {
        review_id
        for match in (subject_selection.matches if subject_selection else ())
        if match.predicate_id == predicate.id
        and (review_id := review_symbol_id(evidence.get(match.evidence_id)))
        is not None
    }
    authority_evidence_ids = {
        match.evidence_id
        for match in (subject_selection.matches if subject_selection else ())
        if match.predicate_id == predicate.id
    }
    uncertainty_declared = bool(
        authority_evidence_ids & uncertainty_evidence_ids
    )
    controlling = tuple(
        binding
        for binding in bindings
        if binding.evidence_id in evidence
        and _authority_controls_path(
            evidence[binding.evidence_id],
            evidence,
            authority_ids,
        )
    )
    controlled_sink_ids = {
        path_ids[-1]
        for binding in controlling
        if (
            path_ids := ordered_path_review_ids(
                evidence[binding.evidence_id],
                evidence,
            )
        )
    }
    bypasses = tuple(
        binding
        for binding in bindings
        if binding.evidence_id in evidence
        and (
            (
                binding.association == "structural_bridge"
                and not _authority_controls_path(
                    evidence[binding.evidence_id],
                    evidence,
                    authority_ids,
                )
            )
            or _path_branches_into_controlled_sink(
                evidence[binding.evidence_id],
                evidence,
                authority_ids,
                controlled_sink_ids,
            )
        )
    )
    if bypasses:
        return _predicate_result(
            claim,
            predicate,
            "contradicted",
            tuple(item.id for item in controlling),
            tuple(item.id for item in bypasses),
            (
                _reason(
                    "authority_bypass_observed",
                    "An observed executable path reaches an authority-controlled "
                    "sink without traversing the declared authority.",
                    bypasses,
                    tuple(evidence[item.evidence_id] for item in bypasses),
                ),
            ),
        )
    if controlling:
        path_reason = _reason(
            "authority_path_observed",
            "The declared authority occurs before a downstream consumer on an "
            "observed executable head path.",
            controlling,
            tuple(evidence[item.evidence_id] for item in controlling),
        )
        deferred = (
            structural_group.deferred_path_evidence_ids
            if structural_group is not None
            else ()
        )
        provider_incomplete = tuple(
            item
            for item in controlling
            if evidence[item.evidence_id].structural_traversal_coverage
            != "complete"
        )
        if deferred or provider_incomplete or uncertainty_declared:
            return _predicate_result(
                claim,
                predicate,
                "partial",
                tuple(item.id for item in controlling),
                (),
                (
                    path_reason,
                    *(
                        (
                            _reason(
                                "coverage_incomplete",
                                "Potential authority paths were deferred by the "
                                "structural closure or provider traversal safety "
                                "boundary; exclusivity is not proved.",
                                provider_incomplete,
                                facts=tuple(
                                    evidence[item_id]
                                    for item_id in dict.fromkeys(
                                        (
                                            *(
                                                item_id
                                                for item_id in deferred
                                                if item_id in evidence
                                            ),
                                            *(
                                                item.evidence_id
                                                for item in provider_incomplete
                                            ),
                                        )
                                    )
                                ),
                            ),
                        )
                        if deferred or provider_incomplete
                        else ()
                    ),
                    *(
                        (
                            _reason(
                                "uncertainty_context",
                                "An authored uncertainty references the same "
                                "canonical authority subject; exclusivity remains "
                                "unresolved.",
                            ),
                        )
                        if uncertainty_declared
                        else ()
                    ),
                ),
            )
        return _predicate_result(
            claim,
            predicate,
            "demonstrated",
            tuple(item.id for item in controlling),
            (),
            (path_reason,),
        )
    deferred = (
        structural_group.deferred_path_evidence_ids
        if structural_group is not None
        else ()
    )
    selected = tuple(
        item
        for item in bindings
        if item.association in {"provided_association", "exact_identifier"}
    )
    return _predicate_result(
        claim,
        predicate,
        "partial" if selected or deferred else "unverified",
        tuple(item.id for item in selected),
        (),
        (
            _reason(
                (
                    "coverage_incomplete"
                    if deferred
                    else "association_only"
                    if selected
                    else "no_binding"
                ),
                (
                    "Potential authority paths were deferred by the structural "
                    "closure safety boundary; control is not proved."
                    if deferred
                    else "The authority surface is observed, but no executable "
                    "head path proves that it controls a downstream consumer."
                    if selected
                    else "No canonical structural fact or executable consumer path "
                    "was associated with the declared authority."
                ),
                selected,
                tuple(
                    evidence[item_id]
                    for item_id in deferred
                    if item_id in evidence
                ),
            ),
        ),
    )


def _authority_controls_path(
    path: EvidenceItem,
    evidence: dict[str, EvidenceItem],
    authority_ids: set[str],
) -> bool:
    if not is_outgoing_executable_head_path(path):
        return False
    path_ids = ordered_path_review_ids(path, evidence)
    return bool(authority_ids & set(path_ids[:-1]))


def _path_branches_into_controlled_sink(
    path: EvidenceItem,
    evidence: dict[str, EvidenceItem],
    authority_ids: set[str],
    controlled_sink_ids: set[str],
) -> bool:
    if not controlled_sink_ids or not is_executable_head_path(path):
        return False
    for step in path.metadata["steps"]:
        if step.get("direction") != "incoming":
            continue
        source_id = review_symbol_id(evidence.get(step.get("source_evidence_id")))
        target_id = review_symbol_id(evidence.get(step.get("target_evidence_id")))
        if (
            source_id in controlled_sink_ids
            and target_id is not None
            and target_id not in authority_ids
        ):
            return True
    return False


def _assess_ordered_path_predicate(
    claim: TransformationClaim,
    predicate: TransformationPredicate,
    bindings: tuple[TransformationEvidenceBinding, ...],
    evidence: dict[str, EvidenceItem],
    structural_group: TransformationStructuralClosureGroup | None,
    *,
    head_sha: str,
) -> TransformationPredicateAssessment:
    path_bindings = tuple(
        binding
        for binding in bindings
        if binding.evidence_role == "structural_path"
        and _ordered_path_matches(
            predicate,
            evidence[binding.evidence_id],
            evidence,
        )
    )
    if predicate.expectation == "absent_head":
        if path_bindings:
            return _predicate_result(
                claim,
                predicate,
                "contradicted",
                (),
                tuple(item.id for item in path_bindings),
                (
                    _reason(
                        "closure_conflict_observed",
                        "A canonical head path contains every declared selector "
                        "in the forbidden order.",
                        path_bindings,
                        tuple(evidence[item.evidence_id] for item in path_bindings),
                    ),
                ),
            )
        return _unresolved_ordered_path(
            claim,
            predicate,
            structural_group,
            evidence,
        )

    if not path_bindings:
        return _unresolved_ordered_path(
            claim,
            predicate,
            structural_group,
            evidence,
        )

    path_reason = _reason(
        "exact_fact_observed",
        "A canonical structural path contains every declared selector in "
        "authored order on the expected revision.",
        path_bindings,
        tuple(evidence[item.evidence_id] for item in path_bindings),
    )
    if predicate.expectation != "verified_head":
        return _predicate_result(
            claim,
            predicate,
            "demonstrated",
            tuple(item.id for item in path_bindings),
            (),
            (path_reason,),
        )

    verification = tuple(
        item for item in bindings if item.evidence_role == "verification"
    )
    if not verification:
        return _predicate_result(
            claim,
            predicate,
            "partial",
            tuple(item.id for item in path_bindings),
            (),
            (
                path_reason,
                _reason(
                    "verification_incomplete",
                    "The ordered head topology is observed, but no exact "
                    "current-head verification is associated with this predicate.",
                ),
            ),
        )
    verified = _assess_verification(
        claim,
        verification,
        evidence,
        head_sha,
        require_success=True,
    )
    return _predicate_result(
        claim,
        predicate,
        verified.status,
        tuple(
            dict.fromkeys(
                (
                    *(item.id for item in path_bindings),
                    *verified.supporting_binding_ids,
                )
            )
        ),
        verified.contradicting_binding_ids,
        (path_reason, *verified.reasons),
    )


def _ordered_path_matches(
    predicate: TransformationPredicate,
    path: EvidenceItem,
    evidence: dict[str, EvidenceItem],
) -> bool:
    expected_revision = (
        "base" if predicate.expectation == "present_base" else "head"
    )
    if path.kind != "structural_path" or path.revision_side != expected_revision:
        return False
    path_items = tuple(
        evidence[item_id]
        for item_id in ordered_path_evidence_ids(path)
        if item_id in evidence
    )
    matching_predicate = (
        replace(predicate, expectation="present_head")
        if predicate.expectation == "absent_head"
        else predicate
    )
    cursor = 0
    for value in predicate.values:
        match_index = next(
            (
                index
                for index in range(cursor, len(path_items))
                if matches_transformation_selector(
                    matching_predicate,
                    value,
                    path_items[index],
                )
            ),
            None,
        )
        if match_index is None:
            return False
        cursor = match_index + 1
    return True


def _unresolved_ordered_path(
    claim: TransformationClaim,
    predicate: TransformationPredicate,
    structural_group: TransformationStructuralClosureGroup | None,
    evidence: dict[str, EvidenceItem],
) -> TransformationPredicateAssessment:
    deferred_ids = (
        structural_group.deferred_path_evidence_ids
        if structural_group is not None
        else ()
    )
    incomplete = bool(deferred_ids)
    return _predicate_result(
        claim,
        predicate,
        "partial" if incomplete else "unverified",
        (),
        (),
        (
            _reason(
                "coverage_incomplete" if incomplete else "no_binding",
                (
                    "Potential structural paths were deferred by the closure "
                    "safety boundary; the declared order was not proved."
                    if incomplete
                    else "No canonical structural path proves every declared "
                    "selector in authored order on the expected revision."
                ),
                facts=tuple(
                    evidence[item_id]
                    for item_id in deferred_ids
                    if item_id in evidence
                ),
            ),
        ),
    )


def _closure_fact_has_predicate(
    item: EvidenceItem,
    predicate: TransformationPredicate,
    plan: ClosureScanPlan | None,
) -> bool:
    if (
        item.closure_scan_result is None
        or plan is None
        or item.closure_scan_result.plan_id != plan.id
    ):
        return False
    return any(
        scan_predicate.source_predicate_id == predicate.id
        for scan_predicate in plan.predicates
    )


def _assess_closure_predicate(
    claim: TransformationClaim,
    predicate: TransformationPredicate,
    binding: TransformationEvidenceBinding,
    fact: EvidenceItem,
    plan: ClosureScanPlan,
) -> TransformationPredicateAssessment:
    result = fact.closure_scan_result
    if result is None:
        return _predicate_result(
            claim,
            predicate,
            "unverified",
            (),
            (),
            (
                _reason(
                    "coverage_incomplete",
                    "Closure evidence has no canonical scan result.",
                    (binding,),
                    (fact,),
                ),
            ),
        )
    observations = {item.revision_side: item for item in result.revisions}
    if plan.expectation == "transition":
        base = observations.get("base")
        head = observations.get("head")
        base_matches = _closure_matches(predicate, base, plan)
        head_matches = _closure_matches(predicate, head, plan)
        if (
            base is not None
            and base.state == "complete"
            and head is not None
            and head.state == "complete"
            and base_matches
            and not head_matches
        ):
            return _predicate_result(
                claim,
                predicate,
                "demonstrated",
                (binding.id,),
                (),
                (
                    _reason(
                        "closure_transition_observed",
                        "Complete base/head scans observed this exact surface in "
                        "base and its absence in head.",
                        (binding,),
                        (fact,),
                    ),
                ),
            )
        if head is not None and head.state == "complete" and head_matches:
            return _predicate_result(
                claim,
                predicate,
                "contradicted",
                (),
                (binding.id,),
                (
                    _reason(
                        "closure_conflict_observed",
                        "The exact removal predicate remains present in head.",
                        (binding,),
                        (fact,),
                    ),
                ),
            )
    elif predicate.expectation == "absent_head":
        head = observations.get("head")
        matches = _closure_matches(predicate, head, plan)
        if head is not None and head.state == "complete" and matches:
            return _predicate_result(
                claim,
                predicate,
                "contradicted",
                (),
                (binding.id,),
                (
                    _reason(
                        "closure_conflict_observed",
                        "A complete head scan found the exact surface that this "
                        "negative predicate requires absent.",
                        (binding,),
                        (fact,),
                    ),
                ),
            )
        if head is not None and head.state == "complete":
            return _predicate_result(
                claim,
                predicate,
                "demonstrated",
                (binding.id,),
                (),
                (
                    _reason(
                        "closure_absence_observed",
                        "A complete head scan found no exact surface selected by "
                        "this negative predicate.",
                        (binding,),
                        (fact,),
                    ),
                ),
            )
    incomplete = any(item.state != "complete" for item in result.revisions)
    return _predicate_result(
        claim,
        predicate,
        "partial" if incomplete else "unverified",
        (binding.id,),
        (),
        (
            _reason(
                "coverage_incomplete" if incomplete else "association_only",
                "Closure coverage or the exact revision transition is insufficient "
                "for this predicate.",
                (binding,),
                (fact,),
            ),
        ),
    )


def _closure_matches(
    predicate: TransformationPredicate,
    observation,
    plan: ClosureScanPlan,
) -> tuple:
    if observation is None:
        return ()
    scan_predicate_ids = {
        item.id
        for item in plan.predicates
        if item.source_predicate_id == predicate.id
    }
    surfaces = {
        "paths" if predicate.selector_kind == "repository_path" else "symbol_names"
    }
    return tuple(
        item
        for item in observation.matches
        if item.predicate_id in scan_predicate_ids
        and item.surface in surfaces
    )


def _aggregate_predicate_assessments(
    claim: TransformationClaim,
    assessments: tuple[TransformationPredicateAssessment, ...],
) -> TransformationClaimAssessment:
    statuses = tuple(item.status for item in assessments)
    if "contradicted" in statuses:
        status = "contradicted"
    elif statuses and all(item == "demonstrated" for item in statuses):
        status = "demonstrated"
    elif any(item in {"demonstrated", "partial"} for item in statuses):
        status = "partial"
    else:
        status = "unverified"
    supporting = tuple(
        dict.fromkeys(
            binding_id
            for item in assessments
            for binding_id in item.supporting_binding_ids
        )
    )
    contradicting = tuple(
        dict.fromkeys(
            binding_id
            for item in assessments
            for binding_id in item.contradicting_binding_ids
        )
    )
    reasons = tuple(
        reason
        for item in assessments
        for reason in item.reasons
    )
    return TransformationClaimAssessment(
        id=f"TAS:{claim.id}",
        claim_id=claim.id,
        status=status,
        supporting_binding_ids=supporting,
        contradicting_binding_ids=contradicting,
        reasons=reasons,
        predicate_assessments=assessments,
    )


def _predicate_result(
    claim: TransformationClaim,
    predicate: TransformationPredicate,
    status,
    supporting,
    contradicting,
    reasons,
) -> TransformationPredicateAssessment:
    return TransformationPredicateAssessment(
        id=f"TAP:{claim.id}:{predicate.id}",
        claim_id=claim.id,
        predicate_id=predicate.id,
        expectation=predicate.expectation,
        status=status,
        supporting_binding_ids=tuple(supporting),
        contradicting_binding_ids=tuple(contradicting),
        reasons=tuple(reasons),
    )


def _assess_closure(claim, binding, fact, plan):
    """Keep selector-free closure claims conservative without a second evaluator."""

    result = fact.closure_scan_result
    if result is None or plan is None:
        return _result(
            claim,
            "unverified",
            (),
            (),
            (
                _reason(
                    "coverage_incomplete",
                    "Closure evidence has no canonical scan plan or result.",
                    (binding,),
                ),
            ),
        )
    incomplete = any(item.state != "complete" for item in result.revisions)
    return _result(
        claim,
        "partial" if incomplete else "unverified",
        (binding,),
        (),
        (
            _reason(
                "coverage_incomplete" if incomplete else "association_only",
                "Closure evidence has no explicit target predicate to evaluate "
                "as a repository-wide conclusion.",
                (binding,),
                (fact,),
            ),
        ),
    )


def _assess_verification(
    claim,
    bindings,
    evidence,
    head_sha,
    *,
    require_success: bool = False,
):
    current = tuple(
        item for item in bindings
        if evidence[item.evidence_id].observed_head_sha == head_sha and head_sha
    )
    stale = tuple(item for item in bindings if item not in current)
    if not current:
        return _result(
            claim,
            "partial" if stale else "unverified",
            stale,
            (),
            (
                _reason(
                    "stale_verification",
                    "Associated verification does not belong to the reviewed head.",
                    stale,
                ),
            ),
        )
    failures = tuple(
        item for item in current
        if evidence[item.evidence_id].verification_conclusion in _FAILURE_CONCLUSIONS
    )
    if failures:
        status = (
            "contradicted"
            if require_success or _expects_success(claim.text)
            else "demonstrated"
        )
        reason = (
            _reason(
                "current_verification_failure",
                "Current-head verification completed with a failing conclusion "
                "that contradicts the claimed successful result.",
                failures,
            )
            if status == "contradicted"
            else _reason(
                "exact_fact_observed",
                "Current-head verification completed; the claim requires execution "
                "but does not assert success.",
                failures,
            )
        )
        return _result(
            claim,
            status,
            failures if status == "demonstrated" else (),
            failures if status == "contradicted" else (),
            (reason,),
        )
    successes = tuple(
        item for item in current
        if evidence[item.evidence_id].verification_status == "completed"
        and evidence[item.evidence_id].verification_conclusion in _SUCCESS_CONCLUSIONS
    )
    if successes:
        return _result(
            claim,
            "demonstrated",
            successes,
            (),
            (
                _reason(
                    "current_verification_success",
                    "Current-head verification completed successfully.",
                    successes,
                ),
            ),
        )
    return _result(
        claim,
        "partial",
        current,
        (),
        (
            _reason(
                "verification_incomplete",
                "Current-head verification is present but has no successful "
                "terminal conclusion.",
                current,
            ),
        ),
    )


def _reason(kind, detail, bindings=(), facts=()):
    return TransformationAssessmentReason(
        kind=kind,
        detail=detail,
        binding_ids=tuple(item.id for item in bindings),
        evidence_ids=tuple(item.id for item in facts),
    )


def _expects_success(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:success(?:ful(?:ly)?)?|succeed(?:s|ed)?|pass(?:es|ed)?|green)\b",
            text,
            re.IGNORECASE,
        )
    )


def _result(claim, status, supporting, contradicting, reasons):
    return TransformationClaimAssessment(
        id=f"TAS:{claim.id}",
        claim_id=claim.id,
        status=status,
        supporting_binding_ids=tuple(item.id for item in supporting),
        contradicting_binding_ids=tuple(item.id for item in contradicting),
        reasons=reasons,
    )
