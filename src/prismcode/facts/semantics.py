from __future__ import annotations

from prismcode.model.contracts import (
    AssociationSignature,
    EvidenceItem,
    Requirement,
    RequirementProfile,
    ReviewStatement,
)
from prismcode.facts.lexical import merge_signatures, semantic_tokens

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


def requirement_profile(focus: Requirement) -> RequirementProfile:
    if focus.kind == "guardrail":
        return "guardrail"
    tokens = semantic_tokens(focus.text)
    if tokens & {"documentation", "document", "readme", "docs"}:
        return "documentation"
    if tokens & {"workflow", "configuration", "config", "action", "actions", "pipeline"}:
        return "workflow_configuration"
    if tokens & {"schema", "migration", "database"}:
        return "schema_migration"
    if tokens & {"test", "tests", "testing", "verification", "verified"}:
        return "test_verification"
    if tokens & {"api", "contract", "interface", "schema", "versioned"}:
        return "api_contract"
    if tokens & {"render", "renderer", "html", "component", "display"}:
        return "ui"
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


def anchor_key(item: EvidenceItem) -> tuple[object, ...]:
    precision = {"symbol": 0, "changed_span": 1, "changed_file": 2}
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
