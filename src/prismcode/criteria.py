from __future__ import annotations

import re

from .contracts import Requirement, SourceRef

_REQUIREMENT_HEADINGS = {
    "requirement",
    "requirements",
    "acceptance criteria",
    "acceptance criterion",
    "definition of done",
    "success criteria",
}
_CHECKLIST_RE = re.compile(r"^\s*[-*+]\s+\[[ xX]\]\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+?)\s*$")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")


def _clean_markdown_text(value: str) -> str:
    value = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL)
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"[*_~]+", "", value)
    return " ".join(value.strip().split())


def extract_requirement_texts(body: str | None) -> tuple[str, ...]:
    if not body:
        return ()
    current_heading: str | None = None
    values: list[str] = []
    seen: set[str] = set()
    for raw_line in body.splitlines():
        heading_match = _HEADING_RE.match(raw_line)
        if heading_match:
            current_heading = _clean_markdown_text(heading_match.group(1)).casefold()
            continue
        checklist_match = _CHECKLIST_RE.match(raw_line)
        bullet_match = _BULLET_RE.match(raw_line)
        candidate = checklist_match.group(1) if checklist_match else None
        if candidate is None and bullet_match and current_heading in _REQUIREMENT_HEADINGS:
            candidate = bullet_match.group(1)
        if candidate is None:
            continue
        cleaned = _clean_markdown_text(candidate)
        key = cleaned.casefold()
        if cleaned and key not in seen:
            values.append(cleaned)
            seen.add(key)
    return tuple(values)


def extract_requirements(body: str | None, *, source: SourceRef) -> tuple[Requirement, ...]:
    return tuple(
        Requirement(id=f"R{index}", text=text, sources=(source,))
        for index, text in enumerate(extract_requirement_texts(body), start=1)
    )


def extract_intent(body: str | None, title: str) -> str:
    if body:
        paragraph: list[str] = []
        for raw_line in body.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                if paragraph:
                    break
                continue
            if _HEADING_RE.match(raw_line) or _CHECKLIST_RE.match(raw_line) or _BULLET_RE.match(raw_line):
                if paragraph:
                    break
                continue
            paragraph.append(stripped)
        cleaned = _clean_markdown_text(" ".join(paragraph))
        if cleaned:
            return cleaned
    return title
