# Facts

## Owns

Canonical evidence construction, path classification, exact-symbol replacement
of mapped hunks, and evidence identity validation.

## Input / output

Source packet, canonical changes, and provider results → one `EvidenceCatalog`.

## Invariants

Each diff location has one canonical representation. Typed routing fields are
first-class contract fields, not metadata conventions.

## Must not

Extract statements, associate R/G, select candidates, or render output.

## Diagnostics

Preserves change-normalization diagnostics as catalog provenance.

## Extension points

New provider facts require a canonical constructor and invariant coverage.
