from __future__ import annotations

import re
from dataclasses import dataclass, replace

from prismcode.model.contracts import (
    Requirement,
    ReviewStatement,
    SourceRef,
    StatementAuthority,
    StatementPurpose,
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
    "aim",
    "aims",
    "change intent",
    "desired outcome",
    "desired outcomes",
    "expected outcome",
    "expected outcomes",
    "goal",
    "goals",
    "intended outcome",
    "intended outcomes",
    "motivation",
    "objective",
    "objectives",
    "purpose",
    "rationale",
    "what this change aims to achieve",
    "what this change is trying to achieve",
    "what we aim to achieve",
    "what we want to achieve",
    "why",
    "why this change",
}
_IMPLEMENTATION_HEADINGS = {
    "approach",
    "change summary",
    "changes",
    "changes made",
    "implementation",
    "implementation details",
    "implementation notes",
    "implementation overview",
    "implementation summary",
    "key changes",
    "semantic atom",
    "solution",
    "solution overview",
    "technical approach",
    "summary",
    "what changed",
    "what was changed",
    "work completed",
}
_SCOPE_HEADINGS = {
    "areas in scope",
    "components in scope",
    "covered areas",
    "covered components",
    "change scope",
    "change boundary",
    "included",
    "included changes",
    "included work",
    "implementation boundary",
    "in scope",
    "scope",
    "scope of change",
    "scope of this change",
    "scope of work",
    "pipeline boundary",
    "review boundary",
    "system boundary",
    "work scope",
    "what is covered",
    "what is included",
    "what this change covers",
    "what this change includes",
}
_BOUNDARY_HEADINGS = {
    "out of scope",
    "non-goals",
    "non goals",
    "boundary",
    "boundaries",
}
_BASELINE_HEADINGS = {"baseline", "baselines", "result", "results"}
_VERIFICATION_HEADINGS = {
    "acceptance tests",
    "automated tests",
    "checks",
    "how to test",
    "how it was tested",
    "how this was tested",
    "how to validate",
    "how to verify",
    "manual testing",
    "quality checks",
    "test cases",
    "test coverage",
    "verification",
    "verification criteria",
    "verification expectations",
    "verification plan",
    "verification steps",
    "validation criteria",
    "validation plan",
    "testing",
    "tests",
    "test plan",
    "test strategy",
    "testing performed",
    "validation",
    "validation strategy",
    "verification approach",
}
_SEMANTICS_BY_HEADING: dict[str, tuple[StatementRole, StatementPurpose]] = {
    **{heading: ("obligation", "acceptance") for heading in _OBLIGATION_HEADINGS},
    **{heading: ("objective", "goal") for heading in _OBJECTIVE_HEADINGS},
    **{heading: ("context", "scope") for heading in _SCOPE_HEADINGS},
    **{heading: ("claim", "boundary") for heading in _BOUNDARY_HEADINGS},
    **{heading: ("claim", "implementation") for heading in _IMPLEMENTATION_HEADINGS},
    **{heading: ("claim", "baseline") for heading in _BASELINE_HEADINGS},
    **{heading: ("claim", "verification") for heading in _VERIFICATION_HEADINGS},
}
_LIST_ITEM_RE = re.compile(
    r"^(?P<indent>[ \t]*)"
    r"(?:(?:[-*+]|\u2022|\u00b7|\u25aa|\u25e6)\s+(?:\[[ xX]\]\s+)?"
    r"|(?:\d+[.)]|\(\d+\)|\d+\u3001|[一二三四五六七八九十]+\u3001)\s*"
    r"|(?:R|AC|REQ)[-_ ]?\d+\s*[:.\u3001]\s*)"
    r"(?P<text>.+?)\s*$",
    re.IGNORECASE,
)
_INLINE_NUMBER_RE = re.compile(r"(?:(?<=^)|(?<=[;\uff1b]))\s*(?:\d+[.)]|\(\d+\))\s*")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
_HEADING_DECORATION_RE = re.compile(r"^[^a-z0-9]+|[^a-z0-9]+$")


@dataclass(frozen=True)
class _ParsedItem:
    text: str
    role: StatementRole
    purpose: StatementPurpose
    section: str
    line: int


@dataclass
class _ListItem:
    text: str
    role: StatementRole
    purpose: StatementPurpose
    section: str
    line: int
    indent: int
    parent: int | None = None
    has_children: bool = False


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
    scope: tuple[ReviewStatement, ...] = ()
    verification_expectations: tuple[ReviewStatement, ...] = ()
    claims: tuple[ReviewStatement, ...] = ()


