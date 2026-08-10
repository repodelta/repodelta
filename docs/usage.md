# Usage

RepoDelta runs after a pull request exists and writes a standalone interactive
HTML review brief. The default path is deterministic and does not require an
LLM provider.

## Install the CLI

Install RepoDelta once in an isolated tool environment; this does not modify a
target repository's virtual environment:

```bash
pipx install repodelta
```

`pipx` installs the PyPI release in its own managed environment and exposes the
`repodelta` command without changing a target project's dependencies.

## Contribute from a source checkout

```bash
python -m venv .venv
source .venv/bin/activate
pip install .
```

Contributors can install the editable development extra and run the
network-free test suite:

```bash
pip install -e .[dev]
pytest -q
```

## Review an offline fixture

```bash
repodelta review \
  --fixture fixtures/pr574.json \
  --output build/pr574.html
```

This path requires no network, GitHub token, model API, or company credentials.
See [Fixture schema](fixture-schema.md) for the versioned input contract.

## Review a live GitHub pull request

Run from any directory:

```bash
repodelta review --repo owner/repository --pr 123 --output build/pr-123.html
```

RepoDelta obtains live metadata from GitHub and fetches the exact PR head and
base revisions into a private temporary Git source. Pass
`--repo-root /path/to/local/repository` only as an explicit optimization when a
local repository already contains both commit objects; its current branch and
working-tree state are not used.

The GitHub adapter collects:

- pull-request metadata and changed-file patches through GitHub REST;
- the Issue selected by GitHub's Development link through GitHub GraphQL;
- current-head Check Runs and commit statuses through GitHub REST.

It records missing links, patches, head SHAs, checks, statuses, and file-limit
truncation as explicit diagnostics. Missing evidence is never converted into a
passing conclusion.

### Author review inputs

Link the governing Issue through GitHub's Development relationship; typing an
Issue number in PR prose does not create that authority. Prefer one reviewable
obligation per item under `Requirements`, and keep goals, scope, guardrails, and
verification expectations in their own sections. See the
[Issue authoring guide](issue-guidelines.md) and
[PR authoring guide](pull-request-guidelines.md). The complete heading-to-type
and authority mapping is documented under
[Architecture → Semantic authority](architecture.md#semantic-authority).

### Structural analysis

Structure-aware analysis is the live-review default. RepoDelta creates private
detached worktrees at the PR's exact head and base revisions, initializes an
isolated Codegraph index once in each worktree, maps changed hunks to symbols,
collects bounded structural paths and ownership, and removes the fetched Git
source, worktrees, and indexes after success or failure.

Authentication is supplied only to the fetch subprocess and is not written to
the remote URL, command arguments, Git configuration, review metadata, or HTML.
RepoDelta first uses a `codegraph` executable on `PATH`; otherwise it runs
`npx --yes @colbymchenry/codegraph`. Codegraph is an external MIT-licensed
runtime and is not bundled in the RepoDelta Python distribution.

Use the explicit Codegraph-free path when structural analysis is not wanted:

```bash
repodelta review \
  --repo owner/repository \
  --pr 123 \
  --no-structural-graph \
  --output build/pr-123.html
```

This path fetches only the exact head and creates one temporary head worktree
for deterministic repository scans; it skips the base revision and both
Codegraph indexes.

Missing, stale, partial, invalid, or unreadable structural data never prevents
the deterministic report from being generated. Use `--verbose` for individual
structural diagnostics.

### GitHub authentication

For a private repository, `GITHUB_TOKEN` must be able to read the repository.
Public repositories may work without a token, subject to GitHub's
unauthenticated rate limits.

Use `--github-token-env OTHER_ENV_NAME` to select another environment variable.
Use `--github-api-url` for GitHub Enterprise Server. When a token is present, an
Enterprise host must also be trusted with
`--trusted-github-api-host HOST`; only HTTPS URLs are accepted.

## Run in GitHub Actions

The repository includes [`.github/workflows/review.yml`](../.github/workflows/review.yml).
It runs automatically for pull requests in this repository and can be started
with **Actions → RepoDelta review → Run workflow** for another readable
repository and PR number.

Each run exposes a report link in the job summary and retains the HTML as an
artifact for 14 days. The built-in `GITHUB_TOKEN` covers pull requests in the
same repository. To review another private repository, configure a
`REPODELTA_GITHUB_TOKEN` Actions secret with read access to that target.

## Evaluate retrieval offline

Run the golden evaluation suite without GitHub, Codegraph, or model credentials:

```bash
repodelta evaluate \
  --suite fixtures/evaluation-suite.json \
  --json-output build/evaluation.json \
  --markdown-output build/evaluation.md
```

The command returns non-zero when configured thresholds fail. See
[Evaluation](evaluation.md) for the versioned contracts, metrics, and safety
boundary.

## Experimental LLM shadow evaluation

LLM shadow selection is opt-in, non-authoritative, and excluded from the
supported product path. See [LLM shadow evaluation](llm-shadow.md) for provider
configuration, blinded labeling, replay, and comparison commands.

## Operational safety

- Tokens are read from environment variables and are not written to review
  metadata or generated output.
- Generated HTML creates links only for absolute HTTP and HTTPS URLs.
- A token is never sent to a custom GitHub API host unless the host is explicitly
  trusted.
- Repository facts, authored claims, inference, assessment, and unresolved
  coverage remain distinguishable in the report.
