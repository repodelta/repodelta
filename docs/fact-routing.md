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
- guardrail coverage diagnostics.

PR claims, changed symbols, paths, and CI observations never compete in one
numeric score or global candidate budget.

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
Convergence retains paths only when their typed seed anchor was selected, then
retains runtime/test context only when its path was selected. Without
Codegraph, the same projection uses canonical changed-hunk or changed-file
fallback and records typed structural diagnostics.

## Coverage

Typed diagnostics distinguish source absence, non-applicability, no eligible
fact, no deterministic association, ambiguity, provider unavailability,
partial coverage, stale sources, per-slot truncation, and unsupported change
types.

`EvidenceCatalog` remains the only evidence store. Candidate relations,
convergence groups, and projection slices contain canonical IDs only.

## Semantic identity and ordering

Eligibility runs before association and uses fact authority, revision side,
change operation, role, and profile. Head- and base-side hunk text are never
collapsed into one matching string. Repository-local `R1`/`G1` tokens are not
treated as issue references.

Convergence is ordinal inside each typed slot. Typed association dominance is
applied before stable source ordinal. Opaque evidence hashes are stable
identifiers, not ranking signals. When an equivalent tier crosses a display
budget, the selected prefix remains deterministic and an ambiguity diagnostic
states that source order is only a presentation tie-break.

Provider coverage belongs to the review and carries affected IDs. Claim
coverage distinguishes an absent PR description, a present description with no
typed extracted claims, and extracted claims with no association.

Guardrails currently emit an explicit missing bounded-scan diagnostic. Selected
changed anchors are not relabeled as absence proof.
