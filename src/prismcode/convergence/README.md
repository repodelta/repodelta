# Convergence

## Owns

Same-focus, same-slot semantic dominance, bridge reachability, ambiguity, and
bounded candidate/display selection. It also owns verification-set convergence:
distinct current-head check identities are retained together, while equivalent
observations for one identity are collapsed.

## Input / output

`ProjectionCandidateSet` → reference-only `CandidateConvergence`.

## Invariants

Candidates never compete across R/G or slots. Claim, changed-anchor, context,
and structural-path slots are competitive. Verification is a set slot: one
check identity does not compete with another.

Direct typed associations dominate bridges. Claim and structural bridges remain
reachable only through selected upstream relations. Stable source order breaks
ties only within one equivalent semantic tier and the ambiguity remains
explicit.

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

Distinguishes inspection-budget truncation, equivalent-tier display ambiguity,
bridge candidates made unreachable by upstream convergence, verification-set
truncation, and conflicting outcomes for one verification identity. Different
check identities never produce semantic ambiguity.

## Extension points

Evaluated deterministic rules may be added as typed dominance relations. A
future shadow reranker may observe this result but must not create evidence.
