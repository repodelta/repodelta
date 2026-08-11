# Contributing to RepoDelta

RepoDelta welcomes Issues and pull requests from everyone. You can report a
problem, suggest a capability, improve the implementation or documentation,
add an integration or evaluation case, or propose a different approach to the
project's coding workflow.

Issues express product direction and must remain accountable to people. An
agent may help research or draft an Issue, but the proposer or assignee is an
identifiable person who owns its intent, requirements, and follow-through.

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

## Execution and accountability

RepoDelta governs the resulting change, not how it was produced locally. A
pull request may be prepared or assigned to a person, an agent, or both, and an
agent may submit through a person's account. The repository does not treat the
PR account as proof of who performed the implementation.

Human accountability remains at both sides of that execution. An identifiable
person owns the Issue's direction and requirements, and an identifiable human
maintainer owns the decision to accept the resulting change. Agents may assist
either process, but they do not replace the accountable Issue owner or provide
the approving review.

GitHub does not allow a pull-request author to approve their own pull request.
When an agent submits through a maintainer's personal account, another
designated maintainer must therefore provide the approval.
