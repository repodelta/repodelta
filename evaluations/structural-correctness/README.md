# Structural correctness campaign

This evaluation checks whether the canonical changed-file overview and each
R/G/T/CC structural focus agree with frozen proposed or independently verified
reference labels. A verifier may be a person, an AI system, or a controlled
combination; authority comes from reproducible evidence and separation from the
RepoDelta projection under test, not from verifier identity. It is separate
from the production review: neither a label nor a comparison result can change
an assessment, verification status, or merge decision.

## Blind workflow

Generate the ordinary report, a labeler-facing packet, a separately stored
canonical observation, a canonical provenance sidecar, and a complete
unresolved label template:

```bash
repodelta review \
  --repo repodelta/repodelta \
  --pr 267 \
  --output build/pr-267.html \
  --structural-correctness-packet-output build/pr-267.packet.json
```

Freeze `pr-267.packet.json`, complete the generated
`pr-267.packet.json.labels.template.json` without opening the observation, and
save it as a proposed reference artifact. A separate verification pass may bind
the exact proposal digest only when it records its verifier, method, evidence,
and isolation from the RepoDelta output under test. Conflicting or insufficient
evidence remains unresolved. Then render the comparison:

```bash
repodelta compare-structural-correctness \
  --labeling-packet build/pr-267.packet.json \
  --observation build/pr-267.packet.json.observation.json \
  --reference-labels build/pr-267.labels.json \
  --output build/pr-267-structural-comparison.html
```

The generated `pr-267.packet.json.provenance.json` is an evaluation-only copy
of the production verification overlay. It preserves each membership's
`asserted`/`matched`/`suggested`/`context`/`unresolved` class together with the
producer and source IDs recorded by the canonical projection. The generated
`pr-267.packet.json.association.json` is a separate evaluation-only copy of
every R/G changed-anchor candidate. It records the canonical association,
reason details, matched terms, bridge IDs, convergence state, and any observed
structural membership. Its `source_channel` is a derived diagnostic
classification of the recorded association kind; it is not a new production
fact. Neither sidecar changes the production selection or assessment; the
association sidecar exists to attribute reason-level behavior without
reconstructing selector decisions from summary counts. The evaluator does not
reconstruct paths or infer selector reasons from the packet. To replay
the observed contribution of one producer, use the separate non-authoritative
sink:

```bash
repodelta compare-structural-provenance \
  --labeling-packet build/pr-267.packet.json \
  --observation build/pr-267.packet.json.observation.json \
  --provenance build/pr-267.packet.json.provenance.json \
  --reference-labels build/pr-267.labels.json \
  --disable-producer structural_path \
  --output build/pr-267-provenance-counterfactual.json
```

This counterfactual removes a membership only when every recorded producer for
that membership is disabled. A `producer:admission_class` selector can disable
one recorded admission while retaining another, so the surviving strongest
class is recomputed. It measures observed contribution; it does not predict
what a redesigned selector or closure policy would have selected.

The generated structural observation is schema v4 and records an independent
canonical membership digest for each focus. Replay requires this provenance
binding; changing producer/source details and recomputing only the sidecar's
own digest fails against the ordinary observation. Historical v2/v3
observations remain valid for ordinary structural comparison, but fail closed
when used for provenance replay.

The JSON keeps `observed` dimensions separate from `comparison` deltas:
selected nodes, claimed-direct nodes, suggestions, structural context,
unresolved memberships, and exact relations are reported independently.
Provider coverage and seed-mapping state are top-level report fields, while
baseline focus dispositions remain recorded per subject kind. Reference false-
inclusion/false-exclusion deltas are only reported for dimensions with a
resolved reference (selected, claimed-direct, and exact relations); epistemic
buckets are not silently compared as if they were semantic reference roles.

Packet identity, candidate completeness, subject completeness, file roles,
direct-versus-context focus membership, exact relation identity, and claimed
equivalent focus membership are validated before comparison. Focus truth is
recorded separately at file, canonical node, and exact relation-group levels;
agreement at one level cannot conceal an error at another. The packet exposes
the bounded candidate universe, conclusion-free symbol names and relation
endpoints, changed-file counts, and at most 32 diff hunk headers per file. It
does not expose source lines, RepoDelta's selected files, projected roles, or
focus memberships.

