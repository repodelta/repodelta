# Agent Change Protocol

Use this protocol for behavioral, authority, contract, data-flow, or
cross-component changes.

## 1. Define

Name the parent transformation, this change's semantic output and scope, and
the production sinks. Start from observable behavior, not expected files.

## 2. Census

Using CodeGraph and available code, test, runtime, and documentation evidence:

- trace sinks backward to producers and decisions;
- trace candidate authorities forward to production consumers;
- search laterally for writers, overrides, reconstruction, and bypasses;
- record unresolved dynamic and external surfaces.

## 3. Decompose and simulate

For each decision define:

- **authority:** who decides;
- **admission:** which inputs it may use;
- **proof:** when those inputs are sufficient;
- **consumption:** where the result becomes production truth.

Model child dependencies and the target flow. Test counterfactuals that separate
relevance from proof: names without an edge, no match under truncated coverage,
stale verification, or an unconsumed producer. Search the simulated state again
for residual authorities and bypasses.

## 4. Select the merge boundary

Choose the smallest responsibility-closed, abandonment-safe region. Define its
contracts, before/after topology, migrations, removals, proof obligations, and
coverage limits. A parent may remain open, but the current state cannot depend
on future work for correctness or architectural meaning.

Remove alternate paths or classify them as dormant, shadow, compatibility,
migration, rollback, experiment, annotation, or projection. Expand the region
if no safe boundary exists. A classification must state production effect,
activation, authority or write permission, and lifecycle; a label is
insufficient. Temporary paths need removal or review conditions, permanent
paths an ongoing invariant.

## 5. Execute unmerged

Use the branch or Draft PR for recursive discovery; commits may be checkpoints.
When a new authority, consumer, proof dependency, or boundary appears, update
the plan and expand the region instead of merging the intermediate state.

## 6. Pre-merge audit

Against the final candidate tree:

- synchronize CodeGraph and repeat the backward, forward, and lateral census;
- verify the target authority controls every observed in-scope production sink
  and all observed relevant consumers migrated;
- verify no unclassified path can decide or rewrite the output;
- exercise the proof matrix and counterfactual fixtures;
- verify path classifications and external contracts;
- make incomplete or unsupported semantics fail closed;
- separate observed in-scope paths, classified retained paths, and unresolved
  dynamic or external paths.

## 7. Merge checkpoint

Record separately:

- **responsibility closure:** this PR's transition is complete;
- **abandonment safety:** the tree can remain indefinitely without future work;
- **parent completion:** the larger transformation is complete or open.

Only the first two are merge gates.

## 8. Post-merge audit

Confirm the merge tree, observe runtime or concurrent-integration evidence, and
measure pre-merge misses. Do not use post-merge census as the normal place to
discover what the transformation should have included.

## Planning output

- Parent transformation, child dependencies, and open obligations
- Output, scope, sinks, and authority / admission / proof / consumption
- Current alternatives, unresolved surfaces, and selected region
- Before/after topology, migrations, removals, and preserved contracts
- Counterfactuals, completion evidence, and coverage limits
- Responsibility closure / abandonment safety / parent completion
