from __future__ import annotations

import re

from prismcode.model.contracts import (
    ClosureScanPlan,
    ClosureScanPlanSet,
    ClosureScanSelector,
    Requirement,
    TransformationClaim,
    TransformationContract,
)

_EXPLICIT_SELECTOR = re.compile(r"`([^`\n]+)`|[\"“]([^\"”\n]+)[\"”]")
_NEGATIVE_COMPLETION = re.compile(
    r"\b(?:no|not|without|absent|remove[sd]?|deleted?|eliminated?|"
    r"must\s+not|does\s+not|do\s+not)\b",
    re.IGNORECASE,
)
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_.:/-]*")
_CLAUSE_BREAK = re.compile(
    r"\s*(?:[,;，；]|\bor\b|\band\b|\bwithout\b|\bnor\b)\s*",
    re.IGNORECASE,
)
_EDGE_WORDS = {
    "a", "add", "an", "any", "be", "do", "does", "executing",
    "defining", "declaring", "emitting", "introduce", "keep", "must",
    "no", "not", "remain", "remains", "the", "to",
}


def compile_closure_scan_plans(
    guardrails: tuple[Requirement, ...],
    transformation_contract: TransformationContract = TransformationContract(),
) -> ClosureScanPlanSet:
    """Compile typed scan intent without treating source claims as evidence."""

    eligible_claims = (
        *transformation_contract.by_kind("removal"),
        *(
            item
            for item in transformation_contract.by_kind("completion_condition")
            if _negative_completion_is_executable(item)
        ),
    )
    statements: tuple[Requirement | TransformationClaim, ...] = (
        *guardrails,
        *eligible_claims,
    )
    plans = ClosureScanPlanSet(
        plans=tuple(_plan(statement) for statement in statements)
    )
    plans.validate_consistency(statements)
    return plans


def _negative_completion_is_executable(claim: TransformationClaim) -> bool:
    return bool(
        _NEGATIVE_COMPLETION.search(claim.text)
        and _EXPLICIT_SELECTOR.search(claim.text)
    )


def _plan(statement: Requirement | TransformationClaim) -> ClosureScanPlan:
    statement_kind = (
        "guardrail"
        if isinstance(statement, Requirement)
        else statement.kind
    )
    plan_id = f"CSP:{statement.id}"
    return ClosureScanPlan(
        id=plan_id,
        statement_id=statement.id,
        statement_kind=statement_kind,
        expectation="transition" if statement_kind == "removal" else "absence",
        query_text=statement.text,
        revision_sides=(
            ("base", "head") if statement_kind == "removal" else ("head",)
        ),
        surfaces=("paths", "file_content", "symbol_names"),
        selectors=_selectors(plan_id, statement.text),
        sources=statement.sources,
    )


def _selectors(plan_id: str, text: str) -> tuple[ClosureScanSelector, ...]:
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
            item.strip(".,;:()[]{}")
            for item in _WORD.findall(clause)
            if item.strip(".,;:()[]{}")
        ]
        while words and words[0].casefold() in _EDGE_WORDS:
            words.pop(0)
        while words and words[-1].casefold() in _EDGE_WORDS:
            words.pop()
        identifiers = [
            word
            for word in words
            if any(mark in word for mark in ("_", ".", "/", "-"))
            or bool(re.search(r"[a-z][A-Z]", word))
        ]
        if identifiers:
            candidates.extend(("identifier", item) for item in identifiers)
        elif len(words) >= 2:
            candidates.append(
                ("phrase", " ".join(item.casefold() for item in words[:4]))
            )
    return tuple(
        ClosureScanSelector(
            id=f"{plan_id}:selector:{index}",
            kind=kind,
            value=value,
        )
        for index, (kind, value) in enumerate(dict.fromkeys(candidates), start=1)
    )
