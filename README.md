# PrismCode

PrismCode generates requirement-first, evidence-linked pull request review briefs.

Its core workflow connects explicit Issue/Ticket acceptance criteria to pull-request code
evidence and requirement-specific CI/Actions observations:

```text
Issue acceptance criteria -> R1/R2/... -> PR/code evidence -> checks/workflows -> review brief
```

This repository is the standalone open-core implementation. It does not import company-private packages. The fixture workflow requires no network, model API, or company credentials; the GitHub workflow talks only to the configured GitHub API.

## Current scope

The open core provides:

- a versioned, conclusion-free `ReviewSourcePacket` shared by fixture and GitHub ingestion;
- conclusion-free requirements plus one canonical evidence catalog and typed fact-routing projection;
- offline JSON fixture ingestion;
- live GitHub pull request metadata and changed-file ingestion;
- GitHub GraphQL Development-link Issue ingestion plus current-head REST check-run and commit-status observations;
- one-pass semantic extraction with separate role, purpose, and authority for
  Issue/PR obligations, goals, scope, boundaries, implementation, baselines,
  verification claims, and intent;
- a deterministic analyzer that builds explainable evidence candidates without declaring implementation or verification status;
- a requirement-first static HTML renderer;
- a local CLI;
- optional repository-local Codegraph hunk-to-symbol mapping with explicit
  availability and freshness diagnostics;
- bounded Codegraph paths from changed symbols to unchanged runtime/test
  neighbors;
- one canonical, deterministic evidence catalog where mapped code changes use
  exact symbol identities and only unmapped spans/files remain fallbacks,
  alongside bounded paths and CI/runtime observations;
- explainable deterministic O/S/R/G/V review contracts, typed C/B/VC PR
  claims, typed T/CC transformation declarations, and evidence candidates;
- deterministic same-R/G, same-slot candidate convergence with typed
  dominance, bridge reachability, canonical changed-anchor and verification
  sets, bounded structural evidence subgraphs, compact claim selection, and
  explicit coverage diagnostics;
- source-backed executable repository scan plans and bounded PR-head
  observations for G guardrails, without treating zero matches as satisfaction
  or repository-wide absence;
- an R-first consistency view with claim/evidence candidates, binding basis,
  source links, and vertically aggregated coverage gaps;
- an Actions workflow for automatic PR reports and manually targeted reviews;
- clean-install CI with network-free tests.
- a deterministic offline evaluation suite for binding, structural-path,
  evidence-classification, and recorded LLM-shadow semantic-mapping baselines.

The GitHub adapter intentionally emits source facts only. Linked Issues come
from GitHub's `closingIssuesReferences` GraphQL field, not Issue numbers typed
into PR prose. The analyzer applies one authority policy:

- linked-Issue Acceptance Criteria, Requirements, and Definition of Done become
  authoritative `R1`, `R2`, ... obligations and `G1`, `G2`, ... guardrails;
- without a selected linked Issue, the same explicit PR-description sections
  become provisional obligations;
- Goals/Objectives become `O1`, `O2`, ... retrieval context;
- Scope/In scope become `S1`, `S2`, ... retrieval context and never acceptance
  criteria;
- linked-Issue Verification/Validation/Testing sections become `V1`, `V2`, ...
  authored verification expectations;
- linked-Issue Out of scope/Boundary statements become authoritative
  `G1`, `G2`, ... guardrails;
- PR Summary/Implementation/Changes and Boundary statements become
  `C1`, `C2`, ... PR-authored claims;
- PR Baseline/Results and Verification/Testing become `B1` and `VC1` claims;
- structured PR transformation sections become typed `T1`, `T2`, ...
  declarations, while Completion conditions become `CC1`, `CC2`, ...;
- the PR introduction or title is intent only and is never promoted to `R1`.

When no explicit acceptance criteria are present, the report says so instead
of manufacturing a requirement from the PR title. Candidate relevance is never
presented as implementation, verification, or acceptance.

PRs may declare an independently verifiable transformation contract with
exact Markdown headings:

```markdown
## Change

## Before
## After

## Selected region
### Inputs
### Outputs
### Boundaries

## Before topology
## After topology
## Canonical authority
## Production path

## Migration
### Producers
### Consumers
### Tests

## Removed legacy paths
## Completion conditions
## Uncertainty
```

Generic Before/After fields remain unclassified state context; the topology
variants are explicit structural claims. All fields remain PR-authored claims.
The current analyzer serializes them
once in `ReviewBrief.transformation_contract`; it does not treat them as
repository observations, assessment results, or merge approval. Contract v4
also records deterministic selector predicates only when the author uses
explicit Markdown code spans such as `` `DeterministicAnalyzer` ``,
`` `src/prismcode/pipeline.py` ``, or an ordered
`` `Source` -> `Analyzer` -> `ReviewBrief` `` path. Unmarked prose remains a
claim with a typed `no_explicit_selector` diagnostic. PrismCode does not guess
code identities from prose, and this predicate layer does not itself observe,
associate, assess, or display repository evidence.

