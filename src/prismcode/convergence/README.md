# Convergence

## Owns

Same-focus, same-slot semantic dominance, bridge reachability, compact claim
selection, typed set convergence, and bounded structural evidence subgraphs.

## Input / output

`ProjectionCandidateSet` → reference-only `CandidateConvergence`.

`TransformationContract` + `TransformationSubjectSelection` +
`EvidenceCatalog` → reference-only `TransformationStructuralClosure`.

## Invariants

Candidates never compete across R/G or slots. Claims are compact competitive
selections. Changed anchors and verification are set slots: one canonical
identity does not compete with another.

Changed-anchor identity is its canonical evidence target ID. Distinct direct
anchors are retained together; claim-bridged anchors form a separately bounded
expansion set. Duplicate relations to one target collapse to their strongest
typed association. Direct, bridged, and total identity safety limits can
truncate coverage but never convert multiple relevant anchors into ambiguity.
Within those safety boundaries, the routing-owned focus-evidence role retains
primary anchors before test and document support. Convergence never derives the
role or suppresses a support lane semantically.

Structural paths and structurally bridged runtime/test contexts converge under
one `ReviewRelevantStructuralClosure` authority. The closure first retains a
canonical path for each observed changed-anchor-to-changed-anchor backbone
connection, then adds one canonical support path per distinct runtime/test
terminal. A path shared by multiple obligations is stored once. Equivalent
shortest paths are provenance alternatives, not separate coverage obligations,
so they remain deferred rather than consuming the safety budget.

Per-anchor, total-path, and context-identity limits apply only at complete path
identity boundaries. Diagnostics count uncovered backbone and terminal
obligations; they do not describe the number of raw reachable path candidates.
The closure references the retained path relations plus every already-collected
canonical relation-change fact whose endpoints are selected anchors, selected
terminals, or nodes on retained paths. Direct review-relevant edges do not
compete with path budgets. Direct/provider context without a path bridge remains
standalone. A terminal available only behind a safety-deferred closure
obligation is `upstream_deferred`, not unassociated.

Claim bridges remain reachable only through selected claims. In the remaining
competitive claim slot, stable source order breaks ties only within one
equivalent semantic tier and the ambiguity remains explicit.

Verification identity is the first-class `(provider, kind, normalized name)`
tuple carried by the evidence fact. Convergence does not reconstruct identity
from metadata. Equivalent observations for one identity collapse; conflicting
completed outcomes for that identity remain selected and produce
`conflicting_facts`. A separate identity-count safety limit may truncate the set;
only at that boundary are failure, pending, and success ordered for retention.

## Must not

Create facts or relations, reclassify evidence, score candidates globally,
infer acceptance, or construct presentation layout.

## Diagnostics

Distinguishes claim inspection truncation and ambiguity, upstream safety
deferral, changed-anchor/path/context/verification set truncation, and
conflicting outcomes for one verification identity. Multiple relevant
anchor, path, context, or check identities never produce semantic ambiguity.
Support omission is a deterministic presentation projection over already
selected facts; it is not provider or convergence truncation.

Transformation structural closure is a separate pre-alignment authority. It
starts only from exact subject-selection seeds, reuses the provider's
already-collected structural paths, retains complete path identities within a
three-hop and identity safety boundary, and attaches the corresponding
canonical relation-change and bounded ownership-change facts. It never calls a
provider or performs another BFS. Deferred whole paths remain explicit coverage
diagnostics rather than being partially represented. Projection consumes these
IDs through `TransformationStructuralTopology`; alignment does not participate
in structural membership.

## Extension points

Evaluated deterministic rules may be added as typed dominance relations. A
future shadow reranker may observe this result but must not create evidence.
