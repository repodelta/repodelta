# Pull requests

Title the PR around its responsibility or contract transition. For new
non-trivial RepoDelta work, begin with the focused Issue it implements:

```text
Closes #<focused-issue>
```

Use exactly one GitHub closing reference: the focused Issue that supplies this
PR's requirements. A focused Issue has at most one active implementation PR,
including a Draft. Other Issues do not supply focused implementation ownership;
parent or hierarchy semantics are outside this guidance. Do not retrospectively
add a focused Issue to work authored before this rule.

Record applicable items only; do not fill absent concepts with template noise:

- parent transformation, responsibility, output, sinks, authority, and region;
- each changed derived result's provenance, scope, owner, and dependencies;
- each changed decision's orthogonal dependency and counterfactual;
- affected contracts, before/after flow, migrations, removals, and retained
  classifications;
- any material re-plan: invalidating evidence and changed target, authority,
  owner, contract, region, or merge evidence;
- contract, counterfactual, sink-level, and final-tree evidence;
- invariant enforcement and why it does not freeze uncertain semantics;
- unresolved surfaces;
- responsibility closure, contract closure, abandonment safety, and parent
  completion as separate states.

## Formal transformation contract

If a PR is intended to supply formal T/CC claims, use exact Markdown ATX
headings (`##`) for the applicable claims. The canonical headings are:

```text
## Change
## Before
## After
## Selected region
### Inputs
### Outputs
### Boundaries
## Before topology
## After topology
## Canonical authority
## Production path
## Migration
### Producers
### Consumers
### Tests
## Removed legacy paths
## Completion conditions
## Uncertainties
```

The parser preserves established compatible headings, but free prose and
approximate headings—such as `## Transformation`, `## Before and after`, or
`## Responsibility and authority`—remain context and do not create formal
T/CC claims. RepoDelta reports a source-backed warning for these recognized
near-misses rather than inferring their semantics. Use the precise headings
above when structural selection or deterministic T/CC assessment is intended.

A derived result is not automatically cross-consumer truth. If consumer-local,
state why the projection is allowed and does not alter canonical facts.
Consumers must not silently produce or re-decide upstream semantics.

Use `Before`/`After` for state transitions and `Before topology`/`After
topology` only for topology claims. Put concrete file/symbol identities in
Markdown code spans so RepoDelta can focus structure without treating state
prose as proof.

Explain why the tree remains valid if the parent stops. Unsupported or
incomplete semantics must fail closed.

Keep the PR Draft while responsibility, contracts, or a merge gate is unsettled.
Mark ready only after auditing the final tree. Link the focused Issue that owns
this PR's obligations and stop conditions.
