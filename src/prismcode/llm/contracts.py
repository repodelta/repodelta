from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Literal, Mapping, Sequence


SHADOW_SCHEMA_VERSION = "2"
MAX_CANDIDATES = 100
MAX_SELECTIONS = 30
MAX_UNRESOLVED_SURFACES = 20
MAX_TEXT_LENGTH = 2_000

ShadowEvidenceRole = Literal["supporting", "contradicting", "context"]
ShadowSemanticRole = Literal[
    "authority",
    "producer",
    "consumer",
    "path",
    "test",
    "removal",
    "boundary",
    "documentation",
    "unknown",
]

_EVIDENCE_ROLES = frozenset({"supporting", "contradicting", "context"})
_RESPONSE_FIELDS = frozenset(
    {
        "schema_version",
        "request_id",
        "subject_id",
        "selections",
        "rejected_evidence_ids",
        "insufficient_evidence_ids",
        "unresolved_surfaces",
    }
)
_SELECTION_FIELDS = frozenset(
    {"evidence_id", "role", "semantic_role", "rationale"}
)
_SEMANTIC_ROLES = frozenset(
    {
        "authority",
        "producer",
        "consumer",
        "path",
        "test",
        "removal",
        "boundary",
        "documentation",
        "unknown",
    }
)


@dataclass(frozen=True)
class ShadowEvidenceCandidate:
    """A canonical fact admitted upstream for shadow-only selection."""

    evidence_id: str
    summary: str
    kind: str
    revision_side: str = "none"
    operation: str = "context"
    classification: str = "unknown"
    profile: str = "unknown"
    authority: str = "unknown"
    path: str = ""
    line_start: int | None = None
    line_end: int | None = None
    symbol_kind: str = ""
    qualified_name: str = ""
    added_code: str = ""
    removed_code: str = ""
    structural_context: tuple[str, ...] = ()
    admission_tier: str = "unspecified"
    association: str = "none"

    def __post_init__(self) -> None:
        _require_text(self.evidence_id, "evidence_id")
        _require_text(self.summary, "summary")
        _require_text(self.kind, "kind")
        for name in (
            "classification",
            "profile",
            "authority",
            "admission_tier",
            "association",
        ):
            _require_text(getattr(self, name), name)
        for name in (
            "path",
            "symbol_kind",
            "qualified_name",
            "added_code",
            "removed_code",
        ):
            value = getattr(self, name)
            if value:
                _require_text(value, name)
        if (self.line_start is None) != (self.line_end is None):
            raise ValueError("candidate line range must be complete")
        if (
            self.line_start is not None
            and self.line_end is not None
            and (self.line_start < 0 or self.line_end < self.line_start)
        ):
            raise ValueError("candidate line range is invalid")
        for context in self.structural_context:
            _require_text(context, "structural_context")

    def to_dict(self) -> dict[str, Any]:
        return _json_dict(self)