## Campaign v1 (superseded proposal)

The first sample is selected by change shape rather than randomly. Its
machine-readable identities, categories, purposes, and campaign constraints
are frozen in [`campaign-v1/manifest.json`](campaign-v1/manifest.json).

The sample must contain reference exclusions and unresolved memberships. If these
real PRs do not expose a retained-bridge or false-inclusion counterexample, a
small synthetic fixture complements the campaign without replacing the real
sample.

Campaign v1 records the original proposed baseline and is retained only as
historical method evidence. It is superseded by campaign v1.1 and must not be
used as the current correctness authority. Its
[reconciliation](campaign-v1/reconciliation.md) explains the authority and
coverage limits that must be resolved before treating its
[findings](campaign-v1/results/findings.md) or
[machine-checked summary](campaign-v1/results/summary.json) as verified
accuracy measurements.

Once frozen, reproducible campaign artifacts use these directories:

```text
campaign-v1/
├── manifest.json
├── packets/       # blind labeler-facing inputs
├── labels/        # frozen proposed or independently verified reference
├── observations/  # separately stored RepoDelta projections
└── results/       # machine-readable summaries and comparison reports
```

The directories are created when their first frozen artifact is admitted;
ordinary exploratory output remains under `build/` and is not committed.

## Reading the result

File comparison distinguishes exact agreement, false inclusion, false
exclusion, role disagreement, and reference-unresolved cases. Focus comparison
keeps selected membership, claimed-direct, suggestion behavior, structural
context, and exact relations as separate dimensions for each subject. A
suggestion is not promoted to direct mapping and is not silently relabeled as
context. `complete` or `available` remains bounded to the coverage surface
recorded in the packet; it is never interpreted as complete repository truth.

Campaign findings determine retrieval changes. Typed production provenance may
be added without changing selection when it prevents context from being
misrepresented as a direct mapping; that is a truth-boundary correction, not an
accuracy claim. Any candidate, path, or closure policy change must be compared
again with the current verified baseline. Coverage truthfulness comes first
when conclusions exceed observed bounds, and large-change clustering comes
later when correctness holds but scale prevents comprehension.

## Campaign v1.1

[`campaign-v1-1`](campaign-v1-1/) preserves v1 as historical proposed evidence
and regenerates the same eight-PR sample under the v3 packet and independently
verified reference contract. Its
[`verification record`](campaign-v1-1/verification.md) documents source-review
isolation and a relation-endpoint defect corrected before reference freeze. Its
[`selection invariance baseline`](campaign-v1-1/results/selection-invariance-baseline.json)
checks selected file/node universes, exact relation IDs, and dispositions
directly against the pre-provenance observation. It is reproducible from the
pinned pre-#289 commit and records each source observation's Git blob identity:

```bash
PYTHONPATH=src python \
  evaluations/structural-correctness/campaign-v1-1/\
  generate_selection_invariance_baseline.py \
  --baseline-commit 090377e
```

The
[`findings`](campaign-v1-1/results/findings.md) retain the focus over-selection
direction while separating provenance behavior from semantic reference roles
and bounding recall claims by per-focus traversal coverage.
The committed [`associations`](campaign-v1-1/associations/) artifacts are the
same evaluation-only R/G changed-anchor sidecars emitted by the command above;
they preserve candidate reasons and convergence data for reason-level
attribution. They do not become a new reference authority or alter the frozen
observations.
The repository also keeps a byte-for-byte extraction under
`campaign-v1-1/results/baseline-sources/090377e/` so a shallow CI checkout can
verify the same recorded Git blob identities when the historical commit is not
available locally.
Campaign v1.1 is the sole current structural-correctness baseline; there is no
campaign v1.2.

### Association attribution comparison

The association sidecar can be compared with the frozen v1.1 references without
rerunning production selection:

```bash
repodelta compare-structural-association \
  --labeling-packet build/pr-267.packet.json \
  --observation build/pr-267.packet.json.observation.json \
  --association-attribution build/pr-267.packet.json.association.json \
  --reference-labels build/pr-267.reference.json \
  --output build/pr-267-association-comparison.json
```

