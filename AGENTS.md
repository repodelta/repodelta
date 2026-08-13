# Responsibility-closed delivery

Treat the repository as responsibility pipelines. A semantic change must:

1. replace the authority for the affected output;
2. migrate every observed affected upstream and downstream contract;
3. remove or classify stale producers, mappings, consumers, and bypasses;
4. verify that observed intended production sinks consume the new result.

Each changed boundary has one canonical contract: preserved properties,
permitted loss, and failure behavior. Representations may differ when mappings
preserve it; consumers may project but must not re-decide upstream semantics.

Before changing or adding a derived result, record provenance (observed,
declared, inferred, or derived), authority scope (domain-wide, cross-consumer,
consumer-local, or presentation-only), owner, and authorized semantic
dependencies. Explicitly local projection is allowed; undeclared production is
not.

Mutation executes the recorded plan. If evidence materially changes target,
authority, contract, region, or derived-result owner, re-plan before further
production-boundary mutation. Helpers and layout do not trigger re-planning
when the plan remains valid.

Expand the selected region only when an external contract is invalidated.
Every mergeable state must be responsibility-closed, abandonment-safe, and fail
closed for unsupported semantics. Main is not an exploration surface.

Tests alone do not prove closure; keep declarations, repository/runtime facts,
inference, and unresolved surfaces distinct.

For a stable invariant, use counterexample and sink evidence, then the smallest
machine-enforceable boundary that excludes a concrete invalid transition. Do
not harden uncertain semantics or increase abstraction without one.

For non-trivial behavioral, responsibility, contract, data-flow, or
cross-component changes, follow `docs/agent-change-protocol.md`. Before an
Issue, commit, or PR, follow its corresponding guideline in `docs/`.