The next deterministic stage resolves each explicit predicate value against
canonical changed structural identities on its expected Base/Head side. Its
`TransformationSubjectSelection` retains every exact match and emits one typed
diagnostic for an unmatched selector; it never guesses from claim prose,
traverses neighboring graph nodes, or treats a match as verification. This is
the sole seed boundary for later bounded transformation closure.

Bounded transformation closure then reuses only structural paths already
collected by the Codegraph provider for those selected seeds. It retains whole
path identities at up to three hops, adds their canonical relation and ownership
change facts, and records an explicit diagnostic when the identity safety limit
defers support. This stage does not invoke Codegraph, perform another graph
traversal, widen selection from prose, or decide presentation topology.

Independently, the facts stage reconstructs
`ReviewBrief.observed_transformation` from canonical diff, Base/Head structural,
path, replacement-candidate, and current-head verification fact IDs. It never
reads the authored transformation contract. The routing stage then creates a
typed `ReviewBrief.transformation_alignment` from eligible observed facts and
provider-owned closure facts. Alignment records deterministic relevance and
coverage only; it does not select evidence, assess a claim, or approve merge.
The assessment stage then assigns exactly one conservative
`demonstrated` / `partial` / `contradicted` / `unverified` status to each typed
transformation claim. It uses only aligned canonical facts, complete closure
observations, and current-head verification. Predicate-level roles remain
visible; when one binding has different roles across a conjunctive claim,
contradiction controls the claim-level binding role. Assessment still does not
decide whether the PR may merge.
The canonical `ReviewProjection` then exposes one verification workspace for
R/G and T/CC subjects. Matrix rows and evidence-inspector records reference the
same selected relations, bindings, evidence, diagnostics, and structural graph;
the projection does not perform another assessment.
The HTML consumes that workspace through one verification accordion, the
projection-owned structural graph, and a collapsed Evidence Appendix. This
replaces the former Canonical Change Map and repeated per-R/G review cards
without creating a second presentation truth. T/CC structural focus remains
unavailable until canonical subject selection and bounded closure project it;
the renderer never manufactures graph membership from aligned evidence alone.

The canonical stage map, ownership rules, and dependency direction are
documented in [`docs/architecture.md`](docs/architecture.md). Each stage also
keeps its local input/output contract beside its code.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pytest -q
prismcode review --fixture fixtures/pr574.json --output build/pr574.html
```

Open `build/pr574.html` in a browser.

### Evaluate retrieval offline

Run the golden suite without GitHub, Codegraph, or model credentials:

```bash
prismcode evaluate \
  --suite fixtures/evaluation-suite.json \
  --json-output build/evaluation.json \
  --markdown-output build/evaluation.md
```

The command returns non-zero when configured thresholds fail. See
[`docs/evaluation.md`](docs/evaluation.md) for the versioned contracts, metrics,
and safety boundary.

### Run bounded LLM shadow selection

Shadow selection is opt-in and never changes deterministic review assessments:

```bash
export OPENAI_API_KEY=...
export PRISMCODE_LLM_MODEL=...
# Optional OpenAI-compatible HTTPS API root; defaults to OpenAI.
export OPENAI_BASE_URL=https://api.openai.com/v1

prismcode review \
  --repo owner/repository \
  --pr 123 \
  --llm-shadow \
  --output build/pr-123.html
```

PrismCode sends only bounded canonical evidence candidates through the
Chat Completions API with strict Structured Outputs, `store: false`, no tools,
and a 40-candidate request limit plus three-request review limit. It records one
typed observation per claim, including the bounded request, admission and
execution fate, validated selection divergence, usage, failures, deferrals,
and coverage limits, in
`build/pr-123.html.llm-shadow.json`; the Brief header shows only the execution
state. Missing configuration records `unavailable`; provider or validation
failure records `partial` or `failed`; deterministic HTML still succeeds.
Omitting `--llm-shadow` performs no provider call and writes no shadow artifact.

For an exact offline transport replay, add
`--llm-shadow-replay path/to/exact-request-replay.json`; replay explicitly
overrides live configuration.

### Review a live GitHub pull request

#### Basic review from any directory

This always collects the PR, its Development-linked Issue, changed-file
patches, and CI observations from GitHub:

```bash
export GITHUB_TOKEN=...
prismcode review \
  --repo owner/repository \
  --pr 123 \
  --repo-root /path/to/local/repository \
  --output build/pr-123.html
```

For every live structure-aware review, `--repo-root` is only a local Git object
and worktree source. It does not need to be checked out at either PR revision
and its `.codegraph` directory is never read or modified. PrismCode creates
private detached worktrees at the exact GitHub head and base SHAs, initializes
one Codegraph index in each, runs structural mapping and head guardrail scans,
then removes both worktrees and indexes after success or failure. The source
repository must already contain both commit objects. This mode requires either
a `codegraph` executable or `npx` on `PATH`.
The bundled review workflow checks out full history so both GitHub PR revision
objects are available; other CI integrations must provision the same input.

Use `--no-structural-graph` for the explicit dependency-free path. PrismCode
still creates and removes an exact temporary head worktree for bounded
guardrail scans, but it does not initialize Codegraph or create a base
worktree:

```bash
prismcode review \
  --repo owner/repository \
  --pr 123 \
  --repo-root /path/to/local/repository \
  --no-structural-graph \
  --output build/pr-123.html