def _clean_markdown_text(value: str) -> str:
    value = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL)
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"[*~]+", "", value)
    return " ".join(value.strip().split())


def _normalize_heading(value: str) -> str:
    normalized = _clean_markdown_text(value).casefold()
    normalized = normalized.rstrip(" :–—-")
    normalized = re.sub(r"\s*\([^)]*\)\s*$", "", normalized)
    normalized = re.sub(r"^\d+[.)]\s*", "", normalized)
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"[/|]+", " ", normalized)
    normalized = re.sub(r"[\s:–—-]+", " ", normalized).strip()
    return _HEADING_DECORATION_RE.sub("", normalized).strip()


def _indent_width(value: str) -> int:
    return sum(4 if character == "\t" else 1 for character in value)


def _split_explicit_inline_items(value: str) -> tuple[str, ...]:
    """Split only an explicit inline numbered sequence, never prose punctuation."""

    matches = tuple(_INLINE_NUMBER_RE.finditer(value))
    if not matches:
        return (value,)
    parts = [value[: matches[0].start()].strip().rstrip(";\uff1b").strip()]
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(value)
        part = value[match.end() : end].strip().rstrip(";\uff1b").strip()
        if part:
            parts.append(part)
    parts = [part for part in parts if part]
    return tuple(parts) if len(parts) >= 2 else (value,)


