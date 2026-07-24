# Deterministic candidate binding

Candidate binding is a retrieval layer, not a conclusion layer.

## Relations

```text
R / G / O / C  -> EvidenceItem
R / G          -> C
R / G          -> C -> EvidenceItem
```

All relations are many-to-many. A requirement can reach evidence without a PR
claim, and one claim can relate to several requirements.

## Candidate features

Each `CandidateBinding` contains independent `BindingReason` records:

- meaningful term overlap;
- compound identifier overlap;
- evidence-path overlap;
- changed-file context;
- bounded structural distance from a lexically matched symbol;
- requirement-to-claim alignment;
- claim-to-evidence bridging.

The displayed integer score is the capped sum of recorded reason weights. It
is deterministic and explainable; it is not a probability.

## Safety boundaries

- Candidates reference canonical statement and evidence IDs.
- Structural expansion can only use paths already bounded by the structural
  provider.
- Claims can add candidates but are never required for R-to-evidence retrieval.
- Budgets cap candidates per statement/relation kind and across the review.
- Coverage explicitly names requirements without evidence candidates, claims
  without requirement candidates, and evidence without statement candidates.
- No candidate changes implementation or verification status.