```

When the checkout revision, indexed content hashes, and PR head all match,
PrismCode maps exact added hunk lines to Codegraph symbols and records
bounded structural paths:

```text
Structural mapping: Codegraph available · 4/4 hunks mapped to 3 symbols · 12 bounded paths · base unavailable · uncovered change relations retained
```

Path expansion starts only from exact changed symbols and follows an explicit
relation allowlist in both directions. A deterministic depth-phased scheduler
completes shallower relations before deeper expansion and shares each depth
fairly between seeds while enforcing per-seed and review-level node/path
limits. A high-fanout seed therefore cannot consume the review budget before
later changed symbols are inspected, and deeper paths cannot displace eligible
direct relations. The provider records complete or truncated traversal
coverage for every seed. An exact symbol replaces the corresponding
changed-hunk fallback and remains a structural node even when no path is
selected. Its hunks, lines, files, and GitHub links remain provenance rather
than parallel evidence. Unmapped hunks remain canonical evidence. File
fallback is used only when GitHub supplies no parseable hunk.

Codegraph `contains` edges are collected separately as bounded structural
ownership facts for observed symbols. They preserve canonical ancestry such as
file → class → method without becoming runtime/test paths or consuming path
budgets. The catalog normalizes revision provenance and converges it into one
review-level retained/added/removed ownership identity when opposite-revision
coverage makes that conclusion safe. Incomplete coverage remains provenance
plus a diagnostic. The shared review graph renders that canonical hierarchy
beside executable relations and lets reviewers hide its ownership-only context
without changing graph membership. Nested containers and semantic zoom remain
future presentation work.

The CLI may run from anywhere. The supplied local repository may be on another
branch or have uncommitted work because analysis never reads that working tree;
all review facts come from the private exact-revision roots. Guardrail and
removal plans own canonical target predicates with optional path scopes; the
scanner inspects each target only inside its declared scope under
explicit file, byte, and match limits and reports per-surface coverage. It
consumes the typed selectors produced by the one-pass PR semantics stage rather
than reparsing normalized claim prose, and scans only tracked head files,
excluding untracked checkout content and
symlink targets, and refuses a tracked working tree that differs from HEAD.
Path, file-content, and lexical symbol-name coverage are recorded separately;
truncation retains the exact boundary kind, limit, and observed count. A
zero-match observation is never presented as guardrail satisfaction or
repository-wide absence. A scoped removal requires an exact target and complete
Base/Head observations; the continued existence of the containing file does not
contradict removal of a symbol inside it.

Use `--verbose` for individual structural diagnostics, or
`--no-structural-graph` to skip the probe explicitly. Missing, stale, partial,
invalid, or unreadable indexes never prevent report generation.

For a private repository, `GITHUB_TOKEN` must be able to read the repository.
Public repositories may work without a token, subject to GitHub's
unauthenticated rate limits. Use `--github-token-env OTHER_ENV_NAME` to select
another environment variable. Use `--github-api-url` for GitHub Enterprise
Server. When a token is present, an Enterprise host must also be explicitly
trusted with `--trusted-github-api-host HOST`; only HTTPS URLs are accepted.

The adapter records explicit diagnostics when:

- GitHub omits a line-level patch for a changed file;
- `--max-files` prevents complete changed-file collection.
- no Development-linked Issue is present;
- no current-head Check Run or commit status exists, or the head SHA is unavailable.

It never converts missing patch, test, or execution evidence into a successful verification claim.

### Automated review workflow

`.github/workflows/review.yml` runs automatically for pull requests in this repository and can
also be started with **Actions → PrismCode review → Run workflow** for any readable repository
and PR number. Each run exposes a report link in the job summary and retains the HTML as a
GitHub Actions artifact for 14 days.

The built-in `GITHUB_TOKEN` covers pull requests in this repository. To review another private
repository, configure a `PRISMCODE_GITHUB_TOKEN` Actions secret with read access to that target.
Missing links, patches, head SHAs, checks, and statuses remain explicit rather
than being treated as passing evidence.

## Architectural boundary

```text
private managed services
        │ implement public protocols / call public core
        ▼
PrismCode open core
ReviewSourcePacket → canonical evidence → typed routing → convergence → ReviewProjection → renderer
```

The open core must remain independently installable and runnable. Optional hosted capabilities should integrate through public protocols or an explicit HTTPS backend, never through an unavailable private import.

## Evidence semantics

The report labels evidence granularity (`CHANGED HUNK`, exact symbol,
`FILE FALLBACK`, execution observation) and explains retrieval relevance. It
does not convert a lexical or structural relationship into a review conclusion.

## Security note

Generated HTML only creates hyperlinks for absolute `http` and `https` URLs. Tokens are read from environment variables and are not stored in review metadata or generated output. A token is never sent to a custom API host unless that host is explicitly trusted.

## License

No open-source license has been selected yet. The repository remains private while licensing, contributor terms, and the public/private product boundary are reviewed.
