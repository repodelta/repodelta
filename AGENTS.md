## Responsibility-closed delivery

Treat the repository as responsibility pipelines. Change semantic
responsibilities, not files or diffs. Start from the output and production
sinks; identify each decision's authority, admitted inputs, proof obligation,
consumers, and bypasses.

Every mergeable state must be responsibility-closed and abandonment-safe:

- one effective production authority owns each responsibility in scope;
- alternate paths are removed or verifiably classified;
- if the parent transformation stops, the state remains correct, honest,
  maintainable, and independent of future wiring;
- unsupported semantics fail closed instead of producing success.

Main is not an exploration surface. Perform recursive discovery, scope
expansion, and counterfactual testing during planning and in an unmerged branch
or Draft PR. Expand an unsafe region before merge or stop. Tests alone do not
prove closure.

Treat code and structural indexes as repository facts; executed tests and
runtime observations as bounded behavioral evidence; and unexecuted tests,
documentation, history, names, and designs as declarations or hypotheses unless
independently grounded. Keep facts, intent, inference, and unresolved surfaces
distinct; report conflicts instead of silently reconciling them.

For non-trivial behavioral, authority, contract, data-flow, or cross-component
changes, follow `docs/agent-change-protocol.md`.

Before generating Git artifacts, follow:

- `docs/commit-message-guidelines.md` for commits;
- `docs/pull-request-guidelines.md` for pull requests.
