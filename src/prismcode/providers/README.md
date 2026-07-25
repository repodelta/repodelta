# Providers

## Owns

Read-only external fact acquisition, including exact symbol overlap and bounded
structural paths.

## Input / output

Canonical changes plus provider configuration → provider result and raw
provider diagnostics.

## Invariants

Providers never mutate repositories or indexes and never produce review
conclusions.

## Must not

Reparse patches, construct `EvidenceCatalog`, route requirements, or format CLI
and HTML copy.

## Diagnostics

Reports provider availability, revision, coverage, and traversal limits.

## Extension points

New providers implement explicit protocols and feed canonical fact
normalization.
