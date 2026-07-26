# Projection

## Owns

Reference-only selected slices and canonical review-wide overview facts.

## Input / output

Typed candidates, `CandidateConvergence`, and packet/provider state →
`ReviewProjection` and `ReviewOverview`.

## Invariants

Profiles remain canonical in the candidate set; selected relations and
convergence diagnostics are referenced from `CandidateConvergence`. Slices
carry only IDs. Review-wide CI, source coverage, empty state, and structural
coverage are computed once here. Diagnostic scope and provider remain canonical
through attention normalization.

## Must not

Retrieve or reclassify evidence, inspect arbitrary provider metadata, or format
HTML/CLI copy.

## Diagnostics

Normalizes review-wide attention facts from typed stage diagnostics. Attention
groups require matching scope, provider, slot, and state; review-level provider
coverage never merges with focus-level convergence coverage.

## Extension points

Guardrail scan facts and converged selections enter through upstream typed
contracts.
