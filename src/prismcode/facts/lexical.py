from __future__ import annotations

import re

from prismcode.model.contracts import AssociationSignature

_TOKEN_RE = re.compile(r"[a-z][a-z0-9_]{2,}", re.IGNORECASE)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")
_STOP_WORDS = {
    "acceptance",
    "artifact",
    "behavior",
    "change",
    "changes",
    "compact",
    "current",
    "debug",
    "each",
    "existing",
    "exports",
    "from",
    "implementation",
    "into",
    "makes",
    "normal",
    "possible",
    "report",
    "requirement",
    "reused",
    "summary",
    "that",
    "this",
    "through",
    "true",
    "without",
    "with",
}


def semantic_tokens(value: str) -> frozenset[str]:
    """Return deterministic retrieval tokens shared by every lexical stage."""

    result: set[str] = set()
    for raw_token in _TOKEN_RE.findall(value):
        token = raw_token.casefold()
        candidates = (token, *token.split("_"))
        result.update(
            candidate
            for candidate in candidates
            if len(candidate) >= 4 and candidate not in _STOP_WORDS
        )
    return frozenset(result)


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


def association_signature(*values: str) -> AssociationSignature:
    return AssociationSignature(
        identifiers=tuple(
            sorted({item for value in values for item in identifier_keys(value)})
        ),
        tokens=tuple(
            sorted({item for value in values for item in semantic_tokens(value)})
        ),
    )


def merge_signatures(*values: AssociationSignature) -> AssociationSignature:
    return AssociationSignature(
        identifiers=tuple(
            sorted({item for value in values for item in value.identifiers})
        ),
        tokens=tuple(sorted({item for value in values for item in value.tokens})),
    )