def parse_markdown_semantics(body: str | None) -> ParsedBody:
    """Parse one Markdown body once into typed section items and an intro."""

    if not body:
        return ParsedBody()
    items: list[_ParsedItem] = []
    seen: set[tuple[StatementRole, StatementPurpose, str]] = set()
    current_section = ""
    current_role: StatementRole | None = None
    current_purpose: StatementPurpose | None = None
    paragraph: list[tuple[int, str]] = []
    list_items: list[_ListItem] = []
    list_stack: list[int] = []
    introductory: list[tuple[int, str]] = []
    intro_complete = False
    fence_marker: str | None = None

    def append_item(
        text: str,
        role: StatementRole,
        purpose: StatementPurpose,
        section: str,
        line: int,
    ) -> None:
        cleaned = _clean_markdown_text(text)
        marker = (role, purpose, cleaned.casefold())
        if cleaned and marker not in seen:
            items.append(_ParsedItem(cleaned, role, purpose, section, line))
            seen.add(marker)

    def finish_paragraph() -> None:
        nonlocal paragraph
        if (
            paragraph
            and current_role in {"objective", "claim", "context"}
            and current_purpose is not None
        ):
            append_item(
                " ".join(text for _, text in paragraph),
                current_role,
                current_purpose,
                current_section,
                paragraph[0][0],
            )
        paragraph = []

    def finish_list() -> None:
        nonlocal list_items, list_stack
        for item in list_items:
            if item.has_children:
                continue
            parent_texts = []
            parent = item.parent
            while parent is not None:
                parent_item = list_items[parent]
                parent_texts.append(parent_item.text)
                parent = parent_item.parent
            parent_texts.reverse()
            text = ": ".join((*parent_texts, item.text))
            for statement in _split_explicit_inline_items(text):
                append_item(
                    statement,
                    item.role,
                    item.purpose,
                    item.section,
                    item.line,
                )
        list_items = []
        list_stack = []

    heading_seen = False
    for line_number, raw_line in enumerate(body.splitlines(), start=1):
        fence_match = _FENCE_RE.match(raw_line)
        if fence_match:
            finish_paragraph()
            finish_list()
            marker = fence_match.group(1)[0]
            fence_marker = None if fence_marker == marker else marker
            continue
        if fence_marker is not None:
            continue

        heading_match = _HEADING_RE.match(raw_line)
        if heading_match:
            finish_paragraph()
            finish_list()
            heading_seen = True
            current_section = _clean_markdown_text(heading_match.group(1))
            semantics = _SEMANTICS_BY_HEADING.get(
                _normalize_heading(current_section)
            )
            current_role = semantics[0] if semantics is not None else None
            current_purpose = semantics[1] if semantics is not None else None
            continue

        list_match = _LIST_ITEM_RE.match(raw_line)
        if list_match:
            finish_paragraph()
            if current_role is not None and current_purpose is not None:
                indent = _indent_width(list_match.group("indent"))
                while list_stack and list_items[list_stack[-1]].indent >= indent:
                    list_stack.pop()
                parent = list_stack[-1] if list_stack else None
                if parent is not None:
                    list_items[parent].has_children = True
                list_items.append(
                    _ListItem(
                        text=list_match.group("text"),
                        role=current_role,
                        purpose=current_purpose,
                        section=current_section,
                        line=line_number,
                        indent=indent,
                        parent=parent,
                    )
                )
                list_stack.append(len(list_items) - 1)
            continue

        stripped = raw_line.strip()
        if not stripped:
            finish_paragraph()
            finish_list()
            if introductory:
                intro_complete = True
            continue
        if list_items and current_role is not None:
            list_items[-1].text = f"{list_items[-1].text} {stripped}"
            continue
        if current_role in {"objective", "claim", "context"}:
            paragraph.append((line_number, stripped))
        elif not heading_seen and not intro_complete:
            introductory.append((line_number, stripped))

    finish_paragraph()
    finish_list()
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

    issue_boundaries = (
        tuple(item for item in issue.items if item.purpose == "boundary")
        if issue_source is not None
        else ()
    )
    requirements = _number_requirement_items(
        (
            *(
                (item, obligation_source or pr_source, obligation_authority)
                for item in selected_obligations
            ),
            *(
                (item, issue_source, "issue")
                for item in issue_boundaries
                if issue_source is not None
            ),
        )
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
    scope_items = (
        *(
            (item, issue_source, "issue")
            for item in issue.items
            if item.purpose == "scope" and issue_source is not None
        ),
        *(
            (item, pr_source, "pr_description")
            for item in pr.items
            if item.purpose == "scope"
        ),
    )
    scope = _number_statements(
        scope_items,
        prefix="S",
        role="context",
    )
    verification_expectations = _number_statements(
        tuple(
            (item, issue_source, "issue")
            for item in issue.items
            if item.purpose == "verification" and issue_source is not None
        ),
        prefix="V",
        role="context",
    )
    claims = _number_claims(
        tuple(item for item in pr.items if item.role == "claim"),
        source=pr_source,
    )
    if pr.introductory_intent:
        intent = ReviewStatement(
            id="I1",
            text=pr.introductory_intent,
            role="intent",
            purpose="intent",
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
            purpose="intent",
            authority="pr_title",
            sources=(SourceRef(label="pull request title", url=pr_source.url),),
        )
    return ReviewSemantics(
        intent=intent,
        obligations=requirements,
        objectives=objectives,
        scope=scope,
        verification_expectations=verification_expectations,
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
        tuple(
            item
            for item in parsed.items
            if item.role == "obligation" or item.purpose == "boundary"
        ),
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
    return _number_requirement_items(
        tuple((item, source, authority) for item in items)
    )


def _number_requirement_items(
    items: tuple[tuple[_ParsedItem, SourceRef, StatementAuthority], ...],
) -> tuple[Requirement, ...]:
    deliverable_index = 0
    guardrail_index = 0
    requirements: list[Requirement] = []
    seen_text: set[str] = set()
    for item, source, authority in items:
        normalized_text = item.text.casefold()
        if normalized_text in seen_text:
            continue
        seen_text.add(normalized_text)
        kind = _requirement_kind(item.text)
        if item.purpose == "boundary":
            kind = "guardrail"
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
                purpose="guardrail" if kind == "guardrail" else "acceptance",
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
                purpose=item.purpose,
                authority=authority,
                sources=(_located_source(source, item),),
            )
        )
    return tuple(statements)


def _number_claims(
    items: tuple[_ParsedItem, ...],
    *,
    source: SourceRef,
) -> tuple[ReviewStatement, ...]:
    counters = {"baseline": 0, "verification": 0}
    prefixes = {
        "implementation": "C",
        "boundary": "C",
        "baseline": "B",
        "verification": "VC",
    }
    statements = []
    claim_index = 0
    for item in items:
        purpose = item.purpose
        if purpose in {"implementation", "boundary"}:
            claim_index += 1
            statement_id = f"C{claim_index}"
        else:
            counters[purpose] += 1
            statement_id = f"{prefixes[purpose]}{counters[purpose]}"
        statements.append(
            ReviewStatement(
                id=statement_id,
                text=item.text,
                role="claim",
                purpose=purpose,
                authority="pr_description",
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
