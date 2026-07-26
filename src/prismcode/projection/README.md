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
`StructuralSupportSet`; `ReviewProjection.review_graph` owns canonical nodes and
edges once across all overlays. Nodes collapse by symbol evidence ID and edges
by deterministic source/relation/direction/target identity. Focus-relative
roles and association/path relation IDs remain in overlays. Review-wide CI,
source coverage, empty state, and structural coverage are computed once here.
Each G slice references its upstream `GuardrailScanPlan` by ID; projection does
not reconstruct scan scope or query intent. Selected boundary facts are
reference-only relation IDs from convergence.
Every selected changed `symbol` is a structural node, including symbols with no
selected edge. Only non-symbol changed facts use the standalone changed-fact
relation list; graph membership never chooses between two representations of
the same mapped change.
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
