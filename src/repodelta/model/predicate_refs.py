from __future__ import annotations

import re
from typing import Literal

from repodelta.model.contracts import (
    AssociationSignature,
    EvidenceItem,
    TransformationPredicate,
    canonical_verification_name,
)

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")

TransformationSelectorMatchKind = Literal[
    "qualified_symbol",
    "symbol_name",
    "repository_path",
    "verification_name",
]
TransformationSelectorResolution = Literal["matched", "no_match", "ambiguous"]


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
    """Match one typed selector against one fact on its declared revision.

    This remains the single-fact predicate used by assessment. Callers that
    admit structural subjects must use ``resolve_transformation_selector`` so
    that an unqualified symbol selector cannot silently select several
    changed identities.
    """

    return _single_transformation_selector_match_kind(
        predicate,
        selector_value,
        item,
    ) is not None


def resolve_transformation_selector(
    predicate: TransformationPredicate,
    selector_value: str,
    items: tuple[EvidenceItem, ...] | list[EvidenceItem],
) -> tuple[
    tuple[EvidenceItem, ...],
    TransformationSelectorResolution,
    TransformationSelectorMatchKind | None,
]:
    """Resolve one selector against a candidate universe conservatively.

    Repository paths are explicit scopes and may intentionally select several
    changed symbols. Symbol selectors, however, are direct-admission roots:
    an unqualified name must resolve to exactly one canonical changed identity.
    Qualified matches take precedence over leaf-name matches; a tie is
    ambiguous and fails closed.
    """

    candidates = tuple(
        (
            item,
            _single_transformation_selector_match_kind(
                predicate,
                selector_value,
                item,
            ),
        )
        for item in items
    )
    matches = tuple(
        (item, match_kind)
        for item, match_kind in candidates
        if match_kind is not None
    )
    if not matches:
        return (), "no_match", None
    if predicate.selector_kind == "repository_path":
        return (
            tuple(item for item, _ in matches),
            "matched",
            "repository_path",
        )
    qualified = tuple(
        item for item, match_kind in matches if match_kind == "qualified_symbol"
    )
    if qualified:
        if len(qualified) == 1:
            return qualified, "matched", "qualified_symbol"
        return (), "ambiguous", None
    verification = tuple(
        item for item, match_kind in matches if match_kind == "verification_name"
    )
    if verification:
        if len(verification) == 1:
            return verification, "matched", "verification_name"
        return (), "ambiguous", None
    named = tuple(
        item for item, match_kind in matches if match_kind == "symbol_name"
    )
    if len(named) == 1:
        return named, "matched", "symbol_name"
    return (), "ambiguous", None


def _single_transformation_selector_match_kind(
    predicate: TransformationPredicate,
    selector_value: str,
    item: EvidenceItem,
) -> TransformationSelectorMatchKind | None:
    """Classify one fact without deciding whether a selector is unique."""

    if predicate.selector_kind == "repository_path":
        selector_path = _normalize_path(selector_value).rstrip("/")
        return "repository_path" if any(
            path == selector_path or path.startswith(f"{selector_path}/")
            for path in _candidate_paths(predicate, item)
        ) else None
    if item.role == "verification":
        identity = item.verification_identity
        selector_name = canonical_verification_name(selector_value)
        return "verification_name" if (
            selector_name
            and identity is not None
            and selector_name == identity.name
        ) else None
    selector_text = _normalize_symbol_selector(selector_value)
    if not selector_text:
        return None
    signature = _candidate_signature(predicate, item)
    metadata = item.metadata
    if predicate.expectation in {"present_base", "absent_head"}:
        side_metadata_defined = "base_qualified_name" in metadata
        if (
            side_metadata_defined
            and metadata.get("base_qualified_name") is None
        ):
            return None
        qualified_name = metadata.get("base_qualified_name")
        name = metadata.get("base_name")
    elif predicate.expectation in {"present_head", "verified_head"}:
        side_metadata_defined = "head_qualified_name" in metadata
        if (
            side_metadata_defined
            and metadata.get("head_qualified_name") is None
        ):
            return None
        qualified_name = metadata.get("head_qualified_name")
        name = metadata.get("head_name")
    else:
        side_metadata_defined = False
        qualified_name = metadata.get("qualified_name")
        name = metadata.get("name")
    normalized_qualified_name = (
        _normalize_symbol_selector(qualified_name)
        if isinstance(qualified_name, str)
        else ""
    )
    normalized_name = (
        _normalize_symbol_selector(name)
        if isinstance(name, str)
        else ""
    )
    selector_is_qualified = _is_qualified_symbol(selector_text)
    if selector_is_qualified:
        if normalized_qualified_name == selector_text:
            return "qualified_symbol"
        if side_metadata_defined:
            return None
        compact_selector = _compact_symbol(selector_text)
        if compact_selector in signature.identifiers and compact_selector != (
            _compact_symbol(selector_text.rsplit(".", 1)[-1])
        ):
            return "qualified_symbol"
        return None
    if normalized_name == selector_text:
        return "symbol_name"
    if side_metadata_defined:
        return None
    selector_keys = _selector_keys(selector_value)
    if selector_keys & {*signature.identifiers, *signature.tokens}:
        return "symbol_name"
    return None


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
    leaf = re.split(r"[.:]", explicit)[-1]
    normalized = re.sub(r"[^A-Za-z0-9_]", "", leaf).casefold()
    return frozenset(
        {
            *identifier_keys(explicit),
            *(item for item in (normalized,) if len(item) >= 3),
        }
    )


def _normalize_symbol_selector(value: str) -> str:
    explicit = value.strip().removesuffix("()").strip()
    explicit = re.sub(r"\s+", "", explicit)
    return explicit.replace("::", ".").casefold()


def _compact_symbol(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _is_qualified_symbol(value: str) -> bool:
    return "." in value
