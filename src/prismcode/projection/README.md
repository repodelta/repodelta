# Projection

## Owns

Reference-only selected slices, one canonical review-level structural graph,
and canonical review-wide overview facts.

## Input / output

Typed candidates, `CandidateConvergence`, canonical `ChangedFile` truth, and
packet/provider state →
`ReviewProjection` and `ReviewOverview`.
`ReviewProjection.verification_workspace` is the single matrix and evidence
inspector boundary over R/G subjects and typed T/CC assessments.
Its transformation summary projects claim groups, observed Base/Head evidence
IDs, association coverage, and assessment counts so presentation never reads
raw contract, observation, alignment, or assessment truth.
`TransformationStructuralClosure` is the sole T/CC structural-membership
authority. Projection converts each closure group into a typed
`TransformationStructuralTopologyGroup`, joins it into the same
review-level `ReviewStructuralGraph`, and passes that overlay to the
workspace. `TransformationAlignment` may contribute observed provenance and
assessment evidence, but it cannot create or remove structural nodes, edges,
ownership edges, or placements.

## Invariants

Profiles remain canonical in the candidate set; selected relations and
convergence diagnostics are referenced from `CandidateConvergence`. Each slice
carries a focus overlay projected from its upstream typed
`ReviewRelevantStructuralClosure`; `ReviewProjection.review_graph` owns
canonical nodes and edges once across all overlays. The same graph also owns
the canonical default change-backbone node, executable-edge, and
ownership-edge IDs. Primary changed anchors seed that backbone; directly
incident added or removed relations may add one endpoint, retained relations
connect only existing backbone members, and required ownership ancestors
organize those members. This selection is non-transitive and leaves all
support/test members in the complete graph and focus overlays. Nodes use the facts-owned
exact logical review-symbol identity and carry one Base-to-Head delta:
`added`, `modified`, `renamed`, `removed`, `retained`, or `unresolved`.
Exact Base+Head support identities are retained; incomplete one-sided support
is unresolved. File-container nodes instead consume the canonical Git
`ChangedFile.status`, so child-span mapping cannot make a changed file appear
retained. Focus-relative roles exist only in `StructuralFocusNode` overlays.
Conflicting deltas for one canonical node identity are rejected rather than
priority-merged. Edges reference only the closure's canonical
`StructuralRelationChangeIdentity` fact IDs; projection never searches all
evidence for relevance or rebuilds edge truth from provider path steps. Selected
structural-change anchors follow revision-local structural ownership provenance
to canonical placements and proven `StructuralOwnershipChangeIdentity` facts
to ownership deltas. Placements converge observed Base/Head containment for one
logical parent/child pair without converting a missing opposite-revision
observation into absence. A selected anchor is structurally isolated only when
neither executable nor placement/ownership evidence is available.
Each structural node also owns one canonical display-evidence reference:
Head for added, modified, renamed, retained, and unresolved nodes when Head
provenance exists; Base for removed nodes when Base provenance exists.
Presentation never selects a revision from evidence order.
Projection also owns canonical executable relation groups. It selects one
primary placement per child, maps concrete edge endpoints to the nearest
distinct ownership cells, and groups only edges with the same display
endpoints, relation, and operation. Every concrete edge remains in exactly one
group with its evidence identity intact. Groups carry the union of member path
provenance, and backbone/focus group IDs are projected from canonical
backbone/focus edge membership. The renderer consumes these groups directly;
it never regroups edges or chooses display endpoints.
Focus-relative roles and association/path relation IDs remain in overlays.
Review-wide CI,
source coverage, empty state, and structural coverage are computed once here.
Each G slice references its upstream `ClosureScanPlan` by ID; projection does
not reconstruct scan scope or query intent. Selected closure facts are
reference-only relation IDs from convergence.
Each slice also owns one `StructuralFocusDisposition`. It partitions selected
non-structural evidence references, deferred structural relation references,
and structural diagnostic references without rerunning routing or convergence.
Its state distinguishes projected, non-structural-only, deferred,
unassociated, unavailable, and empty structural outcomes. The focus overlay
remains the only source of projected node/edge membership.
Every selected structural change is a structural node, including anchors with no
selected edge. Only non-symbol changed facts use the standalone changed-fact
relation list; graph membership never chooses between two representations of
the same mapped change.
Standalone changed facts preserve routing-owned primary, test-support, and
document-support relation groups. Projection partitions those references but
does not infer their roles.
Diagnostic scope and provider remain canonical through attention normalization.
One diagnostic-presentation projection assigns every typed diagnostic exactly
once: review-scoped, unattached, and equivalent cross-focus diagnostics become
review attention; single-focus diagnostics remain on that slice; and
not-applicable diagnostics are explicitly suppressed. `ReviewProjection` and
`ReviewOverview` consume this same disposition rather than independently
deciding where a diagnostic belongs.
The verification workspace preserves every R/G and T/CC subject exactly once.
R/G entries remain explicitly `not_assessed`; projection never upgrades
retrieval relevance into a conclusion. T/CC status and reasons are copied from
the sole `TransformationAssessment` authority. Inspector entries reference
canonical relation, binding, evidence, diagnostic, and shared structural-graph
IDs. T/CC graph overlays are identity joins against the existing shared graph,
not a second graph or another association pass.

## Must not

Retrieve or reclassify evidence, select paths, inspect arbitrary provider
metadata, invent identities for no-association diagnostics, format HTML/CLI
copy, assess R/G, recalculate T/CC status, or delete complete support merely
because it is not part of the default
backbone.

## Diagnostics

Normalizes review-wide attention facts from typed stage diagnostics. Attention
groups require matching scope, provider, slot, and state; review-level provider
coverage never merges with focus-level convergence coverage. The renderer does
not regroup, promote, or suppress diagnostics.

## Extension points

Additional boundary presentation consumes the same upstream plan and fact IDs.
