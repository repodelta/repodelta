# Review fact routing and projection design

Status: accepted design audit implemented by Issue #20. This document records
the reasoning and target data flow before any LLM reranker is considered.

## Decision

PrismCode should not rank every statement against every evidence item and then
construct a review projection from the surviving global candidate pool.

The target flow is:

```text
source statements + canonical repository facts
  -> typed eligibility and canonical replacement
  -> changed-anchor neighborhoods
  -> requirement-specific slot candidates
  -> deterministic per-slot selection
  -> ReviewProjection
  -> renderer
```

Scoring, when needed, is local to candidates with the same semantic role. A PR
claim is not numerically comparable with a changed symbol, a CI observation, or
a structural path.

This remains a retrieval and organization layer. It does not produce
implemented, verified, supported, partial, contradicted, or satisfied
conclusions.

## Current-state audit

### Source and statement providers

| Producer | Canonical output | Current role | Audit |
|---|---|---|---|
| GitHub PR REST | PR title/body, head/base SHA, changed files and patches | Source facts | Keep |
| GitHub GraphQL | Development-linked Issues | Contract authority | Keep; do not infer links from PR prose |
| GitHub checks/status APIs | Current-head check runs and commit statuses | Execution observations | Keep |
| Markdown semantic parser | O/S/R/G/V contract and C/B/VC/I authored statements with authority and purpose | Review contract and authored claims | Keep; add an explicit requirement profile later |
| Unified-diff parser | Added/removed line ranges and bounded snippets | Changed facts | Keep |
| `CodegraphProvider` | Index status, hunk/symbol overlaps, symbols, directed paths and diagnostics | Structural facts | Keep behind `StructuralGraphProvider` |
| Supplied fixture/provider evidence | Stable externally supplied evidence IDs | Test/provider extension | Keep, but require an explicit evidence role |

### Repository fact types currently emitted

`EvidenceCatalog` currently normalizes:

| Kind | Classification | Changed | Meaning |
|---|---|---:|---|
| `symbol` | code/test/document by path | yes/no | Exact Codegraph symbol |
| `change_relation` | code/test/document by path | yes | Uncovered portion of a canonical typed base-to-head diff relation |
| `changed_file` | code/test/document by path | yes | Fallback when patch/hunk is unavailable |
| `structural_path` | runtime/test/mixed | no | Bounded directed Codegraph path |
| `check_run` | ci | no | GitHub current-head check observation |
| `commit_status` | ci | no | GitHub current-head status observation |
| `workflow_run` | ci | no | Workflow observation when supplied |
| `manual` | runtime | no | Supplied manual execution observation |
| arbitrary supplied kind | supplied classification | provider-defined | Stable supplied evidence |

The symbol/hunk/file replacement rule is sound:

```text
exact changed symbol > changed hunk > changed-file fallback
```

It is a presentation replacement over one change, not three competing truths.
The retained sources and metadata continue to provide provenance.

### Structural facts currently emitted

`StructuralGraphResult` contains:

- index state and coverage;
- exact hunk/symbol overlaps;
- directed `calls`, `imports`, `instantiates`, `references`, and `extends`
  paths;
- runtime/test/mixed path classification;
- missing, stale, partial, unmapped, deletion-only, and traversal-budget
  diagnostics.

The provider expands all exact changed-symbol seeds before a
requirement-specific need is known. A round-robin scheduler combines per-seed
limits with one review-level node/path ceiling, so an earlier high-fanout seed
cannot starve later changed symbols and the total provider fact set remains
bounded. Every seed has an explicit complete/truncated coverage record that
distinguishes its own limit from the shared review boundary. Provider coverage
remains review-level; projection routing selects from the resulting canonical
facts without attributing collection limits to an R/G focus.

### Current responsibility problems

`build_candidate_bindings` currently performs five separate jobs:

1. all-statement-to-all-evidence lexical retrieval;
2. requirement-to-claim lexical retrieval;
3. structural-neighbor propagation;
4. claim-to-evidence bridging;
5. per-statement and global truncation.

This causes the following defects:

- one generic token is enough to create a binding because the minimum score is
  equal to one term-overlap weight;
- claim, changed-anchor, structural-path, test, CI, objective, and scope
  candidates consume one global pool;
- global sorting by source ID can exhaust the budget before later R statements
  are considered;
