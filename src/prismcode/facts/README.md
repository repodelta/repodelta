# Facts

## Owns

Canonical evidence construction, path classification, line-level exact-symbol
coverage of change spans, evidence identity validation, and claim-independent
observed-transformation reconstruction.

## Input / output

Source packet, canonical changes, and provider results → one `EvidenceCatalog`.
The catalog then projects once into a reference-only `ObservedTransformation`.

## Invariants

Each diff location has one canonical representation. Revision-specific symbols
retain their provider IDs as provenance, while an exact logical identity over
repository-relative path, qualified name, and symbol kind is canonical across
base/head. A same-revision collision stays distinct rather than being inferred
as the same symbol. One typed `StructuralChangeIdentity` pairs optional
base/head evidence IDs under that review identity and is the only structural
changed anchor. Added, removed, and modified identities retain the union of
their change-relation IDs, paths, signatures, and revision links. Exact
provider-owned counterpart symbols complete an otherwise one-sided changed
identity before operation truth is constructed. They retain `revision_fact`
provenance, carry no structural paths, and never become independent routing
candidates. A missing counterpart implies addition or removal only when typed
provider coverage proves that exact identity was queried on the opposite
revision. Missing, stale, partial, or failed coverage remains uncertainty.
Structural change operations come from canonical base/head presence when every
associated replacement relation has complete opposite-revision directional
line mapping. Mapping another relation in the same hunk is never absence proof.
A file symbol follows the GitHub changed-file status, so a module-level overlap
cannot turn a modified file into an added file. Without applicable
opposite-revision identity or complete absence proof, a one-sided symbol is
explicitly `unresolved`; downstream stages never reconstruct or guess its
revision delta.
Exact parser-owned replacement relations may connect one removed and one added
structural change of the same symbol kind in a typed
`StructuralReplacementCandidate`. Candidates only reference the authoritative
endpoint facts: they do not rewrite an operation, enter evidence routing, choose
among many-to-many possibilities, or assert a rename. No lexical, path, name,
embedding, or model similarity is used at this boundary.
Revision path steps converge into one canonical
`StructuralRelationChangeIdentity` per
directed review-symbol edge. Its base/head path IDs and provider endpoints are
provenance only. Retained
edges require observations on both revisions; added or removed edges require
an added/removed endpoint or complete opposite-revision traversal. Incomplete
coverage remains an explicit diagnostic and never becomes an absence claim.
Revision-local structural ownership observations reference their parent and
child symbol provenance. They converge once into one canonical
`StructuralOwnershipChangeIdentity` per review-symbol parent/child pair. Retained
ownership requires both revisions; added/removed ownership requires a changed
endpoint or complete ownership coverage applicable to the same child on the
opposite revision. Deferred ownership remains revision provenance and one
aggregated partial-coverage diagnostic. Ownership identities stay distinct
from executable `StructuralRelationChangeIdentity` edges.
The catalog serializes the parser-owned `ChangeRelation` collection once;
changed evidence references
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
`ObservedTransformation` references every canonical changed anchor, structural
delta, replacement candidate, structural path, and verification observation
once. Its Base/Head topology membership comes only from facts-owned revision
provenance. It never reads the authored `TransformationContract`.
Observed guardrail scans normalize once as `boundary_fact` items carrying their
typed scan result and explicit G association. Unavailable scans never become
evidence.

## Must not

Extract statements, profile review focuses, determine focus-relative fact
eligibility or support roles, associate R/G, select candidates, or render
output. Reconstruction must not infer authority, migration intent, completion,
absence, or assessment status.

## Diagnostics

Preserves change-normalization and guardrail-provider diagnostics as catalog
provenance.

## Extension points

New provider facts require a canonical constructor and invariant coverage.
