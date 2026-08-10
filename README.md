# RepoDelta

RepoDelta turns a pull request into an interactive visual map of what changed
across the repository—and helps reviewers judge whether the implementation
matches its acceptance criteria.

AI agents can now produce changes faster and at a scale that makes supervising
every execution impractical. RepoDelta shifts human oversight to the acceptance
boundary: before a result enters the codebase, reviewers can understand and
govern what changed without replaying every agent step.

It sits after a human or coding agent has written code and opened a PR:

```text
Human or coding agent
        ↓ writes code
Pull request + linked Issue + CI
        ↓ repodelta review
Interactive HTML review brief
        ↓ inspect evidence and gaps
Human review decision
```

RepoDelta does not write the change or approve it. It connects the PR's authored
requirements and transformation claims to the code, structural relationships,
and current-head checks a reviewer can actually inspect.

![RepoDelta Brief with an Issue-backed goal](https://raw.githubusercontent.com/repodelta/repodelta/main/docs/assets/repodelta-report-overview.jpg)

RepoDelta carries Issue objectives (`O`), requirements (`R`), and guardrails
(`G`) into source-linked review rows alongside PR-authored transformation
claims.

![Issue requirements and guardrails in the Verification section](https://raw.githubusercontent.com/repodelta/repodelta/main/docs/assets/repodelta-verification-focus.png)

Expanding a row shows its observations and assessment and focuses the graph
below. The animation alternates between **All** and **R4**: graph membership
stays fixed while the associated structure is highlighted.

![Structural graph changing from All to an R4-focused view](https://raw.githubusercontent.com/repodelta/repodelta/main/docs/assets/repodelta-structural-graph.webp)

RepoDelta also carries PR-authored transformation claims (`T`) and completion
conditions (`CC`) into the same inspection flow. When a claim names a concrete
file or symbol in a Markdown code span, selecting it focuses the associated
code and relationships. Selector-free or unmatched prose stays visible without
an invented graph mapping, so a reviewer can distinguish a coding agent's
claim from the structure that actually changed. See the
[authoring guide](docs/pull-request-guidelines.md).

## Quick start

Live structure-aware reviews require Python 3.11+, Git, and either the external
[Codegraph](https://github.com/colbymchenry/codegraph) CLI or Node.js with
`npx`. Install the CLI once in its own isolated environment with
[`pipx`](https://pipx.pypa.io/):

```bash
pipx install repodelta
```

This installs RepoDelta from PyPI without modifying any target project's
virtual environment. Contributors can use the editable source installation in
[Usage](docs/usage.md).

Then review a PR from any directory; no checkout of the target repository is
required:

```bash
repodelta review --repo owner/repository --pr 123 --output report.html
```

Open `report.html` in a browser. RepoDelta reads `GITHUB_TOKEN` when it is set,
otherwise tries the authenticated `gh` CLI for the configured GitHub host;
public repositories can also use GitHub's unauthenticated limits.

## Review a GitHub pull request

`--repo` reads live PR, linked-Issue, patch, and check data from GitHub. By
default RepoDelta also fetches the exact PR base and head revisions into a
private temporary workspace, so the command can run from any directory:

```bash
repodelta review --repo owner/repository --pr 123 --output build/pr-123.html
```

If a local repository already contains both revisions, use it as an explicit
optimization:

```bash
repodelta review \
  --repo owner/repository \
  --pr 123 \
  --repo-root /path/to/local/repository \
  --output build/pr-123.html
```

RepoDelta verifies the fetched revisions against GitHub metadata, creates
private worktrees and separate Codegraph indexes, then removes every owned Git
source, worktree, and index after success or failure. Credentials remain
process-scoped and never enter the Git URL, command arguments, report, or
persisted repository configuration. `--no-structural-graph` is Codegraph-free
and fetches only the exact head required by deterministic repository scans.

Private repositories use the same `GITHUB_TOKEN` or authenticated `gh`
credentials; do not put a token in the command or repository URL. For GitHub
Enterprise Server, name both the API endpoint and the host explicitly trusted
to receive those credentials:

```bash
repodelta review \
  --repo team/project \
  --pr 123 \
  --github-api-url https://github.company.com/api/v3 \
  --trusted-github-api-host github.company.com \
  --output report.html
```

The trust option must match the HTTPS API host. RepoDelta refuses to send a
token to any other custom host, which protects credentials from an accidental
or malicious API URL.

For a network-free smoke test instead:

```bash
repodelta review --fixture fixtures/pr574.json --output build/pr574.html
```

See [Usage](docs/usage.md) for authentication, structural analysis, CI
integration, diagnostics, and advanced commands.

## Add it to the PR workflow

The included [RepoDelta review workflow](.github/workflows/review.yml) runs on
pull requests and can also be started manually for a target repository and PR.
Each run places the report link in the job summary and retains the HTML as a
GitHub Actions artifact.

The intended loop is simple:

1. A human or coding agent opens or updates a PR.
2. CI runs RepoDelta against that PR revision.
3. The reviewer opens one report and inspects the requirement-to-evidence path,
   structural change, checks, and unresolved coverage.
4. The PR is revised or reviewed using those observations; RepoDelta itself
   does not make the merge decision.

## Deterministic core, optional LLM research

The complete supported product works without an LLM. A normal
`repodelta review` run sends no repository content to a model provider;
canonical diff facts, symbols, structural graphs, evidence routing,
assessment, and HTML conclusions remain deterministic.

RepoDelta is also exploring where an LLM can add semantic flexibility without
becoming an ungrounded review authority:

| Area | Status | Role |
| --- | --- | --- |
| Full review generation | Supported, deterministic | Produces the complete interactive report and every formal conclusion without a model. |
| Candidate evidence interpretation | Experimental ✓ | In an opt-in shadow run, the LLM classifies bounded deterministic candidates as selected, rejected, or insufficient and labels their evidence relationship and semantic role. |
| LLM-assisted semantic intake and R/G-to-subgraph mapping | To explore | Test whether a model can understand less structured Issue language and improve requirement-to-code retrieval. |
| Architectural overlays and grounded explanations | To explore | Test model-assisted higher-level views and explanations while preserving source links, uncertainty, and deterministic authority. |

The shadow result never changes the formal report, assessment, or merge
decision. It is evaluated separately against deterministic selection and
frozen human labels. See [LLM shadow evaluation](docs/llm-shadow.md) for the
commands and safety boundary; current and planned experiments are tracked in
[#211](https://github.com/repodelta/repodelta/issues/211),
[#224](https://github.com/repodelta/repodelta/issues/224),
[#225](https://github.com/repodelta/repodelta/issues/225),
[#226](https://github.com/repodelta/repodelta/issues/226), and
[#227](https://github.com/repodelta/repodelta/issues/227).

## Documentation

- [Usage](docs/usage.md) — local, GitHub, and Actions workflows
- [Architecture](docs/architecture.md) — canonical stages, ownership, and
  dependency direction
- [Review retrieval design](docs/review-retrieval-design.md) — evidence and
  structural retrieval contracts
- [Evaluation](docs/evaluation.md) — offline suites, metrics, and gates
- [Provenance](docs/provenance.md) — source and evidence identity
- [Fixture schema](docs/fixture-schema.md) — offline input format
- [Issue authoring](docs/issue-guidelines.md) and
  [PR authoring](docs/pull-request-guidelines.md) — source contracts for
  requirements and change claims
- [Agent change protocol](docs/agent-change-protocol.md) — the repository's
  responsibility-closed coding method

## Security

RepoDelta runs locally: temporary source fetches and base/head worktrees,
Codegraph indexes, deterministic analysis, and final HTML stay on the machine
or CI runner where the command executes. A live review calls the configured
GitHub API and Git host to collect PR metadata and the exact reviewed source;
the optional LLM shadow path is the only mode that sends bounded review content
to a model provider.

Tokens are read from environment variables or the authenticated `gh` CLI and
are not stored in Git URLs, persisted Git configuration, review metadata, or
generated HTML. Generated reports create hyperlinks only for absolute HTTP and
HTTPS URLs. Official GitHub is trusted by default; a custom GitHub API host
must be named explicitly before RepoDelta will send it a token.

## Build the next layer with us

Structural change understanding is only the first layer. We invite researchers
and engineers to contribute on two connected fronts:

- **Build RepoDelta.** Propose useful capabilities, improve existing behavior,
  add integrations and evaluation cases, or challenge product assumptions with
  evidence.
- **Improve the method.** RepoDelta's own development is a shared experiment in
  coding workflows designed for an agent-native era. The current method starts
  in [AGENTS.md](AGENTS.md) and is made operational by four guides:
  [Issue authoring](docs/issue-guidelines.md), the
  [agent change protocol](docs/agent-change-protocol.md),
  [commit messages](docs/commit-message-guidelines.md), and
  [pull requests](docs/pull-request-guidelines.md). It is a working approach,
  not doctrine: contributors can question it, compare alternatives, and
  demonstrate that another method produces changes that are more maintainable,
  extensible, or trustworthy.

The current method is visible in every report. Issue-authored objectives,
requirements, and guardrails (`O/R/G`) describe what the change must achieve;
PR-authored transformation claims and completion conditions (`T/CC`) describe
what the human or coding agent says it changed. RepoDelta places both against
the observed diff and structural graph, making mismatches, missing evidence,
and unresolved coverage inspectable instead of trusting the PR description as
proof.

These two contribution paths reinforce each other: product changes create real
cases for evaluating workflow methods, and better methods improve how RepoDelta
itself evolves.

Improve an existing adapter, help design
[requirement sources beyond GitHub Issues](https://github.com/repodelta/repodelta/issues/233)
such as Jira, add an evaluation case, or bring a concrete counterexample or
alternative method. Start with the
[open Issues](https://github.com/repodelta/repodelta/issues) or open a
focused Issue using the repository's authoring guide.

## License

RepoDelta is licensed under the [MIT License](LICENSE).
