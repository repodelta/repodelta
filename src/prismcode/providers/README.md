# Providers

## Owns

Read-only external fact acquisition, including exact symbol overlap and bounded
structural paths.

## Input / output

Canonical changes plus revision-specific provider configuration → one
`StructuralGraphCollection` containing typed head/base results and raw
provider diagnostics.

## Invariants

Providers never mutate repositories or indexes and never produce review
conclusions.

## Must not

Reparse patches, construct `EvidenceCatalog`, route requirements, or format CLI
and HTML copy.

## Diagnostics

Reports provider availability, revision side, checkout revision, coverage, and
traversal limits. Head maps added lines; base maps removed lines through the
same provider implementation.

## Extension points

New providers implement explicit protocols and feed canonical fact
normalization.
