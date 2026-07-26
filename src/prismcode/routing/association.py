from __future__ import annotations

import re

from prismcode.model.contracts import (
    AssociationReason,
    AssociationSignature,
    ReviewStatement,
)
from prismcode.facts.lexical import identifier_keys, semantic_tokens

_REFERENCE_RE = re.compile(r"\b(?:R|G|AC|REQ)[-_ ]?\d+\b", re.IGNORECASE)


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
    target: AssociationSignature,
) -> tuple[AssociationReason, ...]:
    """Associate repository text without interpreting local R1/G1 tokens."""

    identifiers = tuple(
        sorted(identifier_keys(source.text) & set(target.identifiers))
    )
    if identifiers:
        return (
            AssociationReason(
                kind="exact_identifier",
                detail="A distinctive identifier occurs in both texts.",
                matched_terms=identifiers,
            ),
        )
    overlap = tuple(
        sorted(semantic_tokens(source.text) & set(target.tokens))
    )
    if len(overlap) >= 2:
        return (
            AssociationReason(
                kind="distinctive_phrase",
                detail="At least two meaningful terms occur in both texts.",
                matched_terms=overlap,
            ),
        )
    return ()

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
