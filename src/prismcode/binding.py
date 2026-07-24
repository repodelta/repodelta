from __future__ import annotations

import re

from .contracts import (
    EvidenceCatalog,
    EvidenceHint,
    Requirement,
    ReviewSourcePacket,
    SourceRef,
)
from .evidence_graph import evidence_id, verification_evidence_id

_TOKEN_RE = re.compile(r"[a-z][a-z0-9_]{3,}", re.IGNORECASE)
_STOP_WORDS = {
    "acceptance", "artifact", "behavior", "change", "changes", "compact",
    "current", "debug", "existing", "exports", "from", "makes", "normal",
    "possible", "report", "requirement", "reused", "summary", "through",
    "without", "with", "each", "into", "that", "this", "true",
}
_GENERIC_CHECK_NAMES = {"ci", "check", "checks", "test", "tests", "github actions"}


def build_deterministic_evidence_hints(
    requirements: tuple[Requirement, ...],
    packet: ReviewSourcePacket,
    catalog: EvidenceCatalog,
) -> tuple[EvidenceHint, ...]:
    """Produce conservative lexical pointers; never produce a final assessment."""

    hints: list[EvidenceHint] = []
    for requirement in requirements:
        requirement_tokens = _tokens(requirement.text)
        scored: list[tuple[int, object, set[str]]] = []
        for changed_file in packet.changed_files:
            haystack = f"{changed_file.path}\n{changed_file.patch or ''}"
            overlap = requirement_tokens & _tokens(haystack)
            path_overlap = requirement_tokens & _tokens(changed_file.path)
            explicit = {token for token in overlap if "_" in token or "/" in token}
            score = len(overlap) + (2 * len(path_overlap)) + (3 * len(explicit))
            if score >= 2 or explicit:
                scored.append((score, changed_file, overlap))
        if not scored:
            continue
        highest = max(score for score, _, _ in scored)
        selected = [row for row in scored if row[0] >= max(2, highest - 1)]
        catalog_ids = catalog.by_id()
        implementation_ids = tuple(
            item_id
            for _, changed_file, _ in selected
            if (
                item_id := evidence_id("changed_file", changed_file.path)
            ) in catalog_ids
        )
        verification_ids = _matching_verification_ids(requirement_tokens, packet)
        hints.append(
            EvidenceHint(
                requirement_id=requirement.id,
                implementation_evidence_ids=implementation_ids,
                verification_evidence_ids=verification_ids,
                assertion_coverage="adequate" if verification_ids else "not_established",
                provenance=(SourceRef(label="deterministic diff binding"),),
            )
        )
    return tuple(hints)


def _matching_verification_ids(
    requirement_tokens: set[str],
    packet: ReviewSourcePacket,
) -> tuple[str, ...]:
    result: list[str] = []
    for observation in packet.verification_observations:
        name = observation.name.strip().casefold()
        if name in _GENERIC_CHECK_NAMES:
            continue
        overlap = requirement_tokens & _tokens(name)
        if len(overlap) >= 2 or any("_" in token for token in overlap):
            result.append(verification_evidence_id(observation.id))
    return tuple(result)


def _tokens(value: str) -> set[str]:
    result: set[str] = set()
    for raw_token in _TOKEN_RE.findall(value):
        token = raw_token.casefold()
        candidates = (token, *token.split("_"))
        result.update(
            candidate
            for candidate in candidates
            if len(candidate) >= 4 and candidate not in _STOP_WORDS
        )
    return result
