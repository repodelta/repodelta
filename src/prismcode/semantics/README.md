# Semantics

## Owns

One-pass Markdown section parsing, canonical heading normalization, statement
taxonomy, source authority, stable O/S/R/G/V contract identities, distinct
C/B/VC PR-claim identities, and PR-claim source state.

## Input / output

`ReviewSourcePacket` → `ExtractedReviewSemantics`.

## Invariants

Issue obligations and verification expectations remain the primary contract.
PR statements remain claims or provisional obligations according to their
source section. Heading aliases normalize through an exact canonical vocabulary,
never loose substring matching.

## Must not

Inspect repository facts, match statements to code, select evidence, or infer
acceptance.

## Diagnostics

Exposes source absent, extraction missing, and available claim stages.

## Extension points

New human-authored section conventions belong in this stage.
