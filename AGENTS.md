## Responsibility-closed delivery

Treat the repository as responsibility pipelines.

For a semantic change:

1. replace the responsibility that owns the affected output;
2. migrate every affected observed upstream and downstream semantic contract;
3. remove or classify stale producers, mappings, consumers, and bypasses;
4. verify that the intended production sinks consume the new result.

For each changed semantic boundary, define its canonical semantic contract,
required preserved properties, permitted information loss, and failure
behavior. Different representations are allowed when their mappings preserve
that contract.

Consumers may adapt, calculate, or project results, but must not independently
re-decide or override semantics already owned upstream.

Expand the selected region only when the change invalidates a boundary contract
outside it. Stop when the responsibility is replaced and all observed affected
contracts are stable again.

Every mergeable state must be responsibility-closed and abandonment-safe.
Unsupported or incomplete semantics must fail closed rather than produce
success. Main is not an exploration surface.

Tests alone do not prove closure. Bound conclusions by observed structural,
runtime, test, and declared dynamic-boundary evidence. Keep facts,
declarations, inference, and unresolved surfaces distinct.

For non-trivial behavioral, responsibility, contract, data-flow, or
cross-component changes, follow `docs/agent-change-protocol.md`.

Before generating Git artifacts, follow:

- `docs/commit-message-guidelines.md`;
- `docs/pull-request-guidelines.md`.
