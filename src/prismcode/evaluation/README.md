# Evaluation

## Owns

Offline comparison of production projection and transformation-assessment
contracts with declared golden IDs and thresholds.

## Input / output

Evaluation suite → deterministic metrics and evaluation diagnostics.

## Invariants

Evaluation invokes the production pipeline and observes analyzer-owned
assessment output; it does not implement another retriever, assessor, or
renderer.

## Must not

Change candidate selection, create production facts, or convert relevance into
acceptance.

## Diagnostics

Reports expectation and threshold failures only.

## Extension points

New semantic stages add golden assertions before changing production behavior;
assessment assertions identify exact claim/predicate status, reason, and
evidence contracts.
