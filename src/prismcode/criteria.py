from __future__ import annotations

import re
from dataclasses import dataclass, replace

from .contracts import (
    Requirement,
    ReviewStatement,
    SourceRef,
    StatementAuthority,
    StatementRole,
)

_OBLIGATION_HEADINGS = {
    "requirement",
    "requirements",
    "acceptance criteria",
    "acceptance criterion",
    "definition of done",
    "success criteria",
}
_OBJECTIVE_HEADINGS = {
    "goal",
    "goals",
    "objective",
    "objectives",
}
_CLAIM_HEADINGS = {
    "summary",
    "implementation",
    "implementation summary",
    "changes",
    "what changed",
    "approach",
}
_ROLE_BY_HEADING = {
    **{heading: "obligation" for heading in _OBLIGATION_HEADINGS},
    **{heading: "objective" for heading in _OBJECTIVE_HEADINGS},
    **{heading: "claim" for heading in _CLAIM_HEADINGS},
}
_CHECKLIST_RE = re.compile(r"^\s*[-*+]\s+\[[ xX]\]\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+?)\s*$")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")


@dataclass(frozen=True)
class _ParsedItem:
    text: str
    role: StatementRole
    section: str
    line: int


@dataclass(frozen=True)
class ParsedBody:
    items: tuple[_ParsedItem, ...] = ()
    introductory_intent: str = ""
    introductory_line: int | None = None


@dataclass(frozen=True)
class ReviewSemantics:
    intent: ReviewStatement
    obligations: tuple[Requirement, ...] = ()
    objectives: tuple[ReviewStatement, ...] = ()
    claims: tuple[ReviewStatement, ...] = ()


def _clean_markdown_text(value: str) -> str:
    value = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL)
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"[*~]+", "", value)
    return " ".join(value.strip().split())


def parse_markdown_semantics(body: str | None) -> ParsedBody:
    """Parse one Markdown body once into typed section items and an intro."""

    if not body:
        return ParsedBody()
    items: list[_ParsedItem] = []
    seen: set[tuple[StatementRole, str]] = set()
    current_section = ""
    current_role: StatementRole | None = None
    paragraph: list[tuple[int, str]] = []
    introductory: list[tuple[int, str]] = []
    intro_complete = False

    def append_item(text: str, role: StatementRole, section: str, line: int) -> None:
        cleaned = _clean_markdown_text(text)
        marker = (role, cleaned.casefold())
        if cleaned and marker not in seen:
            items.append(_ParsedItem(cleaned, role, section, line))
            seen.add(marker)

    def finish_paragraph() -> None:
        nonlocal paragraph
        if paragraph and current_role in {"objective", "claim"}:
            append_item(
                " ".join(text for _, text in paragraph),
                current_role,
                current_section,
                paragraph[0][0],
            )
        paragraph = []

    heading_seen = False
    for line_number, raw_line in enumerate(body.splitlines(), start=1):
        heading_match = _HEADING_RE.match(raw_line)
        if heading_match:
            finish_paragraph()
            heading_seen = True
            current_section = _clean_markdown_text(heading_match.group(1))
            current_role = _ROLE_BY_HEADING.get(current_section.casefold())
            continue

        checklist_match = _CHECKLIST_RE.match(raw_line)
        bullet_match = _BULLET_RE.match(raw_line)
        list_match = checklist_match or bullet_match
        if list_match:
            finish_paragraph()
            if current_role is not None:
                append_item(
                    list_match.group(1),
                    current_role,
                    current_section,
                    line_number,
                )
            continue

        stripped = raw_line.strip()
        if not stripped:
            finish_paragraph()
            if introductory:
                intro_complete = True
            continue
        if current_role in {"objective", "claim"}:
            paragraph.append((line_number, stripped))
        elif not heading_seen and not intro_complete:
            introductory.append((line_number, stripped))

    finish_paragraph()
    intro = _clean_markdown_text(" ".join(text for _, text in introductory))
    return ParsedBody(
        items=tuple(items),
        introductory_intent=intro,
        introductory_line=introductory[0][0] if introductory else None,
    )


