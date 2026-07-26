from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TypedDict

from prismcode.model.contracts import ChangedFile, Diagnostic, SourceRef

_HUNK_HEADER = re.compile(
    r"^@@\s+-(?P<old_start>\d+)(?:,(?P<old_count>\d+))?"
    r"\s+\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))?\s+@@"
)


@dataclass(frozen=True)
class ChangedLine:
    number: int
    text: str


class _MutableSpan(TypedDict):
    added: list[ChangedLine]
    removed: list[ChangedLine]


class _MutableHunk(TypedDict):
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    spans: list[_MutableSpan]
    current_span: _MutableSpan | None


@dataclass(frozen=True)
class ChangedSpan:
    id: str
    hunk_id: str
    file_path: str
    added: tuple[ChangedLine, ...] = ()
    removed: tuple[ChangedLine, ...] = ()

    @property
    def added_lines(self) -> tuple[int, ...]:
        return tuple(item.number for item in self.added)

    @property
    def removed_lines(self) -> tuple[int, ...]:
        return tuple(item.number for item in self.removed)

    @property
    def new_snippet(self) -> str:
        return "\n".join(item.text for item in self.added)

    @property
    def old_snippet(self) -> str:
        return "\n".join(item.text for item in self.removed)

    @property
    def is_deletion_only(self) -> bool:
        return bool(self.removed) and not self.added


@dataclass(frozen=True)
class ChangedHunk:
    id: str
    file_path: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    spans: tuple[ChangedSpan, ...] = ()

    @property
    def added_lines(self) -> tuple[int, ...]:
        return tuple(line for span in self.spans for line in span.added_lines)

    @property
    def removed_lines(self) -> tuple[int, ...]:
        return tuple(line for span in self.spans for line in span.removed_lines)

    @property
    def old_snippet(self) -> str:
        return "\n".join(span.old_snippet for span in self.spans if span.old_snippet)

    @property
    def new_snippet(self) -> str:
        return "\n".join(span.new_snippet for span in self.spans if span.new_snippet)

    @property
    def is_deletion_only(self) -> bool:
        return bool(self.removed_lines) and not self.added_lines


@dataclass(frozen=True)
class DiffHunkCollection:
    hunks: tuple[ChangedHunk, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()


def parse_changed_files(changed_files: tuple[ChangedFile, ...]) -> DiffHunkCollection:
    hunks: list[ChangedHunk] = []
    diagnostics: list[Diagnostic] = []
    for changed_file in changed_files:
        if not changed_file.patch:
            diagnostics.append(
                Diagnostic(
                    code="structural_graph_patch_unavailable",
                    message=(
                        f"GitHub did not provide patch text for {changed_file.path}; "
                        "hunk-to-symbol mapping was not attempted."
                    ),
                    sources=(
                        SourceRef(
                            label="changed file",
                            url=changed_file.source_url,
                            path=changed_file.path,
                        ),
                    ),
                )
            )
            continue
        hunks.extend(parse_unified_patch(changed_file.path, changed_file.patch))
    return DiffHunkCollection(tuple(hunks), tuple(diagnostics))


def parse_unified_patch(file_path: str, patch: str) -> tuple[ChangedHunk, ...]:
    parsed: list[ChangedHunk] = []
    current: _MutableHunk | None = None
    old_line = 0
    new_line = 0

    def finish_span() -> None:
        if current is None:
            return
        span = current["current_span"]
        if span is None:
            return
        current["spans"].append(span)
        current["current_span"] = None

    def active_span() -> _MutableSpan:
        assert current is not None
        span = current["current_span"]
        if span is None:
            span = {"added": [], "removed": []}
            current["current_span"] = span
        return span

    def finish() -> None:
        nonlocal current
        if current is None:
            return
        finish_span()
        index = len(parsed)
        hunk_id = f"hunk:{file_path}:{index}"
        parsed.append(
            ChangedHunk(
                id=hunk_id,
                file_path=file_path,
                old_start=int(current["old_start"]),
                old_count=int(current["old_count"]),
                new_start=int(current["new_start"]),
                new_count=int(current["new_count"]),
                spans=tuple(
                    ChangedSpan(
                        id=f"{hunk_id}:span:{span_index}",
                        hunk_id=hunk_id,
                        file_path=file_path,
                        added=tuple(span["added"]),
                        removed=tuple(span["removed"]),
                    )
                    for span_index, span in enumerate(current["spans"])
                ),
            )
        )
        current = None

    for raw_line in patch.splitlines():
        header = _HUNK_HEADER.match(raw_line)
        if header:
            finish()
            old_line = int(header.group("old_start"))
            new_line = int(header.group("new_start"))
            current = {
                "old_start": old_line,
                "old_count": int(header.group("old_count") or 1),
                "new_start": new_line,
                "new_count": int(header.group("new_count") or 1),
                "spans": [],
                "current_span": None,
            }
            continue
        if current is None or raw_line == r"\ No newline at end of file":
            continue
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            active_span()["added"].append(ChangedLine(new_line, raw_line[1:]))
            new_line += 1
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            active_span()["removed"].append(ChangedLine(old_line, raw_line[1:]))
            old_line += 1
        else:
            finish_span()
            old_line += 1
            new_line += 1

    finish()
    return tuple(parsed)
