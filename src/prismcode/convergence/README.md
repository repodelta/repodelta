# Convergence

## Owns

Same-focus, same-slot semantic dominance, bridge reachability, ambiguity, and
bounded candidate/display selection.

## Input / output

`ProjectionCandidateSet` → reference-only `CandidateConvergence`.

## Invariants

Candidates never compete across R/G or slots. Direct typed associations
dominate bridges. Claim and structural bridges remain reachable only through
selected upstream relations. Stable source order breaks ties only within one
equivalent semantic tier and the ambiguity remains explicit.

## Must not

Create facts or relations, reclassify evidence, score candidates globally,
infer acceptance, or construct presentation layout.

## Diagnostics

Distinguishes inspection-budget truncation, equivalent-tier display ambiguity,
and bridge candidates made unreachable by upstream convergence.

## Extension points

Evaluated deterministic rules may be added as typed dominance relations. A
future shadow reranker may observe this result but must not create evidence.