def extract_review_semantics(
    *,
    issue_body: str | None,
    issue_source: SourceRef | None,
    pr_body: str | None,
    pr_source: SourceRef,
    pr_title: str,
) -> ReviewSemantics:
    """Apply the single authority policy to already collected source bodies."""

    issue = parse_markdown_semantics(issue_body)
    pr = parse_markdown_semantics(pr_body)
    issue_obligations = (
        tuple(item for item in issue.items if item.role == "obligation")
        if issue_source is not None
        else ()
    )
    pr_obligations = tuple(item for item in pr.items if item.role == "obligation")
    selected_obligations = issue_obligations or pr_obligations
    obligation_authority: StatementAuthority = (
        "issue" if issue_obligations else "pr_description"
    )
    obligation_source = issue_source if issue_obligations else pr_source

    requirements = _number_requirements(
        selected_obligations,
        source=obligation_source or pr_source,
        authority=obligation_authority,
    )
    objective_items = (
        *(
            (item, issue_source, "issue")
            for item in issue.items
            if item.role == "objective" and issue_source is not None
        ),
        *(
            (item, pr_source, "pr_description")
            for item in pr.items
            if item.role == "objective"
        ),
    )
    objectives = _number_statements(
        objective_items,
        prefix="O",
        role="objective",
    )
    claims = tuple(
        ReviewStatement(
            id=f"C{index}",
            text=item.text,
            role="claim",
            authority="pr_description",
            sources=(_located_source(pr_source, item),),
        )
        for index, item in enumerate(
            (item for item in pr.items if item.role == "claim"),
            start=1,
        )
    )
    if pr.introductory_intent:
        intent = ReviewStatement(
            id="I1",
            text=pr.introductory_intent,
            role="intent",
            authority="pr_description",
            sources=(
                replace(
                    pr_source,
                    label=f"{pr_source.label} · Introduction",
                    line_start=pr.introductory_line,
                ),
            ),
        )
    else:
        intent = ReviewStatement(
            id="I1",
            text=pr_title,
            role="intent",
            authority="pr_title",
            sources=(SourceRef(label="pull request title", url=pr_source.url),),
        )
    return ReviewSemantics(
        intent=intent,
        obligations=requirements,
        objectives=objectives,
        claims=claims,
    )


def extract_requirement_texts(body: str | None) -> tuple[str, ...]:
    parsed = parse_markdown_semantics(body)
    return tuple(item.text for item in parsed.items if item.role == "obligation")


def extract_requirements(
    body: str | None,
    *,
    source: SourceRef,
    authority: StatementAuthority = "provided",
) -> tuple[Requirement, ...]:
    parsed = parse_markdown_semantics(body)
    return _number_requirements(
        tuple(item for item in parsed.items if item.role == "obligation"),
        source=source,
        authority=authority,
    )


def extract_intent(body: str | None, title: str) -> str:
    return parse_markdown_semantics(body).introductory_intent or title


def _number_requirements(
    items: tuple[_ParsedItem, ...],
    *,
    source: SourceRef,
    authority: StatementAuthority,
) -> tuple[Requirement, ...]:
    deliverable_index = 0
    guardrail_index = 0
    requirements: list[Requirement] = []
    for item in items:
        kind = _requirement_kind(item.text)
        if kind == "guardrail":
            guardrail_index += 1
            statement_id = f"G{guardrail_index}"
        else:
            deliverable_index += 1
            statement_id = f"R{deliverable_index}"
        requirements.append(
            Requirement(
                id=statement_id,
                text=item.text,
                role="obligation",
                authority=authority,
                kind=kind,
                sources=(_located_source(source, item),),
            )
        )
    return tuple(requirements)


def _number_statements(
    items: tuple[tuple[_ParsedItem, SourceRef, StatementAuthority], ...],
    *,
    prefix: str,
    role: StatementRole,
) -> tuple[ReviewStatement, ...]:
    statements = []
    for index, (item, source, authority) in enumerate(items, start=1):
        statements.append(
            ReviewStatement(
                id=f"{prefix}{index}",
                text=item.text,
                role=role,
                authority=authority,
                sources=(_located_source(source, item),),
            )
        )
    return tuple(statements)


def _located_source(source: SourceRef, item: _ParsedItem) -> SourceRef:
    label = f"{source.label} · {item.section}" if item.section else source.label
    return replace(source, label=label, line_start=item.line)


def _requirement_kind(text: str) -> str:
    normalized = text.casefold().strip()
    guardrail_prefixes = (
        "no ",
        "do not ",
        "must not ",
        "should not ",
        "without changing ",
    )
    return "guardrail" if normalized.startswith(guardrail_prefixes) else "deliverable"
