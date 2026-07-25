# Deterministic review fact routing

Fact routing is a typed retrieval layer, not a conclusion layer.

```text
canonical statements + EvidenceCatalog
  -> eligibility by fact profile and projection slot
  -> deterministic association inside each slot
  -> ProjectionCandidateSet
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
- guardrail boundary facts.

PR claims, changed symbols, paths, and CI observations never compete in one
numeric score or global candidate budget.

## Associations

Ordered deterministic association kinds are:

1. provider-supplied explicit association;
2. explicit R/G reference;
3. exact distinctive identifier;
4. distinctive multi-token phrase;
5. claim bridge;
6. structural bridge;
7. current-head observation;
8. bounded guardrail scan.

A generic one-token overlap is not enough for default selection. Numbers are
not used to compare facts from different slots.

## Structural routing

Only a selected exact changed symbol can seed structural context. Runtime and
test symbols must occur on a bounded path rooted at that anchor. Without
Codegraph, the same projection uses the canonical changed hunk or changed-file
fallback and records typed structural diagnostics.

## Coverage

Typed diagnostics distinguish source absence, non-applicability, no eligible
fact, no deterministic association, ambiguity, provider unavailability,
partial coverage, stale sources, per-slot truncation, and unsupported change
types.

`EvidenceCatalog` remains the only evidence store. Candidate relations and
projection slices contain canonical IDs only.
