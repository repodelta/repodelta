# Projection

## Owns

Reference-only selected slices and canonical review-wide overview facts.

## Input / output

Typed candidates plus packet/provider state → `ReviewProjection` and
`ReviewOverview`.

## Invariants

Profiles and diagnostics remain canonical in the candidate set; slices carry
only their IDs. Review-wide CI, source coverage, empty state, and structural
coverage are computed once here.

## Must not

Retrieve or reclassify evidence, inspect arbitrary provider metadata, or format
HTML/CLI copy.

## Diagnostics

Normalizes review-wide attention facts from typed stage diagnostics.

## Extension points

Guardrail scan facts and converged selections enter through upstream typed
contracts.
