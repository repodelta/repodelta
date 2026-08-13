# Responsibility-closed delivery

Treat the repository as responsibility pipelines. A semantic change must:

1. replace the authority for the affected output;
2. migrate every observed affected upstream and downstream contract;
3. remove or classify stale producers, mappings, consumers, and bypasses;
4. verify that observed intended production sinks consume the new result.

Each changed boundary has one canonical semantic contract: preserved
properties, permitted loss, and failure behavior. Representations may differ
when their mappings preserve that contract. Consumers may adapt or project a
result, but must not re-decide semantics owned upstream.

Before changing or adding a derived semantic result, record its provenance
(observed, declared, inferred, or derived), authority scope (domain-wide,
cross-consumer, consumer-local, or presentation-only), canonical owner, and
authorized semantic dependencies. Consumer-local projection is allowed when
its truth is intentionally local; undeclared semantic production is not.

Mutation executes the recorded semantic plan. If implementation evidence
materially changes the target output, authority, affected contract, selected
region, or ownership of a derived result, re-plan explicitly before further
production-boundary mutation. Local helper organization and presentation
layout do not trigger re-planning when the semantic plan remains valid.

Expand the selected region only when the change invalidates an external
contract. Every mergeable state must be responsibility-closed,
abandonment-safe, and fail closed for unsupported semantics. Main is not an
exploration surface.

Tests alone do not prove closure. Keep declarations, repository and runtime
facts, inference, and unresolved surfaces distinct; bound conclusions by
observed coverage.

When a change reveals a stable semantic invariant, establish it with a
counterexample and sink-level evidence, then encode it at the smallest
sufficient machine-enforceable boundary. Prefer types, controlled construction,
module boundaries, or automated gates when they exclude a concrete invalid
transition. Do not harden exploratory semantics or add constraints that only
increase abstraction.

For non-trivial behavioral, responsibility, contract, data-flow, or
cross-component changes, follow `docs/agent-change-protocol.md`. Before creating
an Issue, follow `docs/issue-guidelines.md`; before committing or opening a PR,
follow `docs/commit-message-guidelines.md` and
`docs/pull-request-guidelines.md`.
