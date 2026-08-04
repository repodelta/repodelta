# Agent Change Protocol

Use this protocol for behavioral, responsibility, contract, data-flow, or
cross-component changes.

## 1. Fix the target

Define:

- semantic output and production sinks;
- responsibility currently producing that output;
- intended after-state;
- observed scope and explicit out-of-scope surfaces.

Do not begin from expected files.

## 2. Find the affected pipeline

Trace:

- backward from production sinks to producers and decisions;
- forward from the responsibility to observed actual consumers;
- laterally for competing producers, writers, fallbacks, and reconstruction;
- across boundaries that parse, normalize, map identities, aggregate, project,
  serialize, default, reorder, or reduce coverage.

Record unresolved dynamic and external surfaces instead of claiming coverage.

## 3. Define changed contracts

For each affected boundary, state:

- semantic entity being transferred;
- canonical semantic contract and relevant equivalence rules;
- properties that must be preserved;
- information that may be lost;
- behavior for incomplete, conflicting, or unsupported input.

Different representations may implement one contract. Analyze only properties
relevant to this change; shared names, tokens, or proximity do not prove
equivalence.

## 4. Select the region

Start with the responsibility being replaced. If an external contract remains
valid, keep that neighbor outside the region. If the change invalidates a
contract, include the affected producer, consumer, adapter, or boundary and
repeat.

Stop expansion when:

- the responsibility is replaced;
- all affected contract edges are migrated;
- surrounding contracts are stable;
- no observed unclassified bypass remains.

Do not expand merely to investigate unrelated defects or eliminate all
unknowns.

## 5. Execute unmerged

Use a branch or Draft PR for recursive discovery and scope adjustment. Within
the selected region:

- replace or reorganize the responsibility;
- migrate affected producers and consumers;
- remove duplicate mappings and downstream reinterpretation;
- delete or classify stale paths;
- preserve or explicitly update external contracts.

## 6. Verify

Against the final candidate tree:

- synchronize CodeGraph;
- trace production sinks back to the intended responsibility;
- verify affected producers and consumers use compatible contracts;
- verify consumers do not reconstruct upstream semantic decisions;
- exercise relevant positive, negative, divergence, collision,
  information-loss, and fail-closed cases;
- record unresolved dynamic or external surfaces.

Tests alone are insufficient; separate observed repository structure, executed
behavior, declarations, inference, and unknowns.

## 7. Merge gate

Record separately:

- responsibility closure;
- boundary-contract closure;
- abandonment safety;
- parent transformation completion.

The first three are merge gates. The parent may remain open only when a stable
record owns its remaining obligations and stop conditions.

## 8. Post-merge audit

Confirm the merge tree and runtime or concurrent-integration evidence. Record
pre-merge misses; do not use post-merge audit as normal planning.

## Planning output

- Semantic output and production sinks
- Responsibility before → after
- Selected region
- Affected observed producers and consumers
- Changed semantic contracts
- Migrations, removals, and classified paths
- Preserved external contracts
- Counterfactual and sink-level evidence
- Unresolved and out-of-scope surfaces
- Responsibility closure / contract closure / abandonment safety
