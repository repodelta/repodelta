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

An `evaluation_suite.v6` document references ordinary
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
- `expected_focus_outcomes` checks the final structural disposition, exact
  overlay size, and subject-visible closure coverage and matches.
- `closure_scan_results` injects recorded scanner observations through the
  production `ClosureScanner` port; it does not bypass closure planning.
- `shadow_execution` references a canonical `llm_shadow_execution.v4`
  observation artifact;
- `expected_shadow_outcomes` declares only execution state and diagnostic
  expectations;
- `human_shadow_labels` references an independent
  `llm_shadow_human_labels.v1` artifact. Each label is validated against the
  recorded bounded request through the production selection validator and must
  partition every admitted candidate as selected, rejected, or insufficient.
  Selected labels also carry evidence and semantic roles; the label artifact
  carries `human_review` authority and a rubric version.

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
- structural focus and closure accuracy;
- human-labeled LLM-shadow selection precision/recall, semantic-role accuracy,
  complete-disposition accuracy, false-rejection rate, insufficient recall,
  deterministic-baseline retention, and unresolved-surface precision/recall;
- execution-state accuracy and rejection-diagnostic accuracy across labeled and
  operational replay cases;
- replay/live observation counts and raw token and latency totals;
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
`TransformationAssessment`, and final verification inspection. It compares
the analyzer-owned status, reasons, evidence bindings, and projected focus
outcomes; it does not recompute them. Shadow evaluation loads already-recorded
typed observations and independent human labels; it never calls an LLM
provider. Human labels are not reconstructed from model selections, and invalid
request identity or incomplete candidate coverage fails before scoring. Replay
and live artifacts use the same scoring contract but remain separately counted.
It does not implement
another retriever or convergence path, render review HTML, or turn candidate
relevance into an implementation, verification, or acceptance conclusion. A
suite with neither projection, assessment, focus, nor shadow assertions fails rather
than reporting vacuous success. Scanner-unavailable observations that do not
produce subject evidence remain `no_structural_evidence`; evaluation does not
upgrade that final state from provider input alone.

Live shadow observations remain non-authoritative measurements. Their raw token
usage and latency are reported without defining pass/fail budgets; monetary
cost requires an explicit provider/model pricing policy and representative live
samples before becoming a gate.
