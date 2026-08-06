## Responsibility-closed delivery

Treat the repository as responsibility pipelines. A semantic change must:

1. replace the authority for the affected output;
2. migrate every observed affected upstream and downstream contract;
3. remove or classify stale producers, mappings, consumers, and bypasses;
4. prove that intended production sinks consume the new result.

Each changed boundary has one canonical semantic contract: preserved
properties, permitted loss, and failure behavior. Representations may differ
when their mappings preserve that contract. Consumers may adapt or project a
result, but must not re-decide semantics owned upstream.

Expand the selected region only when the change invalidates an external
contract. Every mergeable state must be responsibility-closed,
abandonment-safe, and fail closed for unsupported semantics. Main is not an
exploration surface.

Tests alone do not prove closure. Keep declarations, repository and runtime
facts, inference, and unresolved surfaces distinct; bound conclusions by
observed coverage.

For non-trivial behavioral, responsibility, contract, data-flow, or
cross-component changes, follow `docs/agent-change-protocol.md`. Before
creating Git artifacts, follow `docs/commit-message-guidelines.md` and
`docs/pull-request-guidelines.md`.
