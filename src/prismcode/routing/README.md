# Routing

## Owns

Requirement profiles, fact eligibility, authority-aware association, and
complete per-R/G typed candidate enumeration.

## Input / output

Canonical statements and `EvidenceCatalog` → unselected
`ProjectionCandidateSet`.

## Invariants

Eligibility precedes association. Every explicit R/G is visited. Relations
reference canonical IDs, retain typed association reasons, and carry no
selection state.

## Must not

Collect providers, parse patches, order/truncate/select same-slot candidates,
construct final layout, or render diagnostics.

## Diagnostics

Produces typed focus/slot source and association coverage diagnostics.

## Extension points

The convergence stage consumes all typed candidates before projection.
