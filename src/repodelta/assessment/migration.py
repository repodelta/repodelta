from __future__ import annotations

from dataclasses import replace

from repodelta.model.contracts import (
    TransformationAssessmentReason,
    TransformationClaimAssessment,
    TransformationContract,
)


def close_migration_assessments(
    contract: TransformationContract,
    assessments: tuple[TransformationClaimAssessment, ...],
) -> tuple[TransformationClaimAssessment, ...]:
    """Replace one migration parent with the conjunction of typed obligations."""

    parent_ids = contract.migration.general_claim_ids
    if not parent_ids:
        return assessments
    by_claim_id = {item.claim_id: item for item in assessments}
    component_groups = (
        (
            "activation",
            (*contract.authority_claim_ids, *contract.migration.producer_claim_ids),
        ),
        ("consumer migration", contract.migration.consumer_claim_ids),
        ("test migration", contract.migration.test_claim_ids),
        ("legacy removal", contract.removal_claim_ids),
        ("completion condition", contract.completion_condition_claim_ids),
    )
    component_ids = tuple(
        dict.fromkeys(
            claim_id
            for _, claim_ids in component_groups
            for claim_id in claim_ids
        )
    )
    components = tuple(by_claim_id[claim_id] for claim_id in component_ids)
    if len(parent_ids) != 1:
        replacements = {
            parent_id: _result(
                by_claim_id[parent_id],
                components,
                "unverified",
                "migration_scope_ambiguous",
                "Multiple migration parent claims have no typed ownership boundary; "
                "component obligations were not assigned across parents.",
            )
            for parent_id in parent_ids
        }
    else:
        missing = tuple(name for name, claim_ids in component_groups if not claim_ids)
        conflicts = tuple(item for item in components if item.status == "contradicted")
        incomplete = tuple(item for item in components if item.status != "demonstrated")
        parent = by_claim_id[parent_ids[0]]
        if conflicts:
            replacement = _result(
                parent,
                components,
                "contradicted",
                "migration_component_conflict",
                "At least one declared migration obligation is contradicted: "
                + ", ".join(item.claim_id for item in conflicts),
            )
        elif missing or incomplete:
            has_observation = any(
                item.status in {"demonstrated", "partial"} for item in components
            )
            details = (
                *(f"missing {name}" for name in missing),
                *(f"{item.claim_id} is {item.status}" for item in incomplete),
            )
            replacement = _result(
                parent,
                components,
                "partial" if has_observation else "unverified",
                "migration_component_incomplete",
                "Migration closure is incomplete: " + "; ".join(details),
            )
        else:
            replacement = _result(
                parent,
                components,
                "demonstrated",
                "migration_closure_observed",
                "Activation, consumer migration, test migration, legacy removal, "
                "and current-head completion are all demonstrated.",
            )
        replacements = {parent.claim_id: replacement}
    return tuple(replacements.get(item.claim_id, item) for item in assessments)


def _result(
    parent: TransformationClaimAssessment,
    components: tuple[TransformationClaimAssessment, ...],
    status,
    reason_kind,
    detail: str,
) -> TransformationClaimAssessment:
    supporting = tuple(
        dict.fromkeys(
            binding_id
            for item in components
            for binding_id in item.supporting_binding_ids
        )
    )
    contradicting = tuple(
        dict.fromkeys(
            binding_id
            for item in components
            for binding_id in item.contradicting_binding_ids
        )
    )
    return replace(
        parent,
        status=status,
        supporting_binding_ids=supporting,
        contradicting_binding_ids=contradicting,
        component_claim_ids=tuple(item.claim_id for item in components),
        reasons=(TransformationAssessmentReason(kind=reason_kind, detail=detail),),
    )
