# Evaluation

## Owns

Offline comparison of production contracts with declared golden IDs and
thresholds.

## Input / output

Evaluation suite → deterministic metrics and evaluation diagnostics.

## Invariants

Evaluation invokes the production pipeline and does not implement another
retriever or renderer.

## Must not

Change candidate selection, create production facts, or convert relevance into
acceptance.

## Diagnostics

Reports expectation and threshold failures only.

## Extension points

New semantic stages add golden assertions before changing production behavior.
