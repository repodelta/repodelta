# Facts

## Owns

Canonical evidence construction, path classification, line-level exact-symbol
coverage of change spans, and evidence identity validation.

## Input / output

Source packet, canonical changes, and provider results → one `EvidenceCatalog`.

## Invariants

Each diff location has one canonical representation. Revision-specific changed
symbols remain provenance facts; one typed `StructuralChangeIdentity` pairs
their optional base/head evidence IDs and is the only structural changed
anchor. Added, removed, and modified identities retain the union of their
change-relation IDs, paths, signatures, and revision links. The catalog serializes
the parser-owned `ChangeRelation` collection once; changed evidence references
relation IDs and never re-infers operation from surviving lines. Typed routing
fields are first-class contract fields, not metadata conventions.
Changed anchors carry complete, directional association signatures. Bounded
previews are presentation data and never retrieval input. Exact symbols own
only the changed lines they cover; uncovered lines remain canonical
`change_relation` facts. Raw base/head symbol facts never become a parallel
changed-anchor path.
Verification facts carry first-class provider, kind, normalized name, status,
conclusion, and observed head SHA; downstream stages must not recover those
fields from presentation metadata.
Observed guardrail scans normalize once as `boundary_fact` items carrying their
typed scan result and explicit G association. Unavailable scans never become
evidence.

## Must not

Extract statements, associate R/G, select candidates, or render output.

## Diagnostics

Preserves change-normalization and guardrail-provider diagnostics as catalog
provenance.

## Extension points

New provider facts require a canonical constructor and invariant coverage.
