# Semantics

## Owns

One-pass Markdown section parsing, statement taxonomy, source authority, stable
R/G/O/S/C/B/V identities, and PR-claim source state.

## Input / output

`ReviewSourcePacket` → `ExtractedReviewSemantics`.

## Invariants

Issue obligations remain the primary contract. PR statements remain claims or
provisional obligations according to their source section.

## Must not

Inspect repository facts, match statements to code, select evidence, or infer
acceptance.

## Diagnostics

Exposes source absent, extraction missing, and available claim stages.

## Extension points

New human-authored section conventions belong in this stage.
