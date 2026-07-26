# Deterministic review fact routing

Fact routing is a typed retrieval layer, not a conclusion layer.

```text
canonical statements + EvidenceCatalog
  -> eligibility by fact profile and projection slot
  -> deterministic association inside each slot
  -> ProjectionCandidateSet
  -> deterministic same-slot CandidateConvergence
  -> ReviewProjection
```

## Slots

Every R/G is visited independently. Its candidates are separated into:

- PR-authored claims;
- changed anchors;
- unchanged runtime context;
- test context;
- current-head verification observations;
- bounded structural paths;
- guardrail scan-plan-aware coverage diagnostics.

PR claims, changed symbols, paths, and CI observations never compete in one
numeric score or global candidate budget. Claims are a compact competitive
selection. Changed anchors and current-head verification are typed identity
sets; structural paths and runtime/test context are the bounded identity sets
of a reference-only evidence subgraph.

## Associations

Typed deterministic association kinds, in convergence dominance order, are:

1. provider-supplied explicit association;
2. explicit R/G reference;
3. exact distinctive identifier;
4. distinctive multi-token phrase;
5. claim bridge;
6. structural bridge;
7. current-head observation;

A generic one-token overlap is not enough for default selection. Numbers are
not used to compare facts from different slots.

## Structural routing

Routing enumerates structural relations for candidate exact changed symbols.
Convergence derives canonical anchor-terminal connections from those paths and
typed runtime/test contexts, retains shortest support for distinct terminals
first, and selects paths and contexts atomically. Per-anchor and total path
limits, and separate context identity limits, are safety boundaries rather than
relevance competitions. Context found only through a safety-deferred connection
is reported as `upstream_deferred`. Direct/provider context without a structural
bridge remains standalone. Without Codegraph, the same projection uses
canonical changed-hunk or changed-file fallback and records typed structural
diagnostics.

## Coverage

Typed diagnostics distinguish source absence, non-applicability, no eligible
fact, no deterministic association, ambiguity, provider unavailability,
partial coverage, stale sources, safety truncation, upstream deferral, and
unsupported change types.

`EvidenceCatalog` remains the only evidence store. Candidate relations,
convergence groups, and projection slices contain canonical IDs only.

## Semantic identity and ordering

Eligibility runs before association and uses fact authority, revision side,
change operation, role, and profile. Routing reads complete typed association
signatures, never bounded display previews. Head and base signatures are never
collapsed into one undirected string; base terms are admitted only for
removal-oriented or guardrail focus. Repository-local `R1`/`G1` tokens are not
treated as issue references.

Changed-anchor convergence retains distinct canonical evidence target IDs.
Direct associations and claim-bridged expansion have separate safety limits,
plus a total identity limit. Crossing those limits reports coverage truncation;
multiple relevant anchors do not produce ambiguity.

Convergence is ordinal inside the remaining competitive claim slot. Typed
association dominance is applied before stable source ordinal. Opaque evidence
hashes are stable identifiers, not ranking signals. When an equivalent claim
tier crosses a display budget, the selected prefix remains deterministic and
an ambiguity diagnostic states that source order is only a presentation
tie-break.

Verification convergence uses first-class `(provider, kind, normalized name)`
identity. Different identities are retained together. Equivalent observations
for one identity collapse; conflicting completed outcomes for one identity
remain visible as `conflicting_facts`. Only a separate identity-count safety
limit can truncate verification, retaining failure before pending before success
at that boundary. Stale-head observations are filtered during routing.

Provider coverage belongs to the review and carries affected IDs. Claim
coverage distinguishes an absent PR description, a present description with no
typed extracted claims, and extracted claims with no association.

Guardrails currently emit an explicit missing bounded-scan diagnostic. Selected
changed anchors are not relabeled as absence proof.
