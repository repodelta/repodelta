# Convergence

## Owns

Same-focus, same-slot semantic dominance, bridge reachability, competitive-slot
selection, and typed set convergence for changed anchors and verification.

## Input / output

`ProjectionCandidateSet` → reference-only `CandidateConvergence`.

## Invariants

Candidates never compete across R/G or slots. Claims, context, and structural
paths are competitive. Changed anchors and verification are set slots: one
canonical identity does not compete with another.

Changed-anchor identity is its canonical evidence target ID. Distinct direct
anchors are retained together; claim-bridged anchors form a separately bounded
expansion set. Duplicate relations to one target collapse to their strongest
typed association. Direct, bridged, and total identity safety limits can
truncate coverage but never convert multiple relevant anchors into ambiguity.

Claim and structural bridges remain reachable only through selected upstream
relations. In competitive slots, stable source order breaks ties only within one
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

Distinguishes competitive-slot inspection truncation and ambiguity, bridge
candidates made unreachable by upstream convergence, changed-anchor and
verification set truncation, and conflicting outcomes for one verification
identity. Different changed-anchor or check identities never produce semantic
ambiguity merely because several are relevant.

## Extension points

Evaluated deterministic rules may be added as typed dominance relations. A
future shadow reranker may observe this result but must not create evidence.
