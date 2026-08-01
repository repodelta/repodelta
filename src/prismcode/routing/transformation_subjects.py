from __future__ import annotations

import re

from prismcode.facts.lexical import identifier_keys
from prismcode.model.contracts import (
    AssociationSignature,
    EvidenceCatalog,
    EvidenceItem,
    ObservedTransformation,
    TransformationContract,
    TransformationPredicate,
    TransformationSubjectDiagnostic,
    TransformationSubjectMatch,
    TransformationSubjectSelection,
)


def select_transformation_subjects(
    contract: TransformationContract,
    observed: ObservedTransformation,
    evidence_catalog: EvidenceCatalog,
) -> TransformationSubjectSelection:
    """Resolve explicit selectors only to canonical changed structural facts."""

    evidence = evidence_catalog.by_id()
    candidates = tuple(
        evidence[item_id]
        for item_id in observed.structural_change_evidence_ids
        if item_id in evidence
    )
    matches: list[TransformationSubjectMatch] = []
    diagnostics: list[TransformationSubjectDiagnostic] = []

    for predicate in contract.predicates.predicates:
        for selector_index, selector_value in enumerate(predicate.values, start=1):
            selected = tuple(
                item
                for item in candidates
                if _matches(predicate, selector_value, item)
            )
            if not selected:
                diagnostics.append(
                    TransformationSubjectDiagnostic(
                        id=(
                            f"TSD:{predicate.id}:{selector_index}:"
                            "no_structural_match"
                        ),
                        claim_id=predicate.claim_id,
                        predicate_id=predicate.id,
                        selector_index=selector_index,
                        state="no_structural_match",
                        message=(
                            f"Explicit selector {selector_value!r} did not match a "
                            "canonical changed structural identity on its expected "
                            "revision side."
                        ),
                    )
                )
                continue
            matches.extend(
                TransformationSubjectMatch(
                    id=(
                        f"TSM:{predicate.id}:{selector_index}:{item.id}"
                    ),
                    claim_id=predicate.claim_id,
                    predicate_id=predicate.id,
                    selector_index=selector_index,
                    selector_value=selector_value,
                    evidence_id=item.id,
                )
                for item in sorted(selected, key=lambda candidate: candidate.id)
            )

    result = TransformationSubjectSelection(
        matches=tuple(matches),
        diagnostics=tuple(diagnostics),
    )
    result.validate_consistency(contract, observed, evidence_catalog)
    return result


def _matches(
    predicate: TransformationPredicate,
    selector_value: str,
    item: EvidenceItem,
) -> bool:
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
    return bool(
        selector_keys & {*signature.identifiers, *signature.tokens}
    )


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
