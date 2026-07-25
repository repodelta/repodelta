# Changes

## Owns

Canonical unified-diff parsing and head/base line semantics.

## Input / output

`ChangedFile[]` → one `DiffHunkCollection` per analysis.

## Invariants

Head and base snippets remain separate. Every consumer receives the same hunk
IDs and line ranges.

## Must not

Query Codegraph, construct evidence, match requirements, or select candidates.

## Diagnostics

Reports missing or unparsable patch coverage.

## Extension points

Rename and additional patch formats normalize into the same collection.
