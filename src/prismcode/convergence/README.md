# Convergence

## Owns

Same-focus, same-slot semantic dominance, bridge reachability, compact claim
selection, typed set convergence, and bounded structural evidence subgraphs.

## Input / output

`ProjectionCandidateSet` → reference-only `CandidateConvergence`.

## Invariants

Candidates never compete across R/G or slots. Claims are compact competitive
selections. Changed anchors and verification are set slots: one canonical
identity does not compete with another.

Changed-anchor identity is its canonical evidence target ID. Distinct direct
anchors are retained together; claim-bridged anchors form a separately bounded
expansion set. Duplicate relations to one target collapse to their strongest
typed association. Direct, bridged, and total identity safety limits can
truncate coverage but never convert multiple relevant anchors into ambiguity.

Structural paths and structurally bridged runtime/test contexts converge as one
terminal-aware unit. For each reachable anchor-terminal connection, shortest
canonical path identities are eligible; distinct terminal coverage precedes
redundant equivalent support. Per-anchor, total-path, and context-identity
limits apply only to that peripheral connection set. One
`ReviewRelevantStructuralClosure` replaces terminal-only support: it references
the selected path relations plus every already-collected canonical
relation-change fact whose endpoints are selected anchors, selected terminals,
or nodes on retained connecting paths. Direct review-relevant edges do not
compete with terminal path budgets. All other path provenance remains canonical
in the group's deferred relation IDs. Direct/provider context without a path
bridge remains standalone. A terminal available only behind a safety-deferred
connection is `upstream_deferred`, not unassociated.

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

## Extension points

Evaluated deterministic rules may be added as typed dominance relations. A
future shadow reranker may observe this result but must not create evidence.
