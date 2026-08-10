from __future__ import annotations

import re

from repodelta.model.contracts import (
    AssociationSignature,
    EvidenceItem,
    FocusEvidenceRole,
    Requirement,
    RequirementProfile,
    ReviewStatement,
)
from repodelta.facts.lexical import merge_signatures, semantic_tokens

_REMOVAL_TERMS = {
    "remove",
    "removed",
    "removal",
    "delete",
    "deleted",
    "deprecate",
    "deprecated",
    "cleanup",
    "clean",
    "exclude",
    "prevent",
    "avoid",
    "mustn",
}
_DOCUMENTATION_INTENT_RE = re.compile(
    r"^(?:"
    r"document\b|"
    r"(?:documentation|docs|readme)\s+"
    r"(?:covers?|describes?|documents?|explains?|includes?|is|matches?|must|reflects?|should)\b|"
    r"(?:add|publish|update|write)\s+(?:the\s+)?"
    r"(?:documentation|docs|readme)\b"
    r")",
    re.IGNORECASE,
)
_TEST_INTENT_RE = re.compile(
    r"^(?:"
    r"(?:test|validate|verify)\b|"
    r"(?:tests|testing|validation|verification)\s+"
    r"(?:covers?|is|must|pass|passes|should|verify|verifies|validate|validates)\b|"
    r"(?:add|extend|run)\s+(?:the\s+)?(?:regression|tests?|testing)\b"
    r")",
    re.IGNORECASE,
)


def requirement_profile(focus: Requirement) -> RequirementProfile:
    if focus.kind == "guardrail":
        return "guardrail"
    normalized = focus.text.casefold().strip()
    tokens = semantic_tokens(focus.text)
    if _DOCUMENTATION_INTENT_RE.match(normalized):
        return "documentation"
    if _TEST_INTENT_RE.match(normalized):
        return "test_verification"
    if tokens & {"render", "renderer", "html", "component", "display"}:
        return "ui"
    if tokens & {
        "workflow",
        "configuration",
        "config",
        "action",
        "actions",
        "pipeline",
    }:
        return "workflow_configuration"
    if tokens & {"schema", "migration", "database"}:
        return "schema_migration"
    if tokens & {"api", "contract", "interface", "schema", "versioned"}:
        return "api_contract"
    if tokens & {"runtime", "behavior", "execute", "execution", "call"}:
        return "behavior"
    return "generic"


def eligible_changed_anchor(
    item: EvidenceItem,
    profile: RequirementProfile,
    focus: Requirement,
) -> bool:
    """Apply fact semantics before text association.

    Base-side removals are current implementation evidence only when the focus
    explicitly concerns removal, deprecation, legacy cleanup, or a guardrail.
    """

    if item.role != "changed_anchor" or item.profile == "generated":
        return False
    if item.revision_side == "base" or item.operation == "removed":
        if profile != "guardrail" and not semantic_tokens(focus.text) & _REMOVAL_TERMS:
            return False
    allowed = {
        "documentation": {"document"},
        "workflow_configuration": {
            "workflow",
            "configuration",
            "dependency",
            "production",
            "test",
        },
        "schema_migration": {"schema", "production", "test", "configuration"},
        "test_verification": {"test", "workflow", "production"},
        "api_contract": {"production", "test", "schema"},
        "ui": {"production", "test", "document"},
        "behavior": {"production", "test", "configuration"},
        "guardrail": {
            "production",
            "test",
            "document",
            "workflow",
            "configuration",
            "dependency",
            "schema",
        },
        "generic": {
            "production",
            "test",
            "document",
            "workflow",
            "configuration",
            "dependency",
            "schema",
            "unknown",
        },
    }
    return item.profile in allowed[profile]


def focus_evidence_role(
    profile: RequirementProfile,
    fact_profile: str,
) -> FocusEvidenceRole:
    """Classify one eligible fact relative to the review focus."""

    if fact_profile == "document" and profile != "documentation":
        return "document_support"
    if fact_profile == "test" and profile != "test_verification":
        return "test_support"
    return "primary"


def anchor_key(item: EvidenceItem) -> tuple[object, ...]:
    precision = {
        "structural_change": 0,
        "change_relation": 1,
        "changed_file": 2,
    }
    source = item.sources[0] if item.sources else None
    return (
        precision.get(item.kind, 3),
        str(item.metadata.get("path") or (source.path if source else "") or ""),
        int(
            item.metadata.get("start_line")
            or next(iter(item.metadata.get("added_lines", ())), 0)
            or next(iter(item.metadata.get("removed_lines", ())), 0)
            or (source.line_start if source else 0)
            or 0
        ),
        str(item.metadata.get("qualified_name") or ""),
        item.id,
    )


def evidence_signature(
    item: EvidenceItem,
    focus: Requirement | ReviewStatement,
) -> AssociationSignature:
    """Select directional canonical retrieval truth for one review focus."""

    use_base = (
        item.revision_side == "base"
        or focus.purpose == "guardrail"
        or bool(semantic_tokens(focus.text) & _REMOVAL_TERMS)
    )
    return merge_signatures(
        item.head_signature,
        item.base_signature if use_base else AssociationSignature(),
    )
