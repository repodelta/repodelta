from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-z][a-z0-9_]{2,}", re.IGNORECASE)
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