- structural context exists only when a lexical symbol anchor was first found;
- coverage cannot distinguish absent input, ineligible input, no association,
  provider failure, partial coverage, ambiguity, and budget truncation;
- a capped additive score is presented before candidate types have been routed
  into comparable groups.

`build_review_projection` is therefore not yet the owner of projection
selection. It can only trim a candidate set already filtered by the earlier
global process.

The renderer correctly resolves canonical IDs, but it also invents generic
empty-state wording instead of rendering typed selection diagnostics. This
makes an upstream retrieval failure look like an authentic absence of PR or
repository facts.

The current evaluation suite validates selected final IDs, basic
classification, and statement parsing. It does not independently measure fact
extraction, slot eligibility, association quality, provider coverage
diagnostics, or starvation under budget pressure.

## Semantic inputs

Statements retain distinct authority and purpose:

| Statement | Authority | Projection use |
|---|---|---|
| R acceptance obligation | Issue, or provisional PR fallback | Primary review focus |
| G guardrail | Issue | Primary boundary focus |
| Goal/objective | Issue or PR | Retrieval context only |
| Scope | Issue or PR | Eligibility/context hint only |
| Baseline claim | PR | Authored comparison claim |
| Implementation claim | PR | Candidate answer to an R/G |
| Verification claim | PR | Authored claim, never an execution fact |
| Boundary claim | PR | Authored claim, never a redefinition of Issue G |
| Intent/title | PR | Last-resort context only |

Goal and Scope can help route a fact, but do not become acceptance obligations.
A PR claim can bridge an R to repository facts, but does not prove that the
claim and code agree.

## Projection slot contract

Each R/G has one machine-readable slice. A slot answers one question and
accepts only eligible fact or relation types.

| Slot | Question | Eligible inputs | Never accepts |
|---|---|---|---|
| `claim` | What does the PR author say about this R/G? | PR C/B/V/boundary statements linked to the focus | Issue Goal/Scope as if they were PR claims; repository facts |
| `changed_anchor` | What relevant repository location actually changed? | exact changed symbol, change relation, changed-file fallback | unchanged symbols, CI, free structural neighbors |
| `runtime_context` | How can a selected changed anchor enter or affect runtime code? | unchanged code symbol on an eligible selected path | lexically similar but disconnected symbols |
| `test_context` | What tests structurally exercise or reach the selected anchor/context? | changed test anchors and unchanged test symbols on eligible paths | arbitrary test files sharing generic terms |
| `verification` | What ran for the current head? | current-head CI/status/manual observations | PR verification prose |
| `structural_path` | How are selected repository facts connected? | bounded paths whose seed is a selected changed anchor and whose nodes are selected context | paths unrelated to selected anchors |
| `boundary_fact` | What changed area is relevant to a guardrail scan? | typed changed anchors and explicit scan coverage | claims of absence without a stated scan scope |
| `diagnostic` | Why is a slot empty or incomplete? | typed extraction, eligibility, association, provider, coverage, and budget states | renderer-generated guesses |

Changed test code is a changed anchor and may also appear in the test-oriented
presentation group. Its canonical identity is not duplicated.

## Fact eligibility matrix

Legend: `Y` eligible, `C` eligible only with stated conditions, `N` ineligible.

| Fact type | changed anchor | runtime | test | verification | path | boundary |
|---|---:|---:|---:|---:|---:|---:|
| changed production symbol | Y | N | N | N | seed | C |
| changed test symbol | Y | N | Y | N | seed | C |
| unchanged production symbol | N | C: selected path | N | N | node | C |
| unchanged test symbol | N | N | C: selected path | N | node | C |
| changed code hunk | Y | N | C: test path | N | no graph | C |
| changed document hunk/file | C: document profile | N | N | N | N | C |
| changed workflow/config hunk/file | C: workflow/config profile | C: known consumer relation | C | N | C | C |
| changed generated/vendor/lock file | C: explicit profile only | N | N | N | N | C |
| structural path | N | context carrier | context carrier | N | Y | C |
| current-head check/status | N | N | N | Y | N | N |
| manual observation | N | N | N | Y | N | N |
| PR verification statement | N | N | N | authored claim only | N | N |

Before R/G association, always reject:

