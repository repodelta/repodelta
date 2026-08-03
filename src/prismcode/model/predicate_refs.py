from __future__ import annotations

import re

from prismcode.model.contracts import (
    AssociationSignature,
    EvidenceItem,
    TransformationPredicate,
)

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")


def identifier_keys(value: str) -> frozenset[str]:
    """Return canonical identifier keys shared by fact and routing stages."""

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


def matches_transformation_selector(
    predicate: TransformationPredicate,
    selector_value: str,
    item: EvidenceItem,
) -> bool:
    """Match one typed selector against one fact on its declared revision."""

    if predicate.selector_kind == "repository_path":
        selector_path = _normalize_path(selector_value).rstrip("/")
        return any(
            path == selector_path or path.startswith(f"{selector_path}/")
            for path in _candidate_paths(predicate, item)
        )
    selector_keys = _selector_keys(selector_value)
    if not selector_keys:
        return False
    signature = _candidate_signature(predicate, item)
    if item.role == "verification":
        exact = _normalized_selector_key(selector_value)
        return exact in {*signature.identifiers, *signature.tokens}
    return bool(selector_keys & {*signature.identifiers, *signature.tokens})


def _candidate_signature(
    predicate: TransformationPredicate,
    item: EvidenceItem,
) -> AssociationSignature:
    if predicate.expectation in {"present_base", "absent_head"}:
        return item.base_signature
    if predicate.expectation in {"present_head", "verified_head"}:
        return item.head_signature
    return AssociationSignature(
        identifiers=tuple(
            sorted(
                {
                    *item.base_signature.identifiers,
                    *item.head_signature.identifiers,
                }
            )
        ),
        tokens=(),
    )


def _candidate_paths(
    predicate: TransformationPredicate,
    item: EvidenceItem,
) -> frozenset[str]:
    metadata = item.metadata
    if predicate.expectation in {"present_base", "absent_head"}:
        values = (metadata.get("base_path"),)
    elif predicate.expectation in {"present_head", "verified_head"}:
        values = (metadata.get("head_path"),)
    else:
        values = (
            metadata.get("path"),
            metadata.get("base_path"),
            metadata.get("head_path"),
        )
    return frozenset(
        _normalize_path(value)
        for value in values
        if isinstance(value, str) and value.strip()
    )


def _normalize_path(value: str) -> str:
    return value.strip().replace("\\", "/").removeprefix("./")


def _selector_keys(value: str) -> frozenset[str]:
    explicit = value.strip().removesuffix("()")
    normalized = _normalized_selector_key(value)
    return frozenset(
        {
            *identifier_keys(explicit),
            *(item for item in (normalized,) if len(item) >= 3),
        }
    )


def _normalized_selector_key(value: str) -> str:
    explicit = value.strip().removesuffix("()")
    leaf = re.split(r"[.:]", explicit)[-1]
    return re.sub(r"[^A-Za-z0-9_]", "", leaf).casefold()
