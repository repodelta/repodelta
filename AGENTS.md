## Responsibility-closed changes

Treat the repository as recursively composed responsibility pipelines.

The atomic unit of change is a semantic responsibility transition, not a
file, function, commit, or diff.

Start from the semantic output and its production sinks. Identify
observed candidate authorities, consumers, writers, projections, and
unclassified bypasses; then select the smallest responsibility-closed
region that can complete the transition.

Within the same execution scope, every mergeable repository state must
have one effective production authority per responsibility. Other paths
must be verifiably classified. Canonicality follows effective production
data flow, not names or design declarations.

If the requested scope cannot achieve responsibility closure, expand it
or stop implementation. Do not rely on a future PR to justify the current
merge state.

Tests alone do not prove closure. Bound conclusions by available
structural, runtime, test, and dynamic-boundary evidence.

## Change workflow

For non-trivial behavioral, authority, contract, data-flow, or
cross-component changes, read and follow:

- `docs/agent-change-protocol.md`

## Git delivery

Before generating Git artifacts, read and follow:

- Commits: `docs/commit-message-guidelines.md`
- Pull requests: `docs/pull-request-guidelines.md`