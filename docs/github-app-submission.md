# GitHub App submission

RepoDelta maintainers may submit a local branch through a GitHub App so the
pull request has an execution identity distinct from the human maintainer who
reviews it. This is an optional submission mechanism, not a requirement for
contributors or local agent use.

The App needs only repository metadata read access plus contents and pull
requests read/write access. It does not need administration, organization,
secrets, checks, Actions, or workflow permissions and must not bypass the
protected `main` branch.

## Configure a maintainer workstation

Each trusted App manager generates and stores a private key locally. Do not
share a key, commit it, put it in a Git remote, or pass its contents through an
environment variable. Restrict the file to its owner:

```bash
chmod 600 /path/to/app-private-key.pem
export REPODELTA_BOT_APP_ID=4557115
export REPODELTA_BOT_INSTALLATION_ID=152885056
export REPODELTA_BOT_PRIVATE_KEY=/path/to/app-private-key.pem
```

The App and installation IDs are identifiers, not secrets. The private key is
the long-lived credential and remains outside the repository.

## Submit a branch

Commit the intended change locally, prepare the PR body in a file, and run:

```bash
repodelta-bot submit \
  --repo repodelta/repodelta \
  --title "type(responsibility): describe the transition" \
  --body-file /path/to/pr-body.md \
  --reviewer HUMAN_GITHUB_LOGIN
```

The command uses the current local branch name by default. `--head`, `--base`,
`--repo-root`, multiple `--reviewer` values, and `--draft` are available when
needed.

For each invocation, the command signs a short-lived App JWT, exchanges it for
an installation token, supplies that token to Git through an owner-only
temporary askpass file, pushes `HEAD`, and creates the pull request. Temporary
token material is removed on success and failure. The token is never placed in
Git arguments, remote URLs, persistent Git configuration, or command output.

The command does not approve or merge the PR. A human maintainer still reviews
the result, and the repository ruleset remains the acceptance authority.