The result reports selected-membership, claimed-direct, structural-context, and
exact-relation false inclusions/exclusions by subject kind and recorded
association reason. It also reports suggestions and unresolved memberships as
observed-only dimensions. Selected nodes, structural context, and relation
groups are attributed through root-linked lineage already present in the
canonical overlay; claimed-direct false inclusions use the observed member's
own admission relation, while claimed-direct false exclusions use candidate
node identity. `causal_replay` is false. The exclusive reason breakdown keeps
`multiple` for members reachable from more than one recorded root and
`unattributed` for members without a recorded lineage, rather than assigning
a guessed reason; these fallback rows make the reason totals reconcile with
the overall deltas.
The separate `comparison_involved` view remains non-exclusive and may count a
member for every recorded reason that reaches it.

### Identifier specificity probe and policy shadow

`exact_identifier` is a production association reason, not proof that a
lexical overlap names one canonical symbol. The evaluation-only identifier
probe keeps that distinction visible. A live review writes an additional
`*.identifier-specificity.json` sidecar; for a frozen packet and association
sidecar it can be regenerated with:

```bash
repodelta observe-structural-identifier \
  --labeling-packet build/pr-267.packet.json \
  --association-attribution build/pr-267.packet.json.association.json \
  --output build/pr-267.identifier-specificity.json
```

Each matched term records its normalized authored-key form (a complete
identifier or suffix alias inferred by the same deterministic tokenizer),
observed origin (`qualified_name`, `path`, `diff_text`,
`signature_unattributed`, or `unobserved`), canonical changed-symbol
resolution, and per-focus exact-association fanout. Resolution is measured
against all changed symbols in the packet, not a focus-eligible candidate
universe; it is therefore a repository-wide changed-symbol token check rather
than a complete canonical identity resolver. Historical v1.1 packets are necessarily
`partial`: they never contained raw diff text, so the adapter marks that
origin as `unobserved` rather than reconstructing it. In a live brief, diff
origin is recorded only when the target's canonical change-relation identity
resolves to an evidence item carrying the raw preview; otherwise the term is
`signature_unattributed`/`unobserved` and completeness remains `partial`.
Descriptive evidence summaries are not treated as raw diff text.

The sidecar can then compare bounded direct-admission policies without changing
production selection or replaying closure:

```bash
repodelta compare-structural-identifier \
  --labeling-packet build/pr-267.packet.json \
  --observation build/pr-267.packet.json.observation.json \
  --association-attribution build/pr-267.packet.json.association.json \
  --identifier-specificity build/pr-267.identifier-specificity.json \
  --reference-labels build/pr-267.reference.json \
  --output build/pr-267-identifier-policy-shadow.json
```

The comparison includes the observed `current` policy plus `no_suffix`,
`canonical_low_fanout`, `qualified_token_present`, `full_token_low_fanout`, and
`canonical_token_unique` shadows. These isolate qualified-name token support,
exact-association fanout, and uniqueness: none is a full qualified-name
equality check. The comparison reports only direct-node
false inclusions/exclusions against the frozen semantic reference. It does
not claim to predict selected files, structural context, exact relations, or
semantic resolution; an LLM/embedding policy remains unexplored. No policy in
this experiment changes the formal report or assessment authority.

The frozen v1.1 run and its interpretation are recorded in the
[`identifier-specificity findings`](campaign-v1-1/results/identifier-specificity/findings.md).

### R/G semantic candidate universe

The identifier probe showed that tightening lexical admission alone trades
false inclusions for false exclusions. Before changing that production boundary,
an evaluation run can freeze a broader but still bounded R/G candidate universe:
every profile-eligible changed-anchor fact, before current association filters
it. A live structural-correctness output additionally writes:

```text
<packet>.rg-candidates.json
<packet>.rg-retrieval.json
<packet>.rg-candidates.labels.template.json
```

The candidate universe preserves the source fact identity, profile, revision
and change provenance, source links, and any canonical review-symbol or graph
node mapping. A `node_unresolved` or `not_node_backed` candidate remains in the
packet; it is not silently discarded because it cannot be drawn as a graph
node. The universe contains no association result, structural membership, or
model answer.

