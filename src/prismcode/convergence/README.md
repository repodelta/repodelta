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

Structural paths form the bounded union rooted in selected changed anchors.
Duplicate relations to one path target collapse, then shorter paths are retained
first only when per-anchor or total identity safety limits are crossed.
Runtime and test contexts form canonical identity sets reachable through the
selected paths. After all slots converge, `StructuralSupportSet` partitions the
selected structural path relations into displayed support and omitted
provenance. For every reachable selected anchor/context pair it retains the
shortest canonical selected path identities; equivalent shortest identities
remain provenance, while longer redundant paths do not enter projection. A
context available only behind a safety-deferred path is `upstream_deferred`, not
unassociated.

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
