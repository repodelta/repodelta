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

## Optional bot identity for pull-request operations

When a coding agent creates or modifies a pull request, the GitHub operation
can use either the user's normal GitHub identity or the RepoDelta GitHub App
identity.

Using the App keeps agent-authored GitHub operations separate from the human
who requested or reviewed the work. This allows that human to independently
review and approve the pull request later under the repository's normal
review rules.

To push the current branch and create a pull request using the Bot identity:

```bash
./tools/repodelta-bot submit --repo repodelta/repodelta --title "..." \
  --body-file pr.md
```

Reviewers can still be requested normally:

```bash
./tools/repodelta-bot submit --repo repodelta/repodelta --title "..." \
  --body-file pr.md --reviewer GITHUB_LOGIN
```

The `--reviewer` option only requests a normal GitHub review. It does not assign
a special acceptance owner or change the repository's existing approval and
merge rules.

To update an existing pull-request branch using the Bot identity:

```bash
./tools/repodelta-bot push --repo repodelta/repodelta
```

Both `submit` and `push` obtain a GitHub App installation token and perform the
remote Git operation through the App rather than through the current user's
GitHub credentials.

An App manager supplies the owner-only private key and App identifiers as
described by `./tools/repodelta-bot submit --help`. Submission fails closed if
the same commit was already pushed through a personal account, because an
up-to-date Git operation cannot make the App the effective pusher.

Use `--expected-remote-head FULL_SHA` for an intentional history handoff. The
lease rejects the update if anyone changed the remote branch after that SHA was
observed.
