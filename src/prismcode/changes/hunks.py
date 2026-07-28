from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TypedDict

from prismcode.model.contracts import (
    ChangeRelation,
    ChangedFile,
    ChangedLine,
    Diagnostic,
    SourceRef,
)

_HUNK_HEADER = re.compile(
    r"^@@\s+-(?P<old_start>\d+)(?:,(?P<old_count>\d+))?"
    r"\s+\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))?\s+@@"
)


class _MutableRelation(TypedDict):
    added: list[ChangedLine]
    removed: list[ChangedLine]


class _MutableHunk(TypedDict):
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    relations: list[_MutableRelation]
    current_relation: _MutableRelation | None


@dataclass(frozen=True)
class ChangedHunk:
    id: str
    base_path: str | None
    head_path: str | None
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    relations: tuple[ChangeRelation, ...] = ()

    @property
    def added_lines(self) -> tuple[int, ...]:
        return tuple(
            line for relation in self.relations for line in relation.added_lines
        )

    @property
    def removed_lines(self) -> tuple[int, ...]:
        return tuple(
            line for relation in self.relations for line in relation.removed_lines
        )

    @property
    def old_snippet(self) -> str:
        return "\n".join(
            relation.old_snippet
            for relation in self.relations
            if relation.old_snippet
        )

    @property
    def new_snippet(self) -> str:
        return "\n".join(
            relation.new_snippet
            for relation in self.relations
            if relation.new_snippet
        )

    @property
    def is_deletion_only(self) -> bool:
        return bool(self.removed_lines) and not self.added_lines

    def path_for_revision(self, revision_side: str) -> str:
        path = self.base_path if revision_side == "base" else self.head_path
        if path is None:
            raise ValueError(f"{self.id}: no {revision_side} path exists")
        return path


@dataclass(frozen=True)
class DiffHunkCollection:
    hunks: tuple[ChangedHunk, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()


def parse_changed_files(changed_files: tuple[ChangedFile, ...]) -> DiffHunkCollection:
    hunks: list[ChangedHunk] = []
    diagnostics: list[Diagnostic] = []
    for changed_file in changed_files:
        display_path = changed_file.display_path
        if not changed_file.patch:
            diagnostics.append(
                Diagnostic(
                    code="structural_graph_patch_unavailable",
                    message=(
                        f"GitHub did not provide patch text for {display_path}; "
                        "hunk-to-symbol mapping was not attempted."
                    ),
                    sources=(
                        SourceRef(
                            label="changed file",
                            url=changed_file.source_url,
                            path=display_path,
                        ),
                    ),
                )
            )
            continue
        hunks.extend(
            parse_unified_patch(
                changed_file.head_path,
                changed_file.patch,
                base_path=changed_file.base_path,
            )
        )
    return DiffHunkCollection(tuple(hunks), tuple(diagnostics))


def parse_unified_patch(
    head_path: str | None,
    patch: str,
    *,
    base_path: str | None = None,
) -> tuple[ChangedHunk, ...]:
    if base_path is None and head_path is not None:
        base_path = head_path
    if base_path is None and head_path is None:
        raise ValueError("unified patch requires a base or head path")
    parsed: list[ChangedHunk] = []
    current: _MutableHunk | None = None
    old_line = 0
    new_line = 0

    def finish_relation() -> None:
        if current is None:
            return
        relation = current["current_relation"]
        if relation is None:
            return
        current["relations"].append(relation)
        current["current_relation"] = None

    def active_relation() -> _MutableRelation:
        assert current is not None
        relation = current["current_relation"]
        if relation is None:
            relation = {"added": [], "removed": []}
            current["current_relation"] = relation
        return relation

    def finish() -> None:
        nonlocal current
        if current is None:
            return
        finish_relation()
        index = len(parsed)
        identity_path = (
            head_path
            if base_path == head_path
            else f"{base_path or ''}→{head_path or ''}"
        )
        hunk_id = f"hunk:{identity_path}:{index}"
        parsed.append(
            ChangedHunk(
                id=hunk_id,
                base_path=base_path,
                head_path=head_path,
                old_start=int(current["old_start"]),
                old_count=int(current["old_count"]),
                new_start=int(current["new_start"]),
                new_count=int(current["new_count"]),
                relations=tuple(
                    ChangeRelation(
                        id=f"{hunk_id}:change:{relation_index}",
                        hunk_id=hunk_id,
                        base_path=base_path,
                        head_path=head_path,
                        kind=(
                            "replaced"
                            if relation["added"] and relation["removed"]
                            else "added"
                            if relation["added"]
                            else "removed"
                        ),
                        added=tuple(relation["added"]),
                        removed=tuple(relation["removed"]),
                    )
                    for relation_index, relation in enumerate(
                        current["relations"]
                    )
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
                "relations": [],
                "current_relation": None,
            }
            continue
        if current is None or raw_line == r"\ No newline at end of file":
            continue
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            active_relation()["added"].append(
                ChangedLine(new_line, raw_line[1:])
            )
            new_line += 1
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            active_relation()["removed"].append(
                ChangedLine(old_line, raw_line[1:])
            )
            old_line += 1
        else:
            finish_relation()
            old_line += 1
            new_line += 1

    finish()
    return tuple(parsed)
