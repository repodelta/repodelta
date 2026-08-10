# PrismCode

PrismCode turns a completed pull request into an interactive, requirement-first
review report.

It sits after a human or coding agent has written code and opened a PR:

```text
Human or coding agent
        ↓ writes code
Pull request + linked Issue + CI
        ↓ prismcode review
Interactive HTML review brief
        ↓ inspect evidence and gaps
Human review decision
```

PrismCode does not write the change or approve it. It connects the PR's authored
requirements and transformation claims to the code, structural relationships,
and current-head checks a reviewer can actually inspect.

![PrismCode Brief with an Issue-backed goal](docs/assets/prismcode-report-overview.jpg)

PrismCode carries Issue objectives (`O`), requirements (`R`), and guardrails
(`G`) into source-linked review rows alongside PR-authored transformation
claims.

![Issue requirements and guardrails in the Verification section](docs/assets/prismcode-verification-focus.png)

Expanding a row shows its observations and assessment and focuses the graph
below. The animation alternates between **All** and **R4**: graph membership
stays fixed while the associated structure is highlighted.

![Structural graph changing from All to an R4-focused view](docs/assets/prismcode-structural-graph.webp)

## Quick start

Live structure-aware reviews require Git and either the external
[Codegraph](https://github.com/colbymchenry/codegraph) CLI or Node.js with
`npx`. From a PrismCode source checkout:

```bash
python -m venv .venv
source .venv/bin/activate
pip install .
prismcode review --repo prismcode-ai/prismcode --pr 210 --output build/pr-210.html
```

Open `build/pr-210.html` in a browser. PrismCode reads `GITHUB_TOKEN` when it is
set, otherwise tries the authenticated `gh` CLI for the configured GitHub host;
public repositories can also use GitHub's unauthenticated limits.

## Review a GitHub pull request

`--repo` reads live PR, linked-Issue, patch, and check data from GitHub; source
analysis still uses a local Git checkout containing the PR's base and head
objects. From that target checkout, run:

```bash
cd /path/to/local/repository
prismcode review --repo owner/repository --pr 123 --output build/pr-123.html
```

When running from somewhere else, identify the same local checkout explicitly:

```bash
prismcode review \
  --repo owner/repository \
  --pr 123 \
  --repo-root /path/to/local/repository \
  --output build/pr-123.html
```

PrismCode creates private worktrees at the PR's exact base and head revisions,
initializes a separate Codegraph index in each, analyzes them, and removes both
worktrees and indexes. Remote-only source analysis is not currently supported.
Use `--no-structural-graph` for the explicit Codegraph-free path; it still
requires the local checkout for an exact head worktree.

For a network-free smoke test instead:

```bash
prismcode review --fixture fixtures/pr574.json --output build/pr574.html
```

See [Usage](docs/usage.md) for authentication, structural analysis, CI
integration, diagnostics, and advanced commands.

## Add it to the PR workflow

The included [PrismCode review workflow](.github/workflows/review.yml) runs on
pull requests and can also be started manually for a target repository and PR.
Each run places the report link in the job summary and retains the HTML as a
GitHub Actions artifact.

The intended loop is simple:

1. A human or coding agent opens or updates a PR.
2. CI runs PrismCode against that PR revision.
3. The reviewer opens one report and inspects the requirement-to-evidence path,
   structural change, checks, and unresolved coverage.
4. The PR is revised or reviewed using those observations; PrismCode itself
   does not make the merge decision.

## Deterministic by default

The supported product path is deterministic. A normal `prismcode review` run
requires no model and sends no repository content to an LLM provider. Canonical
diff facts, symbols, structural graphs, evidence routing, assessment, and HTML
conclusions remain under deterministic authority.

An opt-in, non-authoritative LLM shadow path exists for research only. Its
current evaluation is tracked in [#211](https://github.com/prismcode-ai/prismcode/issues/211),
and separate future experiments are tracked in
[#224](https://github.com/prismcode-ai/prismcode/issues/224),
[#225](https://github.com/prismcode-ai/prismcode/issues/225),
[#226](https://github.com/prismcode-ai/prismcode/issues/226), and
[#227](https://github.com/prismcode-ai/prismcode/issues/227). See
[LLM shadow evaluation](docs/llm-shadow.md) for the experimental commands and
safety boundary.

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

PrismCode runs locally: repository checkout, temporary base/head worktrees,
Codegraph indexes, deterministic analysis, and final HTML stay on the machine
or CI runner where the command executes. A live review calls the configured
GitHub API to collect PR, linked-Issue, and check data; the optional LLM shadow
path is the only mode that sends bounded review content to a model provider.

Tokens are read from environment variables and are not stored in review
metadata or generated HTML. Generated reports create hyperlinks only for
absolute HTTP and HTTPS URLs. A token is never sent to a custom GitHub API host
unless that host is explicitly trusted.

## Build the next layer with us

Change understanding is only the first step. PrismCode is also an open
experiment in making coding agents maintainable and extensible enough to work
on production code: every change is used to test and refine the repository's
own method, not only its report generator.

That method starts in [AGENTS.md](AGENTS.md) and is made operational by four
guides: [Issue authoring](docs/issue-guidelines.md), the
[agent change protocol](docs/agent-change-protocol.md),
[commit messages](docs/commit-message-guidelines.md), and
[pull requests](docs/pull-request-guidelines.md). They define how requirements,
responsibility boundaries, implementation transitions, verification, and
post-change learning stay connected.

Contributions and competing approaches are welcome. You can improve an
existing adapter, help design [requirement sources beyond GitHub Issues](https://github.com/prismcode-ai/prismcode/issues/233)
such as Jira, add an evaluation case, or challenge the coding method with a
concrete counterexample. Start with the
[open Issues](https://github.com/prismcode-ai/prismcode/issues) or open a
focused Issue using the repository's authoring guide.

## License

PrismCode is licensed under the [MIT License](LICENSE).
