# Providers

## Owns

Read-only external fact acquisition, including exact symbol overlap and bounded
structural paths.

## Input / output

Canonical changes plus revision-specific provider configuration → one
`StructuralGraphCollection` containing typed head/base results and raw
provider diagnostics.

## Invariants

Structural overlap coverage and queries use only the path belonging to the
provider revision. A head provider never probes a base path and a base provider
never probes a head path. After both directional overlap results exist, each
provider performs one exact local lookup for the other revision's changed
symbol identities using repository path, qualified name, and symbol kind.
Those counterpart symbols are separate revision provenance: they do not become
hunk overlaps, traversal seeds, or paths. Existing local overlaps win by
identity and are never duplicated. Typed counterpart coverage names only the
exact identities whose revision-specific files passed index inspection; only
that set can prove exact absence.

Providers never mutate repositories or indexes and never produce review
conclusions.

## Must not

Reparse patches, construct `EvidenceCatalog`, route requirements, or format CLI
and HTML copy.

## Diagnostics

Reports provider availability, revision side, checkout revision, coverage, and
traversal limits. Structural expansion is depth-phased across the review and
round-robin fair between seeds within a depth. Head maps added lines; base maps
removed lines through the same provider implementation. Exact counterpart
query failure is reported explicitly and never fabricates opposite-revision
presence.

Codegraph `contains` edges are emitted through the separate
`StructuralOwnershipRelation` contract for exact and bounded-path symbols.
Ownership ancestry has its own depth and relation-count safety boundary,
deduplicates parent/child identities, rejects cycles, and never becomes a
runtime/test path or consumes traversal path budgets. The result carries typed
ownership coverage with its observed-symbol applicability set, relation count,
state, and limiting dimensions so downstream convergence never treats an
unobserved opposite revision as absence.

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
