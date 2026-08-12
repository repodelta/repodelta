# Contributing to RepoDelta

RepoDelta welcomes Issues and pull requests from everyone. Bring a problem,
an idea, a useful feature, an integration, an evaluation case, or a different
approach to the project's coding workflow.

**People own intent and acceptance; people and agents are free to implement the
change in whatever way works.** An identifiable person owns each Issue's
direction and requirements. A pull request may be prepared or assigned to a
person, an agent, or both. Before it enters `main`, an identifiable human
maintainer reviews and approves the result.

Before contributing, see the guides for
[Issues](docs/issue-guidelines.md),
[agent changes](docs/agent-change-protocol.md),
[commits](docs/commit-message-guidelines.md), and
[pull requests](docs/pull-request-guidelines.md).

## Merge requirements

Every pull request must:

- receive an approving review from a designated maintainer;
- pass the required CI and RepoDelta review checks;
- resolve review conversations; and
- receive a new approval after later commits make an earlier review stale.

Opening an Issue or pull request does not grant write or merge access.
RepoDelta evaluates the resulting change, not how it was produced locally.
GitHub does not allow pull-request authors to approve their own PRs, so a PR
submitted through a maintainer's account needs another maintainer's approval.

## Optional bot submission

Maintainers can submit an agent-prepared branch through the repository's
GitHub App, then review it under their own human identity:

```bash
./tools/repodelta-bot submit --repo repodelta/repodelta --title "..." \
  --body-file pr.md --reviewer HUMAN_GITHUB_LOGIN
```

An App manager supplies their owner-only private key and App identifiers as
described by `./tools/repodelta-bot submit --help`. The bot only pushes and
opens the PR; a human maintainer still approves it. Submission fails closed if
the same commit was already pushed through a personal account, because an
up-to-date Git operation cannot make the App the effective pusher.

To update an existing bot-authored PR, first commit the new local result and
then let the App perform the branch update:

```bash
./tools/repodelta-bot push --repo repodelta/repodelta
```

Use `--expected-remote-head FULL_SHA` for an intentional history handoff. The
lease rejects the update if anyone changed the remote branch after that SHA was
observed.
