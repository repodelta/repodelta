# Changes

## Owns

Canonical unified-diff parsing and head/base line semantics.

## Input / output

`ChangedFile[]` → one `DiffHunkCollection` per analysis.

## Invariants

Each hunk owns canonical contiguous `ChangeRelation`s typed as `added`,
`removed`, or `replaced`. Head and base lines remain separate and retain exact
revision-side line numbers and paths. Replacement relations own both sides
together. Hunk snippets are derived from spans rather than stored as parallel
truth. There is no revision-ambiguous changed path.

## Must not

Query Codegraph, construct evidence, match requirements, or select candidates.

## Diagnostics

Reports missing or unparsable patch coverage. Invalid empty or kind/side
relation shapes fail at the model boundary.

## Extension points

Additional patch formats normalize into the same revision-path relation
collection.
