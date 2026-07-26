# Changes

## Owns

Canonical unified-diff parsing and head/base line semantics.

## Input / output

`ChangedFile[]` → one `DiffHunkCollection` per analysis.

## Invariants

Each hunk owns contiguous replacement/addition/deletion spans. Head and base
lines remain separate and retain exact revision-side line numbers. Hunk
snippets are derived from spans rather than stored as parallel truth.

## Must not

Query Codegraph, construct evidence, match requirements, or select candidates.

## Diagnostics

Reports missing or unparsable patch coverage.

## Extension points

Rename and additional patch formats normalize into the same collection.
