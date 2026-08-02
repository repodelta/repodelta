from __future__ import annotations

import re
from typing import Literal

from prismcode.model.contracts import (
    ClosureSelectorKind,
    ClosureScanPlan,
    ClosureScanPlanSet,
    ClosureScanPredicate,
    ClosureScanSelector,
    Requirement,
    TransformationClaim,
    TransformationContract,
    TransformationPredicate,
)

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

    predicates_by_claim = transformation_contract.predicates.by_claim_id()
    eligible_claims = (
        *transformation_contract.by_kind("removal"),
        *(
            item
            for item in transformation_contract.by_kind("completion_condition")
            if _negative_completion_is_executable(
                item,
                predicates_by_claim.get(item.id, ()),
            )
        ),
    )
    statements: tuple[Requirement | TransformationClaim, ...] = (
        *guardrails,
        *eligible_claims,
    )
    plans = ClosureScanPlanSet(
        plans=tuple(
            _plan(
                statement,
                predicates_by_claim.get(statement.id, ()),
            )
            for statement in statements
        )
    )
    plans.validate_consistency(statements)
    return plans


def _negative_completion_is_executable(
    claim: TransformationClaim,
    predicates: tuple[TransformationPredicate, ...],
) -> bool:
    return bool(
        _NEGATIVE_COMPLETION.search(claim.text)
        and predicates
    )


def _plan(
    statement: Requirement | TransformationClaim,
    authored_predicates: tuple[TransformationPredicate, ...],
) -> ClosureScanPlan:
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
        predicates=_predicates(
            plan_id,
            _inferred_candidates(statement.text)
            if isinstance(statement, Requirement)
            else _authored_candidates(authored_predicates),
        ),
        sources=statement.sources,
    )


SelectorCandidate = tuple[
    Literal["target", "path_scope"],
    ClosureSelectorKind,
    str,
]


def _predicates(
    plan_id: str,
    candidates: list[SelectorCandidate],
) -> tuple[ClosureScanPredicate, ...]:
    scopes = tuple(
        value for role, kind, value in candidates
        if role == "path_scope" and kind == "path"
    )
    targets = tuple(
        (kind, value) for role, kind, value in candidates
        if role == "target" and (not scopes or kind != "phrase")
    )
    unique_targets = tuple(dict.fromkeys(targets))
    unique_scopes = tuple(dict.fromkeys(scopes))
    return tuple(
        ClosureScanPredicate(
            id=f"{plan_id}:predicate:{index}",
            target=ClosureScanSelector(
                id=f"{plan_id}:predicate:{index}:target",
                kind=kind,
                value=value,
            ),
            path_scopes=tuple(
                ClosureScanSelector(
                    id=f"{plan_id}:predicate:{index}:path_scope:{scope_index}",
                    kind="path",
                    value=scope,
                )
                for scope_index, scope in enumerate(unique_scopes, start=1)
            ),
        )
        for index, (kind, value) in enumerate(unique_targets, start=1)
    )


def _authored_candidates(
    predicates: tuple[TransformationPredicate, ...],
) -> list[SelectorCandidate]:
    return [
        (
            predicate.role,
            "path" if predicate.selector_kind == "repository_path" else "identifier",
            predicate.values[0],
        )
        for predicate in predicates
        if predicate.selector_kind != "ordered_path"
    ]


def _inferred_candidates(text: str) -> list[SelectorCandidate]:
    candidates: list[SelectorCandidate] = []
    for clause in _CLAUSE_BREAK.split(text):
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
            candidates.extend(
                ("target", _selector_kind(item), item) for item in identifiers
            )
        elif len(words) >= 2:
            candidates.append(
                (
                    "target",
                    "phrase",
                    " ".join(item.casefold() for item in words[:4]),
                )
            )
    return candidates


def _selector_kind(value: str) -> ClosureSelectorKind:
    if "/" in value or "\\" in value:
        return "path"
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.:-]*", value):
        return "identifier"
    return "phrase"
