# Structural correctness campaign

This evaluation checks whether the canonical changed-file overview and each
R/G/T/CC structural focus agree with frozen human labels. It is separate from
the production review: neither a label nor a comparison result can change an
assessment, verification status, or merge decision.

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
save it as the human-label artifact. Then render the standalone comparison:

```bash
repodelta compare-structural-correctness \
  --labeling-packet build/pr-267.packet.json \
  --observation build/pr-267.packet.json.observation.json \
  --human-labels build/pr-267.labels.json \
  --output build/pr-267-structural-comparison.html
```

Packet identity, candidate completeness, subject completeness, file roles,
focus membership, relation identity, and claimed equivalent focus membership
are validated before comparison. The packet exposes the bounded candidate
universe but not RepoDelta's selected files, roles, or focus memberships.

## Campaign v1 sample

The first sample is selected by change shape rather than randomly:

| PR | Change shape | Why it is included |
| --- | --- | --- |
| #208 | Small structural correction | Tests a compact changed-anchor case. |
| #238 | Revision-aware state mapping | Tests base/head selectors and focused state semantics. |
| #245 | Documentation-only framing | Tests structurally inapplicable authored semantics. |
| #250 | New cross-component feature | Tests production, CLI, credential boundary, and verification structure. |
| #235 | Remote workspace feature | Tests cross-component runtime and infrastructure paths. |
| #262 | Presentation and investigation refactor | Tests several focus subjects over shared changed files. |
| #267 | Canonical projection migration | Tests the contract introduced immediately before this campaign. |
| #240 | Large mechanical identity migration | Tests scale, rename-like repetition, and the limit of an unclustered overview. |

The sample must contain human exclusions and unresolved memberships. If these
real PRs do not expose a retained-bridge or false-inclusion counterexample, a
small synthetic fixture complements the campaign without replacing the real
sample.

## Reading the result

File comparison distinguishes exact agreement, false inclusion, false
exclusion, role disagreement, and human-unresolved cases. Focus comparison
reports shared membership and false inclusions/exclusions independently for
each subject. `complete` or `available` remains bounded to the coverage surface
recorded in the packet; it is never interpreted as complete repository truth.

Campaign findings determine the next product change. Provenance labels are
justified when the underlying memberships are correct but insufficiently
explained. Projection fixes come first when membership is wrong. Coverage
truthfulness comes first when conclusions exceed observed bounds. Large-change
clustering comes later when correctness holds but scale prevents comprehension.