- CI/status observations for another head SHA;
- structural paths not rooted at an exact selected changed anchor;
- unchanged symbols not on an eligible path;
- document facts from runtime/test slots;
- generated/vendor/lockfile facts from general code slots;
- structurally superseded hunk/file representations;
- duplicate provider descriptions of the same canonical identity;
- facts from incomplete GitHub file collection without a coverage diagnostic.

Do not globally discard document, workflow, configuration, schema, migration,
dependency, generated, or deletion-only changes. Route them through a typed
change profile and expose explicit unsupported/partial coverage where the
current providers cannot relate them.

Phrase association uses one review-local vocabulary over unique semantic
meanings. Two shared terms remain necessary, and at least one must occur in no
more than half of the applicable focus corpus. Duplicate requirement text is
one meaning rather than artificial frequency. Claim bridges also require an
authorized term from the eligible-anchor corpus. Exact identifiers, explicit
references, and provider associations bypass phrase distinctiveness because
their authority is already stronger.

## Requirement profiles

Profiles choose a slot template; they do not produce a conclusion.

| Profile | Primary facts |
|---|---|
| behavior/runtime | changed production anchor, runtime path, test context, current-head verification |
| API/contract | declaration/signature anchor, consumers, compatibility tests |
| UI/rendering | component/render anchor, entry path, UI tests or artifacts |
| test/verification | changed test/workflow anchor and current-head execution |
| workflow/configuration | workflow/config hunk, referenced command or known consumer, current-head execution |
| documentation | changed document hunk, directory/module ownership, referenced identifiers |
| schema/migration | schema/migration anchor, writers/readers, compatibility or migration tests |
| guardrail/boundary | changed-area scan and explicit scan coverage |
| generic | claim plus changed-anchor candidates; no invented structural context |

Initial profiles should use deterministic cues such as statement purpose,
explicit identifiers, file kinds, and known headings. Ambiguous cases use the
generic profile and carry an ambiguity diagnostic.

## Changed-anchor and Codegraph policy

### Eligible traversal seeds

Codegraph expansion may only contribute to a slice from:

1. an exact changed symbol that represents a changed hunk;
2. an indexed file/module symbol selected for a module-level or import hunk.

A changed hunk or changed-file fallback remains a valid anchor but cannot
invent graph paths. Deletion-only hunks require a base-revision index; without
one they remain hunk anchors with an explicit structural limitation.

### Relation purposes

| Relation/direction | Intended use |
|---|---|
| outgoing `calls` / `instantiates` | runtime path from changed code to behavior |
| incoming `calls` | callers and tests that exercise changed code |
| outgoing/incoming `imports` | module-level integration and ownership |
| `extends` | inheritance/implementation context |
| `references` | named consumers when a stronger relation is unavailable |

Container/ownership edges remain excluded from runtime paths unless a future
provider gives them a distinct non-execution role.

### Path rules

- Keep the provider safety cap, but select per seed and per path purpose.
- Prefer a direct path over a longer path.
- Prefer a path with a specific runtime/test purpose over an unclassified path.
- Do not compare path relevance numerically with claim or anchor relevance.
- Keep at most one canonical path for the same seed, terminal, relation
  sequence, and direction sequence.
- Runtime traversal and test discovery have separate budgets.
- Report provider truncation, partial index coverage, stale index, unindexed
  files, unmatched hunks, and base-index requirements in the projection.

The provider may continue returning a bounded superset. A later optimization
may add query-by-seed/purpose to the provider protocol, but projection
correctness must not depend on that optimization.

## Association model

Association happens after eligibility routing. It emits a typed candidate
relation with reasons, not a cross-type global score.

### Relation strengths

Use an ordered rule set:

1. `explicit_reference`: R/AC identifier explicitly referenced by a PR claim;
2. `exact_identifier`: distinctive code/config/workflow identifier occurs in
   the focus or an aligned claim and the candidate;
3. `distinctive_phrase`: normalized multi-token phrase overlap;
4. `claim_bridge`: R/G to PR claim, then claim to an eligible changed anchor;
5. `structural_bridge`: selected changed anchor to eligible runtime/test node;
6. `path_or_module_context`: matching path/module ownership after a stronger
   anchor exists;
7. `generic_lexical`: optional low-confidence recall candidate, never sufficient
   alone for structural expansion or default selection.

These strengths are ordinal. A number may break ties within one relation kind,
but no universal additive score is required.

### Projection containers

The versioned, reference-only selected view is:

