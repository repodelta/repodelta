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
canonical observation, and a complete unresolved label template:

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

Packet identity, candidate completeness, subject completeness, file roles,
direct-versus-context focus membership, exact relation identity, and claimed
equivalent focus membership are validated before comparison. Focus truth is
recorded separately at file, canonical node, and exact relation-group levels;
agreement at one level cannot conceal an error at another. The packet exposes
the bounded candidate universe, conclusion-free symbol names and relation
endpoints, changed-file counts, and at most 32 diff hunk headers per file. It
does not expose source lines, RepoDelta's selected files, projected roles, or
focus memberships.

## Campaign v1 sample

The first sample is selected by change shape rather than randomly. Its
machine-readable identities, categories, purposes, and campaign constraints
are frozen in [`campaign-v1/manifest.json`](campaign-v1/manifest.json).

The sample must contain reference exclusions and unresolved memberships. If these
real PRs do not expose a retained-bridge or false-inclusion counterexample, a
small synthetic fixture complements the campaign without replacing the real
sample.

Campaign v1 records a proposed baseline. Its
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
reports those outcomes independently for file membership, canonical node role,
and exact relations for each subject. `complete` or `available` remains bounded
to the coverage surface recorded in the packet; it is never interpreted as
complete repository truth.

Campaign findings determine the next product change. Provenance labels are
justified when the underlying memberships are correct but insufficiently
explained. Projection fixes come first when membership is wrong. Coverage
truthfulness comes first when conclusions exceed observed bounds. Large-change
clustering comes later when correctness holds but scale prevents comprehension.
