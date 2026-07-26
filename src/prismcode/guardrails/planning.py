from __future__ import annotations

from prismcode.model.contracts import (
    GuardrailScanPlan,
    GuardrailScanPlanSet,
    Requirement,
)


def compile_guardrail_scan_plans(
    guardrails: tuple[Requirement, ...],
) -> GuardrailScanPlanSet:
    """Compile one conservative, conclusion-free repository plan per G."""

    plans = GuardrailScanPlanSet(
        plans=tuple(
            GuardrailScanPlan(
                id=f"GSP:{guardrail.id}",
                guardrail_id=guardrail.id,
                query_text=guardrail.text,
                sources=guardrail.sources,
            )
            for guardrail in guardrails
        )
    )
    plans.validate_consistency(guardrails)
    return plans