```text
ReviewProjection
  review_graph
    path_relation_ids[]
    nodes[evidence_id, path_relation_ids[]]
    edges[id, source_evidence_id, relation, direction,
          target_evidence_id, path_relation_ids[]]
  slices[]
    focus_statement_id
    claim_relation_ids[]
    standalone_changed_fact_relation_ids[]
    standalone_runtime_relation_ids[]
    standalone_test_relation_ids[]
    verification_relation_ids[]
    structural_overlay
      path_relation_ids[]
      nodes[evidence_id, role, relation_ids[], path_relation_ids[]]
      edge_ids[]
    diagnostics[]
```

The upstream `ProjectionCandidateSet` still enumerates typed relations.
Graph and overlay entries reference canonical evidence/relation IDs and copy no
statement or evidence content. Shared selected paths and cross-focus overlap
collapse to one review-level node/edge identity without discarding global or
focus-relative path provenance.

Candidate relations contain:

- slot;
- association kind;
- ordered reasons;
- optional bridge IDs;
- stable source ordinal;
- no copied statement or evidence content.

`CandidateConvergence` separately references selected and deferred relation
IDs plus typed ambiguity and budget diagnostics. Each convergence group also
owns one reference-only `StructuralSupportSet` containing exactly the selected
shortest terminal support. Deferred relation IDs are the sole provenance for
unselected paths. Projection does not repeat path/terminal selection. Selection
truth is not copied onto each routed relation.

This replaces the current use of one untyped `statement_evidence` relation for
every evidence role. It does not create a second evidence store.

## Selection and budgets

Budgets have three independent levels:

1. retrieval budget: how many eligible facts may be inspected;
2. selection budget: how many relations enter a `ReviewSlice`;
3. presentation budget: how many selected facts are expanded by default.

Apply budgets in this order:

```text
per review
  -> guarantee one pass over every R/G
  -> per R/G
  -> per slot
  -> per association strength
```

No earlier statement may consume the minimum allocation of a later statement.
Objectives, Scope, and PR-only context cannot consume R/G selection budgets.
When a budget truncates candidates, record the affected focus and slot.

Default claim selection can remain compact, while set and subgraph slots use
explicit identity safety limits:

- two PR claims;
- up to 20 direct, 10 claim-bridged, and 30 total changed-anchor identities;
- up to 20 runtime-context identities;
- up to 20 test-context identities;
- one current-head verification observation per distinct check identity;
- up to five canonical paths sponsored by each selected anchor and 30 paths
  total;
- one canonical typed scan plan per guardrail plus a plan-aware
  missing-execution diagnostic until a bounded scan provider returns facts.

Those are convergence safety limits, not retrieval or ordinary display limits.

## Coverage and diagnostics

Every empty or incomplete slot carries one of:

| State | Meaning |
|---|---|
| `source_absent` | The source did not provide the expected input |
| `not_applicable` | The slot does not apply to this requirement profile |
| `no_eligible_fact` | Facts exist, but none satisfy the slot contract |
| `no_association` | Eligible facts exist, but no deterministic relation was found |
| `ambiguous` | Multiple candidates cannot be deterministically separated |
| `provider_unavailable` | Required provider could not run |
| `partial_coverage` | Provider or GitHub collection covered only part of the review |
| `stale_source` | Fact/index does not correspond to the current head |
| `budget_truncated` | A named collection or selection safety budget stopped complete coverage |
| `unsupported_change_type` | A changed fact type has no current relation strategy |

Diagnostics include focus ID, slot, provider, affected paths/IDs when
available, and coverage counts. The renderer displays these diagnostics and
does not infer its own reason from an empty tuple.

Absence wording must state the observed scope. For example:

```text
No dependency-manifest change observed among 13/13 collected changed files.
```

It must not claim:

```text
No dependency change.
```

## Provenance and freshness

Canonical facts and selected relations must make these available:

- provider and source authority;
- repository and PR;
- head/base revision where applicable;
- source URL and file/span;
- collection completeness;
- index/provider state;
- current-head match;
- stable identity and schema version.

PR verification prose and current-head execution observations remain separate
objects even when they describe the same command.

## Rendering contract

The renderer receives a complete `ReviewProjection` plus typed diagnostics.
It may resolve IDs, group selected slots, collapse presentation, and create
links. It must not:

