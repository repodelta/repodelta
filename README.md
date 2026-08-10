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

The report is a standalone HTML file. A reviewer can:

- start from Issue-backed requirements and guardrails or PR-authored
  transformation claims;
- explore changed symbols, ownership, calls, imports, and nearby runtime or test
  structure in the structural delta graph;
- select a claim to focus the graph and expand its canonical observations,
  conservative assessment, source links, and coverage limits;
- distinguish supporting evidence from contradiction, missing evidence, and
  incomplete collection instead of treating relevance as proof.

The graph below alternates between the default **All** view and the result of
expanding **R4**. The graph membership stays fixed while the matching region is
highlighted and unrelated structure is muted.

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

Run from a local checkout of the target repository:

```bash
cd /path/to/local/repository
prismcode review --repo owner/repository --pr 123 --output build/pr-123.html
```

PrismCode reads the PR, its GitHub Development-linked Issue, changed-file
patches, and current-head checks. The current directory is the default
`--repo-root`: PrismCode creates private worktrees at the PR's exact base and
head revisions, initializes a separate Codegraph index in each, analyzes them,
and removes both worktrees and indexes. Pass `--repo-root` only when the target
checkout is elsewhere. Use `--no-structural-graph` for the explicit
Codegraph-free path.

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

Tokens are read from environment variables and are not stored in review
metadata or generated HTML. Generated reports create hyperlinks only for
absolute HTTP and HTTPS URLs. A token is never sent to a custom GitHub API host
unless that host is explicitly trusted.

## License

PrismCode is licensed under the [MIT License](LICENSE).
