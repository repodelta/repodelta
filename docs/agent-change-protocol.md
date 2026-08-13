# Agent change protocol

Use this protocol for behavioral, responsibility, contract, data-flow, or
cross-component changes.

## 0. Semantic execution

Execute the change as:

```
OBSERVE → CLASSIFY SEMANTICS → PLAN → MUTATE CANDIDATE
→ VERIFY → HARDEN → ACCEPT
```

Observation, semantic decisions, mutation, verification, hardening, and
acceptance are distinct phases. Mutation executes the recorded semantic plan.
If implementation evidence materially changes the target output, authority,
affected contract, selected region, semantic owner, or merge-gate evidence,
update the plan before further production-boundary mutation. Read-only
investigation and local experiments may continue; authority, contract-bearing
types, cross-boundary mappings, and sink behavior wait for the updated plan.
Helper organization, local algorithms, and layout changes do not trigger a
re-plan when the semantic plan remains valid.

## 1. Fix the target

Define the semantic output, production sinks, current authority, intended
after-state, observed scope, and explicit exclusions. Start from behavior, not
expected files.

## 2. Census the pipeline

Trace:

- backward from sinks to producers and decisions;
- forward from the authority to actual consumers;
- laterally for competing writers, fallbacks, and reconstruction;
- across representation boundaries (parsing, normalization, identity,
  aggregation, projection, serialization, and deserialization);
- across trust, validation, persisted-state, derivation, decision, and
  consumer/projection boundaries.

Record dynamic and external unknowns; do not convert them into coverage.

## 3. Classify semantics and define contracts

For each changed semantic result and boundary, record:

- provenance: observed, declared, inferred, or derived;
- authority scope: domain-wide, cross-consumer, consumer-local, or
  presentation-only;
- canonical owner;
- authorized semantic dependencies, including relevant state transitions,
  topology, completeness, version, precedence, or failure state;
- high-risk orthogonal dependencies that must not control the result.

Then specify the semantic entity, equivalence rules, preserved properties,
permitted information loss, and behavior for incomplete, conflicting, or
unsupported input. Shared names or proximity do not prove equivalence. Define
counterexamples that distinguish contract preservation from accidental
agreement. Every deserialization edge must revalidate the canonical semantic
contract before constructing a validated domain object.

Use independence counterfactuals where practical: hold authorized semantic
dependencies constant, vary a high-risk orthogonal dependency, and verify that
the decision is unchanged.

Treat enforcement as part of the contract. First establish the invariant with
counterfactual and sink evidence, then choose the smallest sufficient boundary:
documentation for exploratory semantics, behavioral tests for established
behavior, distinct types or immutable state for stable domain distinctions,
controlled validators or derivation APIs for stable construction rules, and
module or static gates for stable architecture boundaries. Combine mechanisms
when they prevent different invalid transitions. Do not harden an uncertain
hypothesis or add a stronger mechanism that excludes no concrete invalid state.

## 4. Close the region

Begin with the responsibility being replaced. Keep a neighbor outside while
its contract remains valid; otherwise include it and repeat. Stop when the
responsibility and every affected contract edge are migrated, surrounding
contracts are stable, and no observed unclassified bypass remains. A
consumer-local result may remain local when its scope and owner are explicit
and it does not alter canonical facts. Do not expand to unrelated defects or
to eliminate every unknown.

## 5. Design top-down; implement bottom-up

Fix the region's input and output contracts, then recursively decompose it
into coherent sub-responsibilities and internal contracts. Identify newly
introduced derived semantic results and assign their scope, owner, and
authorized dependencies before implementation.

Implement leaf sub-responsibilities and their contracts, compose adjacent
sub-pipelines, migrate external producers and consumers, switch production
sinks, then remove duplicate decisions and stale paths. Use a branch or Draft
PR for discovery. Do not change a production boundary to leave an incomplete
internal pipeline for later. If implementation evidence changes a material
semantic plan element, record the plan delta before continuing.

## 6. Verify the final tree

- synchronize CodeGraph and retrace sinks to the intended authority;
- verify producer/consumer contract compatibility and absence of downstream
  semantic re-decision;
- verify semantic provenance, scope, owner, authorized dependencies, and
  independence counterfactuals for changed decisions;
- test positive, negative, divergence, collision, information-loss, and
  fail-closed behavior relevant to the change;
- verify hardened invariants at their production sinks; type, dependency, and
  static gates do not replace behavioral proof;
- for each changed serialized contract, enumerate its writers, readers,
  deserializers, validators, and persisted derived fields; test tampered input
  at each changed deserialization boundary;
- recompute persisted derived state from canonical inputs or check it against
  them; loading it must not create another authority;
- separate declarations, structural/runtime facts, inference, and unknowns.

Record responsibility closure, contract closure, abandonment safety, and parent
transformation completion separately. The first three are merge gates. A parent
may remain open only when a stable record owns its obligations and stop
conditions.

## 7. Audit after merge

Confirm the merge tree and available integration/runtime evidence. Record
pre-merge misses; post-merge audit is not deferred planning.

## Planning record

Capture only what is needed to execute and review the change:

- output, sinks, before/after authority, and selected region;
- changed semantic results with provenance, authority scope, canonical owner,
  authorized dependencies, and key orthogonal counterfactuals;
- affected producers, consumers, contracts, internal composition order,
  migrations, removals, classifications, and preserved boundaries;
- material re-plan deltas, when implementation evidence changed the recorded
  semantic plan;
- counterfactual, sink-level, and final-tree evidence;
- stable invariants, their current and target enforcement, and the concrete
  invalid transitions the target prevents;
- unresolved/excluded surfaces and the four completion states above.
