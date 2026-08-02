from __future__ import annotations

import re

from prismcode.model.contracts import (
    ClosureScanPlan,
    ClosureScanPlanSet,
    EvidenceCatalog,
    EvidenceItem,
    TransformationAlignment,
    TransformationAssessment,
    TransformationAssessmentReason,
    TransformationClaim,
    TransformationClaimAssessment,
    TransformationContract,
    TransformationEvidenceBinding,
)

_PRODUCTION_PROFILES = frozenset(
    {"production", "workflow", "configuration", "dependency", "schema", "unknown"}
)
_GLOBAL_CLAIM_KINDS = frozenset(
    {
        "selected_region",
        "input_boundary",
        "output_boundary",
        "boundary",
        "authority",
        "production_path",
    }
)
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
) -> TransformationAssessment:
    """Assess aligned facts without inferring acceptance or mergeability."""

    evidence = evidence_catalog.by_id()
    bindings = alignment.by_claim_id()
    plans = closure_scan_plans.by_statement_id()
    assessments = tuple(
        _assess_claim(
            claim,
            bindings.get(claim.id, ()),
            evidence,
            plans.get(claim.id),
            head_sha=head_sha,
        )
        for claim in contract.claims
    )
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
) -> TransformationClaimAssessment:
    if claim.kind == "uncertainty":
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
        and claim.kind not in _GLOBAL_CLAIM_KINDS
        and claim.kind != "completion_condition"
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


def _assess_closure(claim, binding, fact, plan):
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
    exact_predicates = tuple(
        item for item in plan.predicates
        if item.target.kind in {"identifier", "path"}
    )
    if not exact_predicates or len(exact_predicates) != len(plan.predicates):
        return _result(
            claim,
            "partial",
            (binding,),
            (),
            (
                _reason(
                    "association_only",
                    "Phrase-only or incomplete closure predicates cannot prove an exact "
                    "repository-wide transition or absence.",
                    (binding,),
                    (fact,),
                ),
            ),
        )
    observations = {item.revision_side: item for item in result.revisions}

    def strong(side: str):
        observation = observations.get(side)
        if observation is None:
            return {}
        result = {}
        for predicate in exact_predicates:
            surface = (
                "paths" if predicate.target.kind == "path" else "symbol_names"
            )
            result[predicate.id] = tuple(
                item for item in observation.matches
                if item.predicate_id == predicate.id
                and item.surface == surface
                and (
                    predicate.path_scopes
                    or item.profile in _PRODUCTION_PROFILES
                )
            )
        return result

    head = observations.get("head")
    base = observations.get("base")
    head_matches = strong("head")
    base_matches = strong("base")
    head_conflicts = tuple(
        item for matches in head_matches.values() for item in matches
    )
    base_support = tuple(
        item for matches in base_matches.values() for item in matches
    )
    if head is not None and head.state == "complete" and head_conflicts:
        return _result(
            claim,
            "contradicted",
            (),
            (binding,),
            (
                _reason(
                    "closure_conflict_observed",
                    "A complete head scan found the exact production surface "
                    "that the claim requires absent.",
                    (binding,),
                    (fact,),
                ),
            ),
        )
    if result.expectation == "transition":
        complete_transition = (
            base is not None
            and base.state == "complete"
            and head is not None
            and head.state == "complete"
            and all(base_matches.get(item.id) for item in exact_predicates)
            and not head_conflicts
        )
        if complete_transition:
            return _result(
                claim,
                "demonstrated",
                (binding,),
                (),
                (
                    _reason(
                        "closure_transition_observed",
                        "Complete base/head scans observed the exact production "
                        "surface in base and its absence in head.",
                        (binding,),
                        (fact,),
                    ),
                ),
            )
    elif head is not None and head.state == "complete" and not head_conflicts:
        return _result(
            claim,
            "demonstrated",
            (binding,),
            (),
            (
                _reason(
                    "closure_absence_observed",
                    "A complete head scan found no exact production surface "
                    "selected by the absence claim.",
                    (binding,),
                    (fact,),
                ),
            ),
        )
    incomplete = any(item.state != "complete" for item in result.revisions)
    return _result(
        claim,
        "partial" if incomplete or base_support else "unverified",
        (binding,),
        (),
        (
            _reason(
                "coverage_incomplete" if incomplete else "association_only",
                "Closure scan coverage or exact revision transition is "
                "insufficient for a repository-wide conclusion.",
                (binding,),
                (fact,),
            ),
        ),
    )


def _assess_verification(claim, bindings, evidence, head_sha):
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
        status = "contradicted" if _expects_success(claim.text) else "demonstrated"
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
