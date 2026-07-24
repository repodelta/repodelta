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
- Candidate relevance is never an implementation, verification, or acceptance
  conclusion.

## Report projection

`Review checks` uses R statements as its primary axis when explicit acceptance
criteria exist and PR-authored C statements as a fallback axis otherwise.
Related claims and canonical evidence appear inside the corresponding review
card. Each evidence row exposes its retrieval score, binding reasons, and
source links. The renderer limits visible evidence candidates per statement;
this presentation limit does not alter the canonical binding set.

`Needs attention` aggregates acceptance-basis, claim, evidence, source, CI, and
scope coverage across the review. Its wording distinguishes
communication/retrieval gaps from implementation or verification conclusions.