The retrieval sidecar separately records the current production association
for every frozen candidate (`not_retrieved`, `selected`, or `deferred`) and its
recorded reasons. It is an observation of the existing selector, not a second
selector. The label template separately asks an isolated verifier to classify
each candidate as `implements`, `constrains`, `removes`,
`directly_verifies`, `contextual_support`, `unrelated`, or `insufficient`, and
to state whether the semantic-direct relation has direct-capable proof,
suggestion-only evidence, or insufficient evidence. `insufficient` is a
reviewed conclusion: it means the bounded source evidence was examined but
does not support a responsible decision. It is not the template's “not yet
reviewed” state.

The generated template marks every row `pending`; it is deliberately not
comparable. A labeler must explicitly mark every row `reviewed`, then an
independent verifier records the isolation and evidence that bind the exact
proposal digest:

```bash
repodelta verify-rg-semantic-reference \
  --candidate-universe evaluations/structural-correctness/campaign-v1-1/\
rg-candidate-universes/pr-267.json \
  --reference-labels build/pr-267.rg-semantic-reference.proposed.json \
  --verified-by independent-verifier \
  --verification-method "blind source review" \
  --verification-evidence issue#304 \
  --system-under-test-isolated \
  --output build/pr-267.rg-semantic-reference.verified.json
```

Only that independently completed and verified reference may be compared with
the observed retrieval; proposed references fail closed and cannot emit
semantic FI/FE metrics:

```bash
repodelta compare-rg-semantic-candidates \
  --candidate-universe build/pr-267.packet.json.rg-candidates.json \
  --retrieval-observation build/pr-267.packet.json.rg-retrieval.json \
  --reference-labels build/pr-267.rg-semantic-reference.verified.json \
  --output build/pr-267.rg-semantic-comparison.json
```

The comparison keeps two questions distinct: whether current retrieval surfaced
a semantic-direct candidate at all, and whether current `provided_association`/
`exact_identifier` attempts agree with the smaller direct-capable set. It
reports any independently reviewed direct expectation outside the bounded
candidate universe, and direct candidates that lack a canonical graph node.
Those are coverage limits, not automatic false exclusions.

Structural paths, relation endpoints, ownership/placement ancestry, and
retained topology remain structural context rather than direct semantic
candidates. Guardrail closure scans and current-head verification observations
also remain a separate proof surface. Future LLM work, including Issue #225,
may consume this frozen candidate substrate for ranking or suggestion, but may
not define it or promote a candidate to formal direct admission.

The v1.1 extraction is reproducible only by re-running its source PRs because
the older packet intentionally omitted anchors that were never associated:

```bash
GITHUB_TOKEN="$(gh auth token)" PYTHONPATH=src python \
  evaluations/structural-correctness/campaign-v1-1/\
  run_rg_candidate_universe.py
```

It refuses to write the new artifacts if an ordinary frozen v1.1 packet
changes. Generate a label template from a frozen candidate universe without
opening its retrieval sidecar:

```bash
repodelta prepare-rg-semantic-reference \
  --candidate-universe evaluations/structural-correctness/campaign-v1-1/\
rg-candidate-universes/pr-267.json \
  --proposed-by independent-labeler \
  --output build/pr-267.rg-semantic-reference.json
```

The generated template remains pending until a labeler reviews it without
reading the retrieval sidecar. It is not presented as a semantic-correctness
result, and neither is a complete-but-proposed reference. `direct_capable` is
only the reference reviewer's judgment that a future direct mapping might be
provable from the cited evidence; it never creates a production `matched` or
direct mapping. A production change would need its own machine-verifiable
proof trace and authority contract.

Before the first R/G semantic-labeling batch, freeze and follow the
[`labeling and verification protocol`](campaign-v1-1/rg-semantic-labeling-protocol.md).
It governs the independent proposer/verifier roles, allowed inputs, evidence
review, reproducible model-assisted runs, high-risk adjudication, and the stop
conditions that the lifecycle schema alone cannot prove.
