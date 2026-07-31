# Semantics

## Owns

One-pass Markdown section parsing, canonical heading normalization, statement
taxonomy, source authority, stable O/S/R/G/V contract identities, distinct
C/B/VC PR-claim identities, typed T/CC transformation-contract identities,
and source state.

## Input / output

`ReviewSourcePacket` → `ExtractedReviewSemantics`.

## Invariants

Issue obligations and verification expectations remain the primary contract.
PR statements remain claims or provisional obligations according to their
source section. Heading aliases normalize through an exact canonical vocabulary,
never loose substring matching. Implementation aliases cover common summary,
approach, solution, and semantic-atom conventions through that same vocabulary.
Structured transformation headings produce one PR-authored
`TransformationContract`. The same parse owns its selector predicates: only
explicit inline-code spans become symbol/path selectors, and explicit arrow
sequences become ordered-path selectors. Cleaned claim text remains the
canonical authored statement; raw Markdown is used only while extracting
selectors and is not retained as a parallel contract. Claims without explicit
selectors receive a typed diagnostic instead of a guessed code identity.
Transformation claims do not also enter the generic C claim path and never
become repository observations or assessments.
Boundary aliases cover guardrail, constraint, and safety-boundary conventions;
verification aliases cover regression, test-evidence, and validation-result
conventions. Their source authority remains decisive: Issue boundaries become
G obligations and Issue verification sections become V expectations, while the
same PR sections remain C boundary or VC verification claims.
Authored list labels such as `R1:` or `G2:` are display syntax only: the parser
removes them only in their matching typed section before assigning canonical
IDs, so source formatting cannot become duplicated statement text or override
canonical numbering. A different typed prefix, such as an `R1:` reference in an
implementation claim, remains semantic text for downstream association.

## Must not

Inspect repository facts, match statements to code, select evidence, or infer
acceptance.

## Diagnostics

Exposes source absent, extraction missing, and available claim stages.

## Extension points

New human-authored section conventions belong in this stage.
