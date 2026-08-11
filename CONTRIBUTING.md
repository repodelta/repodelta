# Contributing to RepoDelta

RepoDelta welcomes Issues and pull requests from everyone. You can report a
problem, suggest a capability, improve the implementation or documentation,
add an integration or evaluation case, or propose a different approach to the
project's coding workflow.

Before opening an Issue, follow the repository's
[Issue authoring guide](docs/issue-guidelines.md). Before submitting code,
follow the [agent change protocol](docs/agent-change-protocol.md) when it
applies, along with the guides for
[commits](docs/commit-message-guidelines.md) and
[pull requests](docs/pull-request-guidelines.md).

## Acceptance boundary

Anyone may propose a change, but only repository maintainers can accept one
into `main`. Every pull request must:

- receive an approving review from a designated maintainer;
- pass the required CI and RepoDelta review checks;
- resolve review conversations; and
- receive a new approval if later commits make the earlier review stale.

Opening an Issue or pull request does not grant write or merge access. These
rules apply equally to changes proposed by maintainers: an author cannot
approve their own pull request.

## Agent-authored changes

Submission identity and acceptance identity are separate responsibilities.
Agent-authored pull requests should be opened by RepoDelta's dedicated bot or
GitHub App, not through the personal credentials of the maintainer directing
the work. Any designated maintainer may then review and approve the pull
request, including the maintainer who directed that agent execution.

When an agent instead submits through a maintainer's personal account, GitHub
treats that maintainer as the pull-request author. The author cannot approve
their own pull request, so another designated maintainer must review it.