@dataclass(frozen=True)
class ShadowEvidenceRequest:
    """Bounded input whose candidate membership remains deterministic."""

    request_id: str
    subject_id: str
    subject_kind: str
    authored_statement: str
    candidates: tuple[ShadowEvidenceCandidate, ...]
    coverage_limits: tuple[str, ...] = ()
    schema_version: str = SHADOW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SHADOW_SCHEMA_VERSION:
            raise ValueError("unsupported shadow request schema_version")
        for name in ("request_id", "subject_id", "subject_kind", "authored_statement"):
            _require_text(getattr(self, name), name)
        if len(self.candidates) > MAX_CANDIDATES:
            raise ValueError(f"candidates exceed safety limit {MAX_CANDIDATES}")
        candidate_ids = [candidate.evidence_id for candidate in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("candidate evidence IDs must be unique")
        for limit in self.coverage_limits:
            _require_text(limit, "coverage_limit")

    def to_dict(self) -> dict[str, Any]:
        return _json_dict(self)


def shadow_candidate_from_mapping(
    raw: Mapping[str, Any],
) -> ShadowEvidenceCandidate:
    """Load the canonical additive candidate contract at serialization edges."""

    return ShadowEvidenceCandidate(
        evidence_id=str(raw.get("evidence_id", "")),
        summary=str(raw.get("summary", "")),
        kind=str(raw.get("kind", "")),
        revision_side=str(raw.get("revision_side", "none")),
        operation=str(raw.get("operation", "context")),
        classification=str(raw.get("classification", "unknown")),
        profile=str(raw.get("profile", "unknown")),
        authority=str(raw.get("authority", "unknown")),
        path=str(raw.get("path", "")),
        line_start=raw.get("line_start"),
        line_end=raw.get("line_end"),
        symbol_kind=str(raw.get("symbol_kind", "")),
        qualified_name=str(raw.get("qualified_name", "")),
        added_code=str(raw.get("added_code", "")),
        removed_code=str(raw.get("removed_code", "")),
        structural_context=tuple(raw.get("structural_context", ())),
        admission_tier=str(raw.get("admission_tier", "unspecified")),
        association=str(raw.get("association", "none")),
    )


@dataclass(frozen=True)
class ShadowEvidenceSelectionItem:
    evidence_id: str
    role: ShadowEvidenceRole
    semantic_role: ShadowSemanticRole
    rationale: str


@dataclass(frozen=True)
class ShadowEvidenceSelection:
    """Validated shadow output; deliberately carries no formal assessment."""

    request_id: str
    subject_id: str
    selections: tuple[ShadowEvidenceSelectionItem, ...]
    rejected_evidence_ids: tuple[str, ...] = ()
    insufficient_evidence_ids: tuple[str, ...] = ()
    unresolved_surfaces: tuple[str, ...] = ()
    schema_version: str = SHADOW_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return _json_dict(self)


@dataclass(frozen=True)
class ShadowSelectionDiagnostic:
    code: str
    message: str


@dataclass(frozen=True)
class ShadowSelectionValidation:
    selection: ShadowEvidenceSelection | None
    diagnostics: tuple[ShadowSelectionDiagnostic, ...]

    @property
    def accepted(self) -> bool:
        return self.selection is not None and not self.diagnostics


def parse_shadow_selection(
    raw: Mapping[str, Any], request: ShadowEvidenceRequest
) -> ShadowSelectionValidation:
    """Validate untrusted model output against one canonical request."""

    diagnostics: list[ShadowSelectionDiagnostic] = []
    unexpected_fields = set(raw) - _RESPONSE_FIELDS
    if unexpected_fields:
        diagnostics.append(
            _diagnostic(
                "unexpected_response_fields",
                f"Unexpected response fields: {', '.join(sorted(unexpected_fields))}.",
            )
        )
    if raw.get("schema_version") != SHADOW_SCHEMA_VERSION:
        diagnostics.append(_diagnostic("schema_mismatch", "Unsupported schema_version."))
    if raw.get("request_id") != request.request_id:
        diagnostics.append(_diagnostic("request_mismatch", "request_id does not match."))
    if raw.get("subject_id") != request.subject_id:
        diagnostics.append(_diagnostic("subject_mismatch", "subject_id does not match."))

    raw_items = raw.get("selections")
    if not _is_sequence(raw_items):
        diagnostics.append(_diagnostic("invalid_selections", "selections must be a list."))
        raw_items = ()
    if len(raw_items) > MAX_SELECTIONS:
        diagnostics.append(
            _diagnostic(
                "selection_budget_exceeded",
                f"selections exceed safety limit {MAX_SELECTIONS}.",
            )
        )

    allowed_ids = {candidate.evidence_id for candidate in request.candidates}
    seen_ids: set[str] = set()
    selections: list[ShadowEvidenceSelectionItem] = []
    for index, item in enumerate(raw_items[: MAX_SELECTIONS + 1]):
        if not isinstance(item, Mapping):
            diagnostics.append(
                _diagnostic(
                    "invalid_selection",
                    f"selection {index} is not an object.",
                )
            )
            continue
        unexpected_item_fields = set(item) - _SELECTION_FIELDS
        if unexpected_item_fields:
            diagnostics.append(
                _diagnostic(
                    "unexpected_selection_fields",
                    f"selection {index} contains unexpected fields.",
                )
            )
            continue
        evidence_id = item.get("evidence_id")
        role = item.get("role")
        semantic_role = item.get("semantic_role")
        rationale = item.get("rationale")
        if not isinstance(evidence_id, str) or evidence_id not in allowed_ids:
            diagnostics.append(
                _diagnostic(
                    "unknown_evidence_id",
                    f"selection {index} cites an unadmitted evidence ID.",
                )
            )
            continue
        if evidence_id in seen_ids:
            diagnostics.append(
                _diagnostic(
                    "duplicate_evidence_id",
                    f"evidence ID {evidence_id!r} is selected more than once.",
                )
            )
            continue
        if role not in _EVIDENCE_ROLES:
            diagnostics.append(
                _diagnostic(
                    "invalid_evidence_role",
                    f"selection {index} has an invalid role.",
                )
            )
            continue
        if semantic_role not in _SEMANTIC_ROLES:
            diagnostics.append(
                _diagnostic(
                    "invalid_semantic_role",
                    f"selection {index} has an invalid semantic role.",
                )
            )
            continue
        if not _valid_text(rationale):
            diagnostics.append(
                _diagnostic(
                    "invalid_rationale",
                    f"selection {index} has an invalid rationale.",
                )
            )
            continue
        seen_ids.add(evidence_id)
        selections.append(
            ShadowEvidenceSelectionItem(
                evidence_id=evidence_id,
                role=role,
                semantic_role=semantic_role,
                rationale=rationale,
            )
        )

    disposition_ids: dict[str, tuple[str, ...]] = {}
    for field in ("rejected_evidence_ids", "insufficient_evidence_ids"):
        raw_ids = raw.get(field)
        parsed_ids: list[str] = []
        if not _is_sequence(raw_ids):
            diagnostics.append(
                _diagnostic(
                    f"invalid_{field}",
                    f"{field} must be a list.",
                )
            )
        else:
            if len(raw_ids) > MAX_CANDIDATES:
                diagnostics.append(
                    _diagnostic(
                        "candidate_disposition_budget_exceeded",
                        f"{field} exceeds safety limit {MAX_CANDIDATES}.",
                    )
                )
            for index, evidence_id in enumerate(raw_ids[: MAX_CANDIDATES + 1]):
                if not isinstance(evidence_id, str) or evidence_id not in allowed_ids:
                    diagnostics.append(
                        _diagnostic(
                            "unknown_evidence_id",
                            f"{field} {index} cites an unadmitted evidence ID.",
                        )
                    )
                    continue
                if evidence_id in parsed_ids:
                    diagnostics.append(
                        _diagnostic(
                            "duplicate_evidence_id",
                            f"evidence ID {evidence_id!r} occurs twice in {field}.",
                        )
                    )
                    continue
                parsed_ids.append(evidence_id)
        disposition_ids[field] = tuple(parsed_ids)

    rejected_ids = disposition_ids["rejected_evidence_ids"]
    insufficient_ids = disposition_ids["insufficient_evidence_ids"]
    selected_ids = {item.evidence_id for item in selections}
    rejected_set = set(rejected_ids)
    insufficient_set = set(insufficient_ids)
    overlap = (
        (selected_ids & rejected_set)
        | (selected_ids & insufficient_set)
        | (rejected_set & insufficient_set)
    )
    if overlap:
        diagnostics.append(
            _diagnostic(
                "overlapping_candidate_disposition",
                "Candidate dispositions overlap for: "
                f"{', '.join(sorted(overlap))}.",
            )
        )
    missing = allowed_ids - selected_ids - rejected_set - insufficient_set
    if missing:
        diagnostics.append(
            _diagnostic(
                "incomplete_candidate_partition",
                "Every admitted candidate must be selected, rejected, or "
                f"insufficient; missing: {', '.join(sorted(missing))}.",
            )
        )

    raw_unresolved = raw.get("unresolved_surfaces", [])
    unresolved: list[str] = []
    if not _is_sequence(raw_unresolved):
        diagnostics.append(
            _diagnostic("invalid_unresolved_surfaces", "unresolved_surfaces must be a list.")
        )
    else:
        if len(raw_unresolved) > MAX_UNRESOLVED_SURFACES:
            diagnostics.append(
                _diagnostic(
                    "unresolved_surface_budget_exceeded",
                    "unresolved_surfaces exceed the safety limit "
                    f"{MAX_UNRESOLVED_SURFACES}.",
                )
            )
        for index, value in enumerate(raw_unresolved[: MAX_UNRESOLVED_SURFACES + 1]):
            if not _valid_text(value):
                diagnostics.append(
                    _diagnostic(
                        "invalid_unresolved_surface",
                        f"unresolved surface {index} is invalid.",
                    )
                )
            else:
                unresolved.append(value)

    if diagnostics:
        return ShadowSelectionValidation(selection=None, diagnostics=tuple(diagnostics))
    return ShadowSelectionValidation(
        selection=ShadowEvidenceSelection(
            request_id=request.request_id,
            subject_id=request.subject_id,
            selections=tuple(selections),
            rejected_evidence_ids=_candidate_order(request, rejected_ids),
            insufficient_evidence_ids=_candidate_order(request, insufficient_ids),
            unresolved_surfaces=tuple(unresolved),
        ),
        diagnostics=(),
    )


def _diagnostic(code: str, message: str) -> ShadowSelectionDiagnostic:
    return ShadowSelectionDiagnostic(code=code, message=message)


def _candidate_order(
    request: ShadowEvidenceRequest,
    evidence_ids: tuple[str, ...],
) -> tuple[str, ...]:
    selected = set(evidence_ids)
    return tuple(
        candidate.evidence_id
        for candidate in request.candidates
        if candidate.evidence_id in selected
    )


def _json_dict(value: object) -> dict[str, Any]:
    return json.loads(json.dumps(asdict(value)))


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _valid_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= MAX_TEXT_LENGTH


def _require_text(value: object, name: str) -> None:
    if not _valid_text(value):
        raise ValueError(f"{name} must be non-empty and at most {MAX_TEXT_LENGTH} characters")
