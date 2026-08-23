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
producer and source IDs recorded by the canonical projection. The evaluator
does not reconstruct paths or infer selector reasons from the packet. To replay
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

The JSON keeps `observed` dimensions separate from `comparison` deltas:
selected nodes, claimed-direct nodes, suggestions, structural context,
unresolved memberships, exact relations, and the packet's coverage state are
reported independently. Reference false-inclusion/false-exclusion deltas are
only reported for dimensions with a resolved reference (selected, claimed
direct, and exact relations); epistemic buckets are not silently compared as if
they were semantic reference roles.

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
The repository also keeps a byte-for-byte extraction under
`campaign-v1-1/results/baseline-sources/090377e/` so a shallow CI checkout can
verify the same recorded Git blob identities when the historical commit is not
available locally.
Campaign v1.1 is the sole current structural-correctness baseline; there is no
campaign v1.2.
