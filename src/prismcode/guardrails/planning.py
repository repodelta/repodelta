from __future__ import annotations

import re

from prismcode.model.contracts import (
    GuardrailScanPlan,
    GuardrailScanPlanSet,
    GuardrailScanSelector,
    Requirement,
)

_EXPLICIT_SELECTOR = re.compile(r"`([^`\n]+)`|[\"“]([^\"”\n]+)[\"”]")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_.:/-]*")
_CLAUSE_BREAK = re.compile(
    r"\s*(?:[,;，；]|\bor\b|\band\b|\bwithout\b|\bnor\b)\s*",
    re.IGNORECASE,
)
_EDGE_WORDS = {
    "a",
    "add",
    "an",
    "any",
    "be",
    "do",
    "does",
    "executing",
    "defining",
    "declaring",
    "emitting",
    "introduce",
    "keep",
    "must",
    "no",
    "not",
    "remain",
    "remains",
    "the",
    "to",
}


def _selectors(plan_id: str, text: str) -> tuple[GuardrailScanSelector, ...]:
    candidates: list[tuple[str, str]] = []
    for match in _EXPLICIT_SELECTOR.finditer(text):
        value = next(item for item in match.groups() if item is not None).strip()
        kind = (
            "identifier"
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.:/-]*", value)
            else "phrase"
        )
        candidates.append((kind, value))
    without_explicit = _EXPLICIT_SELECTOR.sub(" ", text)
    for clause in _CLAUSE_BREAK.split(without_explicit):
        words = [
            item.casefold().strip(".:/-")
            for item in _WORD.findall(clause)
            if item.strip(".:/-")
        ]
        while words and words[0] in _EDGE_WORDS:
            words.pop(0)
        while words and words[-1] in _EDGE_WORDS:
            words.pop()
        if len(words) >= 2:
            candidates.append(("phrase", " ".join(words[:4])))
        elif words and any(mark in words[0] for mark in ("_", ".", "/", "-")):
            candidates.append(("identifier", words[0]))
    unique = tuple(dict.fromkeys(candidates))
    return tuple(
        GuardrailScanSelector(
            id=f"{plan_id}:selector:{index}",
            kind=kind,
            value=value,
        )
        for index, (kind, value) in enumerate(unique, start=1)
    )


def compile_guardrail_scan_plans(
    guardrails: tuple[Requirement, ...],
) -> GuardrailScanPlanSet:
    """Compile one conservative, conclusion-free repository plan per G."""

    plans = GuardrailScanPlanSet(
        plans=tuple(_plan(guardrail) for guardrail in guardrails)
    )
    plans.validate_consistency(guardrails)
    return plans


def _plan(guardrail: Requirement) -> GuardrailScanPlan:
    plan_id = f"GSP:{guardrail.id}"
    selectors = _selectors(plan_id, guardrail.text)
    return GuardrailScanPlan(
        id=plan_id,
        guardrail_id=guardrail.id,
        query_text=guardrail.text,
        surfaces=(
            "paths",
            "file_content",
            "symbol_names",
        ),
        selectors=selectors,
        sources=guardrail.sources,
    )
