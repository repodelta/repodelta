from __future__ import annotations

from prismcode.model.contracts import EvidenceItem, Requirement, RequirementProfile
from prismcode.facts.lexical import semantic_tokens


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
        removal_terms = {
            "remove",
            "removed",
            "removal",
            "delete",
            "deleted",
            "deprecate",
            "deprecated",
            "legacy",
            "cleanup",
            "clean",
            "exclude",
            "prevent",
            "avoid",
            "mustn",
        }
        if profile != "guardrail" and not semantic_tokens(focus.text) & removal_terms:
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
    precision = {"symbol": 0, "changed_hunk": 1, "changed_file": 2}
    source = item.sources[0] if item.sources else None
    return (
        precision.get(item.kind, 3),
        str(item.metadata.get("path") or (source.path if source else "") or ""),
        int(
            item.metadata.get("start_line")
            or item.metadata.get("new_start")
            or (source.line_start if source else 0)
            or 0
        ),
        str(item.metadata.get("qualified_name") or ""),
        item.id,
    )


def evidence_text(item: EvidenceItem) -> str:
    metadata = item.metadata
    # Current implementation association only sees the head-side change.
    # Base-side text remains available as provenance for removal-oriented focus.
    excerpt = (
        metadata.get("base_excerpt")
        if item.revision_side == "base"
        else metadata.get("head_excerpt")
    )
    return "\n".join(
        value
        for value in (
            item.summary,
            str(metadata.get("path") or ""),
            str(metadata.get("qualified_name") or ""),
            str(excerpt or ""),
        )
        if value
    )