- perform lexical matching;
- reclassify a fact;
- choose structural paths;
- infer why a slot is empty;
- convert a candidate relation into a conclusion;
- reconstruct a parallel evidence grouping.

A populated slice renders:

```text
Issue contract -> PR says -> Repository facts
```

The Issue column identifies the focus and source authority. The PR column
contains authored claim candidates. Repository facts are grouped by changed
anchor, runtime, test, verification, path, and boundary roles.

A missing side is shown only when the other side contains review information
or a typed diagnostic is actionable. Completely empty slices are aggregated by
their real typed diagnostic, but are retained in the machine contract.

## Evaluation plan

Measure stages independently:

1. statement extraction and authority accuracy;
2. canonical fact extraction and replacement accuracy;
3. fact classification/profile accuracy;
4. slot eligibility precision/recall;
5. R/G-to-claim relation precision/recall;
6. R/G-to-changed-anchor precision/recall;
7. runtime/test path usefulness and shortest-path correctness;
8. verification freshness accuracy;
9. coverage diagnostic accuracy;
10. projection selection accuracy;
11. reviewer acceptance, latency, and cost later.

Required golden cases:

- Issue and PR use different but equivalent wording;
- PR claim contradicts or overstates the code change;
- changed adapter Y connects to unchanged runtime X and downstream Z;
- production code is unchanged but tests change;
- document-only, workflow, configuration, dependency, schema, generated, and
  deletion-only changes;
- Codegraph available, missing, partial, stale, truncated, and base-index
  unavailable;
- missing GitHub patch and changed-file collection limit;
- many early G/O/S/C candidates cannot starve later R statements;
- one fact relates to multiple R statements;
- multiple R statements share one claim;
- generic token overlap produces no default selected relation;
- PR has no linked Issue but contains explicit provisional acceptance criteria;
- Issue has R statements and the PR description is empty or weak.

Projection accuracy must not default to success when the fixture declares no
expected projection assertions. Each release gate needs meaningful positive
and negative cases for every new slot/profile.

## Migration plan

### Phase A: contracts and audit fixtures

- Add fact role/change profile and typed coverage diagnostics.
- Add `ProjectionCandidateSet` and slot-specific candidate relations.
- Preserve `EvidenceCatalog` as the only evidence store.
- Add starvation, partial-provider, document/config, and Y-to-X-to-Z fixtures.
- Do not change the HTML yet.

### Phase B: typed routing

- Split current `build_candidate_bindings` into:
  - eligibility routing;
  - claim association;
  - changed-anchor association;
  - structural context routing;
  - verification routing.
- Select per R/G and per slot.
- Remove `CandidateBindingSet` from the production brief instead of operating
  a compatibility or dual-write path.

### Phase C: projection and renderer

- Make `ReviewProjection` consume only the typed candidate set.
- Render typed diagnostics and partial structural coverage.
- Remove renderer-owned empty-state inference and obsolete generic candidate
  cards.
- Remove the old global score and global candidate budget after fixture/schema
  migration.

### Phase D: evaluation and removal

- Gate on stage-specific metrics and real PR fixtures.
- Delete lexical structural propagation, claim-bridge duplication, global
  source-ID truncation, and documentation that describes the old score as the
  projection selector.
- Keep lexical tokens only as one low-strength association feature where
  golden evaluation shows value.

### Phase E: optional LLM shadow reranking

Only after deterministic routing is stable:

- give the model candidates from one focus and one slot;
- allow output to reference candidate relation IDs only;
- record deterministic and model selections;
- never let the model invent facts or bypass eligibility;
- keep it out of conclusions until measured precision, rejection safety,
  latency, and cost meet explicit thresholds.

## PR 19 disposition

Draft PR #19 established useful reference-only `ReviewProjection` and
`ReviewSlice` concepts, but its selection path depended on the prematurely
scored global candidate pool. Issue #20 replaces that path from `main` rather
than merging it and adding a compatibility layer.

Retain and adapt:

- reference-only projection contracts;
- one slice per R/G;
- compact slot budgets;
- canonical ID resolution;
- graph/no-graph projection shape;
- three-part renderer vocabulary.

Replace before merge or split into a clean successor:

- global all-statement/all-evidence scoring as projection input;
- source-ID-ordered global truncation;
- lexical-anchor-owned structural expansion;
- generic empty-state rendering;
- evaluation fixtures that do not expose starvation and provider coverage.
