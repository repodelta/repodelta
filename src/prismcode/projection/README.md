# Projection

## Owns

Reference-only selected slices, one canonical review-level structural graph,
and canonical review-wide overview facts.

## Input / output

Typed candidates, `CandidateConvergence`, and packet/provider state →
`ReviewProjection` and `ReviewOverview`.

## Invariants

Profiles remain canonical in the candidate set; selected relations and
convergence diagnostics are referenced from `CandidateConvergence`. Each slice
carries a focus overlay projected from its upstream typed
`ReviewRelevantStructuralClosure`; `ReviewProjection.review_graph` owns
canonical nodes and edges once across all overlays. Nodes use the facts-owned
exact logical review-symbol identity and carry review operation plus base/head
provider evidence provenance. Edges reference only the closure's canonical
`StructuralRelationChangeIdentity` fact IDs; projection never searches all
evidence for relevance or rebuilds edge truth from provider path steps. Selected
structural-change anchors follow canonical `StructuralOwnershipChangeIdentity`
facts to their ancestor nodes through a separate ownership-edge collection.
Revision provenance and deferred ownership never enter the graph. A selected
anchor is structurally isolated only when neither executable nor ownership
edges are available. Focus-relative roles and association/path relation IDs remain in
overlays. Review-wide CI,
source coverage, empty state, and structural coverage are computed once here.
Each G slice references its upstream `GuardrailScanPlan` by ID; projection does
not reconstruct scan scope or query intent. Selected boundary facts are
reference-only relation IDs from convergence.
Every selected structural change is a structural node, including anchors with no
selected edge. Only non-symbol changed facts use the standalone changed-fact
relation list; graph membership never chooses between two representations of
the same mapped change.
Standalone changed facts preserve routing-owned primary, test-support, and
document-support relation groups. Projection partitions those references but
does not infer their roles.
Diagnostic scope and provider remain canonical through attention normalization.

## Must not

Retrieve or reclassify evidence, select paths, inspect arbitrary provider
metadata, or format HTML/CLI copy.

## Diagnostics

Normalizes review-wide attention facts from typed stage diagnostics. Attention
groups require matching scope, provider, slot, and state; review-level provider
coverage never merges with focus-level convergence coverage.

## Extension points

Additional boundary presentation consumes the same upstream plan and fact IDs.
