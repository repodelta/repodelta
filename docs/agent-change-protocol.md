# Agent change protocol

Use this protocol for behavioral, responsibility, contract, data-flow, or
cross-component changes.

## 0. Semantic execution

```
OBSERVE → CLASSIFY SEMANTICS → PLAN → MUTATE CANDIDATE
→ VERIFY → HARDEN → ACCEPT
```

Keep phases distinct. Mutation executes the recorded plan. If evidence
materially changes target, authority, contract, region, semantic owner, or
merge evidence, update the plan before further production-boundary mutation.
Investigation may continue; authority, contract-bearing types, cross-boundary
mappings, and sinks wait. Helpers, local algorithms, and layout do not trigger
a re-plan when the plan remains valid.

## 1. Fix the target

Define semantic output, production sinks, current authority, intended after-state,
observed scope, and exclusions. Start from behavior, not files.

## 2. Census the pipeline

Trace backward from sinks, forward from authority, and laterally for competing
writers, fallbacks, and reconstruction. Cover representation, trust/validation,
persisted-state, derivation/decision, and consumer/projection boundaries
(including parsing, normalization, identity, aggregation, serialization, and
deserialization). Record dynamic/external unknowns; do not convert them into
coverage.

## 3. Classify semantics and define contracts

For each changed result/boundary, record provenance (observed, declared,
inferred, derived), authority scope (domain-wide, cross-consumer,
consumer-local, presentation-only), owner, authorized semantic dependencies
(state transitions, topology, completeness, version, precedence, failure), and
high-risk orthogonal dependencies.

Then specify semantic entity, equivalence, preserved properties, permitted loss,
and behavior for incomplete, conflicting, or unsupported input. Names do not
prove equivalence; define distinguishing counterexamples. Revalidate the
canonical contract at changed deserialization edges before constructing a
validated domain object.

Where practical, hold authorized dependencies constant, vary an orthogonal
dependency, and verify the decision is unchanged. Establish invariants with
counterfactual/sink evidence, then choose the smallest sufficient enforcement
boundary; combine mechanisms only for different concrete invalid transitions.

## 4. Close the region

Begin with the responsibility being replaced. Keep a neighbor outside while
its contract remains valid; otherwise include it and repeat. Stop when the
responsibility and affected contract edges are migrated, surrounding contracts
are stable, and no observed unclassified bypass remains. A consumer-local
result may remain local when scope/owner are explicit and canonical facts are
unchanged. Do not expand to unrelated defects or eliminate every unknown.

## 5. Design and implement

Fix region input/output contracts; decompose sub-responsibilities and assign
scope, owner, and dependencies to new derived results. Implement leaves, compose
sub-pipelines, migrate producers/consumers, switch sinks, and remove duplicate
decisions/stale paths. Use a branch or Draft PR for discovery; do not leave a
production boundary incomplete. Record a plan delta before continuing if
implementation changes a material semantic plan element.

## 6. Verify the final tree

- retrace sinks to the intended authority; verify contract compatibility and no
  downstream semantic re-decision;
- verify changed results' provenance, scope, owner, dependencies, and
  independence counterfactuals;
- test relevant positive, negative, divergence, collision, information-loss,
  and fail-closed behavior;
- verify hardened invariants at sinks; machine gates do not replace proof;
- for changed serialized contracts, enumerate writers/readers/deserializers/
  validators/persisted fields, test tampering, and recompute/check persisted
  state against canonical inputs;
- separate declarations, runtime facts, inference, and unknowns.

Record responsibility closure, contract closure, abandonment safety, and parent
completion separately. The first three are merge gates. A parent may remain
open only when a stable record owns its obligations and stop conditions.

## 7. Audit after merge

Confirm the merge tree and available integration/runtime evidence. Record
pre-merge misses; post-merge audit is not deferred planning.

## Planning record

Capture only what is needed to execute/review:

- output, sinks, before/after authority, and selected region;
- changed results: provenance, scope, owner, dependencies, and key orthogonal
  counterfactuals;
- affected producers, consumers, contracts, composition order, migrations,
  removals, classifications, and preserved boundaries;
- material re-plan deltas, when the recorded plan changed;
- counterfactual, sink-level, final-tree, and hardening evidence;
- unresolved/excluded surfaces and the four completion states above.
