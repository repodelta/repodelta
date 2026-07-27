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

Coverage is revision-applicable: the head index is requested only for
structural hunks with added lines, while the base index is requested only for
structural hunks with removed lines. Added-only files cannot make base partial,
and removed-only files cannot make head partial. Revision non-applicability and
non-structural document exclusion remain separate informational provenance.

## Extension points

New providers implement explicit protocols and feed canonical fact
normalization.

## Managed review workspace

`--prepare-codegraph` wraps the existing provider boundary in one explicit
lifecycle. The caller-owned exact head checkout is validated and its index is
initialized or synchronized. Without an explicit base root, PrismCode creates
a detached temporary worktree at the PR base revision, initializes its index,
and removes both through `finally` after success or failure. Explicit
`--base-repo-root` inputs remain caller-owned and are never deleted.

The workspace manager never switches branches, resets tracked content, invokes
a shell, or turns preparation failure into structural evidence.
