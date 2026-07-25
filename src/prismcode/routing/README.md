# Routing

## Owns

Requirement profiles, fact eligibility, authority-aware association, and
per-R/G typed candidate groups.

## Input / output

Canonical statements and `EvidenceCatalog` → `ProjectionCandidateSet`.

## Invariants

Eligibility precedes association. Every explicit R/G is visited. Relations
reference canonical IDs and are not acceptance conclusions.

## Must not

Collect providers, parse patches, implement same-slot semantic convergence,
construct final layout, or render diagnostics.

## Diagnostics

Produces typed focus/slot coverage and budget diagnostics.

## Extension points

Same-slot semantic convergence will consume these typed candidates before
projection selection.
