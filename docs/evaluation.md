# Offline evaluation

PrismCode evaluates typed fact routing, structural evidence behavior, and the
production transformation assessment against explicit golden IDs before those
authorities change.

```bash
prismcode evaluate \
  --suite fixtures/evaluation-suite.json \
  --json-output build/evaluation.json \
  --markdown-output build/evaluation.md
```

The command is deterministic and network-free. It exits `0` when every suite
threshold passes, `1` when metrics miss a threshold, and `2` for invalid input
or an I/O error.

## Suite contract

An `evaluation_suite.v3` document references ordinary
`analysis_fixture.v3` inputs. A case can additionally provide a serialized
`StructuralGraphResult`, allowing exact-symbol and bounded-path behavior to be
replayed without installing Codegraph.

Golden expectations use stable statement and evidence IDs:

- `expected_selections` declares the canonical target selected for one R/G and
  one projection slot;
- `expected_no_selections` declares a typed slot that should remain empty;
- `expected_evidence` checks canonical code/test/document/CI/runtime/mixed
  classification and fact profile;
- `expected_statements` checks a statement's stable ID, role, purpose, and
  authority.
- `expected_assessments` checks a transformation claim or predicate's status,
  typed reasons, and exact supporting or contradicting evidence IDs.

No path, filename, or display-text heuristic is used to decide correctness.

## Metrics

The result records:

- precision@k;
- recall@k;
- mean reciprocal rank;
- positive-query no-candidate rate;
- negative-query no-match accuracy;
- negative-query false-positive rate;
- evidence classification accuracy;
- statement semantic accuracy;
- transformation assessment accuracy;
- missing and unexpected target IDs for every query;
- per-focus/per-slot budget and threshold diagnostics.

Positive retrieval metrics exclude `expected_no_selections` cases. Negative
queries are scored separately so adding easy no-match examples cannot inflate
precision, recall, or mean reciprocal rank. Every query, classification, or
statement-semantic mismatch records its case, identity, expected values, and
observed values before aggregate threshold diagnostics are applied.

JSON output is sorted and contains no timestamp, so repeated runs over the same
suite are byte-for-byte stable. The Markdown file is a concise human-readable
projection of the same result.

## Safety boundary

Evaluation observes the production `ProjectionCandidateSet`,
`CandidateConvergence`, `ReviewProjection`, `EvidenceCatalog`, and
`TransformationAssessment`. It compares the analyzer-owned status, reasons,
and evidence bindings; it does not recompute them. It does not implement
another retriever or convergence path, render review HTML, or turn candidate
relevance into an implementation, verification, or acceptance conclusion. A
suite with neither projection nor assessment assertions fails rather than
reporting vacuous success.

Future evidence-map and LLM work should add golden cases or thresholds before
changing production behavior.
