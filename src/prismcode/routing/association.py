from __future__ import annotations

import re

from prismcode.model.contracts import AssociationReason, ReviewStatement
from prismcode.facts.lexical import semantic_tokens

_REFERENCE_RE = re.compile(r"\b(?:R|G|AC|REQ)[-_ ]?\d+\b", re.IGNORECASE)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")


def statement_reasons(
    source: ReviewStatement,
    target: ReviewStatement,
) -> tuple[AssociationReason, ...]:
    """Associate authored statements; only this authority boundary accepts R/G IDs."""

    references = {
        value.replace("_", "").replace("-", "").replace(" ", "").casefold()
        for value in _REFERENCE_RE.findall(target.text)
    }
    focus_reference = source.id.replace("_", "").replace("-", "").casefold()
    if (
        target.authority in {"pr_description", "provided"}
        and focus_reference in references
    ):
        return (
            AssociationReason(
                kind="explicit_reference",
                detail=f"The authored claim explicitly references {source.id}.",
                matched_terms=(source.id,),
            ),
        )
    return text_reasons(source.text, target.text)


def evidence_reasons(
    source: ReviewStatement,
    target_text: str,
) -> tuple[AssociationReason, ...]:
    """Associate repository text without interpreting local R1/G1 tokens."""

    return text_reasons(source.text, target_text)


def text_reasons(
    source_text: str,
    target_text: str,
) -> tuple[AssociationReason, ...]:
    identifiers = tuple(
        sorted(identifier_keys(source_text) & identifier_keys(target_text))
    )
    if identifiers:
        return (
            AssociationReason(
                kind="exact_identifier",
                detail="A distinctive identifier occurs in both texts.",
                matched_terms=identifiers,
            ),
        )
    overlap = tuple(sorted(semantic_tokens(source_text) & semantic_tokens(target_text)))
    if len(overlap) >= 2:
        return (
            AssociationReason(
                kind="distinctive_phrase",
                detail="At least two meaningful terms occur in both texts.",
                matched_terms=overlap,
            ),
        )
    return ()


def identifier_keys(value: str) -> frozenset[str]:
    keys: set[str] = set()
    for token in _WORD_RE.findall(value):
        has_shape = "_" in token or any(char.isupper() for char in token[1:])
        if not has_shape:
            continue
        raw_parts = [part.casefold() for part in token.split("_") if part]
        parts = [part for part in raw_parts if len(part) >= 3 or part.isdigit()]
        collapsed = "".join(parts)
        if len(collapsed) >= 5:
            keys.add(collapsed)
        for index in range(1, len(parts)):
            suffix = "".join(parts[index:])
            if len(suffix) >= 5:
                keys.add(suffix)
    return frozenset(keys)
