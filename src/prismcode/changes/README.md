# Changes

## Owns

Canonical unified-diff parsing and head/base line semantics.

## Input / output

`ChangedFile[]` → one `DiffHunkCollection` per analysis.

## Invariants

Each hunk owns canonical contiguous `ChangeRelation`s typed as `added`,
`removed`, or `replaced`. Head and base lines remain separate and retain exact
revision-side line numbers. Replacement relations own both sides together. Hunk
snippets are derived from spans rather than stored as parallel truth.

## Must not

Query Codegraph, construct evidence, match requirements, or select candidates.

## Diagnostics

Reports missing or unparsable patch coverage. Invalid empty or kind/side
relation shapes fail at the model boundary.

## Extension points

Rename and additional patch formats normalize into the same relation
collection.
