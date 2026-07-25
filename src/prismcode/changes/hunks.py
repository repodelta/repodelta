from __future__ import annotations

import re
from dataclasses import dataclass

from prismcode.model.contracts import ChangedFile, Diagnostic, SourceRef

_HUNK_HEADER = re.compile(
    r"^@@\s+-(?P<old_start>\d+)(?:,(?P<old_count>\d+))?"
    r"\s+\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))?\s+@@"
)


@dataclass(frozen=True)
class ChangedHunk:
    id: str
    file_path: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    added_lines: tuple[int, ...] = ()
    removed_lines: tuple[int, ...] = ()
    old_snippet: str = ""
    new_snippet: str = ""

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
    current: dict[str, object] | None = None
    old_line = 0
    new_line = 0

    def finish() -> None:
        nonlocal current
        if current is None:
            return
        index = len(parsed)
        parsed.append(
            ChangedHunk(
                id=f"hunk:{file_path}:{index}",
                file_path=file_path,
                old_start=int(current["old_start"]),
                old_count=int(current["old_count"]),
                new_start=int(current["new_start"]),
                new_count=int(current["new_count"]),
                added_lines=tuple(current["added_lines"]),  # type: ignore[arg-type]
                removed_lines=tuple(current["removed_lines"]),  # type: ignore[arg-type]
                old_snippet="\n".join(current["old_snippet"]),  # type: ignore[arg-type]
                new_snippet="\n".join(current["new_snippet"]),  # type: ignore[arg-type]
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
                "added_lines": [],
                "removed_lines": [],
                "old_snippet": [],
                "new_snippet": [],
            }
            continue
        if current is None or raw_line == r"\ No newline at end of file":
            continue
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            added_lines = current["added_lines"]
            assert isinstance(added_lines, list)
            added_lines.append(new_line)
            new_snippet = current["new_snippet"]
            assert isinstance(new_snippet, list)
            new_snippet.append(raw_line[1:])
            new_line += 1
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            removed_lines = current["removed_lines"]
            assert isinstance(removed_lines, list)
            removed_lines.append(old_line)
            old_snippet = current["old_snippet"]
            assert isinstance(old_snippet, list)
            old_snippet.append(raw_line[1:])
            old_line += 1
        else:
            old_line += 1
            new_line += 1

    finish()
    return tuple(parsed)
