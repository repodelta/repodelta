from __future__ import annotations

import re
from collections import Counter

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
    *,
    distinctive_terms: frozenset[str],
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
    return text_reasons(
        source.text,
        target.text,
        distinctive_terms=distinctive_terms,
    )


def evidence_reasons(
    source: ReviewStatement,
    target: AssociationSignature,
    *,
    distinctive_terms: frozenset[str],
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
    discriminative = tuple(
        item for item in overlap if item in distinctive_terms
    )
    if len(overlap) >= 2 and discriminative:
        return (
            AssociationReason(
                kind="distinctive_phrase",
                detail=(
                    "A review-discriminative term and at least one supporting "
                    "term occur in both texts."
                ),
                matched_terms=discriminative,
            ),
        )
    return ()


def text_reasons(
    source_text: str,
    target_text: str,
    *,
    distinctive_terms: frozenset[str],
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
    discriminative = tuple(
        item for item in overlap if item in distinctive_terms
    )
    if len(overlap) >= 2 and discriminative:
        return (
            AssociationReason(
                kind="distinctive_phrase",
                detail=(
                    "A review-discriminative term and at least one supporting "
                    "term occur in both texts."
                ),
                matched_terms=discriminative,
            ),
        )
    return ()


def distinctive_text_terms(
    documents: tuple[tuple[str, str], ...],
) -> dict[str, frozenset[str]]:
    return _distinctive_terms(
        tuple((key, semantic_tokens(text)) for key, text in documents)
    )


def distinctive_signature_terms(
    documents: tuple[tuple[str, AssociationSignature], ...],
) -> dict[str, frozenset[str]]:
    return _distinctive_terms(
        tuple((key, frozenset(signature.tokens)) for key, signature in documents)
    )


def _distinctive_terms(
    documents: tuple[tuple[str, frozenset[str]], ...],
) -> dict[str, frozenset[str]]:
    """Return boolean corpus authority over unique semantic meanings."""

    unique_meanings = tuple(dict.fromkeys(tokens for _, tokens in documents))
    threshold = max(1, len(unique_meanings) // 2)
    frequencies = Counter(
        token for meaning in unique_meanings for token in meaning
    )
    return {
        key: frozenset(
            token for token in tokens if frequencies[token] <= threshold
        )
        for key, tokens in documents
    }
