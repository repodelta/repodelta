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
- conclusion-free requirements plus one canonical evidence and candidate-binding graph;
- offline JSON fixture ingestion;
- live GitHub pull request metadata and changed-file ingestion;
- GitHub GraphQL Development-link Issue ingestion plus current-head REST check-run and commit-status observations;
- one-pass semantic extraction with explicit authority for Issue/PR obligations,
  objectives, claims, and intent;
- a deterministic analyzer that builds explainable evidence candidates without declaring implementation or verification status;
- a requirement-first static HTML renderer;
- a local CLI;
- optional repository-local Codegraph hunk-to-symbol mapping with explicit
  availability and freshness diagnostics;
- bounded Codegraph paths from changed symbols to unchanged runtime/test
  neighbors;
- one canonical, deterministic evidence catalog for changed hunks, exact
  symbols, bounded paths, file fallbacks, and CI/runtime observations;
- explainable deterministic R/G/O/C-to-evidence and R/G-to-claim candidates;
- an R-first consistency view with claim/evidence candidates, binding basis,
  source links, and vertically aggregated coverage gaps;
- an Actions workflow for automatic PR reports and manually targeted reviews;
- clean-install CI with network-free tests.

The GitHub adapter intentionally emits source facts only. Linked Issues come
from GitHub's `closingIssuesReferences` GraphQL field, not Issue numbers typed
into PR prose. The analyzer applies one authority policy:

- linked-Issue Acceptance Criteria, Requirements, and Definition of Done become
  authoritative `R1`, `R2`, ... obligations and `G1`, `G2`, ... guardrails;
- without a selected linked Issue, the same explicit PR-description sections
  become provisional obligations;
- Goals/Objectives become `O1`, `O2`, ... retrieval context;
- Summary/Implementation/Changes become `C1`, `C2`, ... PR-authored claims;
- the PR introduction or title is intent only and is never promoted to `R1`.

When no explicit acceptance criteria are present, the report says so instead
of manufacturing a requirement from the PR title. Candidate relevance is never
presented as implementation, verification, or acceptance.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pytest -q
prismcode review --fixture fixtures/pr574.json --output build/pr574.html
```

Open `build/pr574.html` in a browser.

### Review a live GitHub pull request

#### Basic review from any directory

This always collects the PR, its Development-linked Issue, changed-file
patches, and CI observations from GitHub:

```bash
export GITHUB_TOKEN=...
prismcode review \
  --repo owner/repository \
  --pr 123 \
  --output build/pr-123.html
```

PrismCode also probes the current directory (`.`) for
`.codegraph/codegraph.db`. If the current directory is not the analyzed PR's
exact head checkout, or its index is unavailable or stale, the report is still
generated from canonical changed-hunk evidence:

```text
Structural mapping: skipped · Codegraph index not found · changed-hunk fallback used
```

#### Structure-aware review from the PR checkout

Run the same command from a checkout whose `HEAD` is the PR head. The
repository-local Codegraph index must be synchronized with that checkout:

```bash
cd /path/to/repository-at-pr-head
# First index only: npx @colbymchenry/codegraph init -i
npx @colbymchenry/codegraph sync

prismcode review \
  --repo owner/repository \
  --pr 123 \
  --output build/pr-123.html
```

When the checkout revision, indexed content hashes, and PR head all match,
PrismCode maps exact changed hunk lines to Codegraph symbols and records
bounded structural paths:

```text
Structural mapping: Codegraph available · 4/4 hunks mapped to 3 symbols · 12 bounded paths · unmapped hunks retained
```

Path expansion starts only from exact changed symbols, follows an explicit
relation allowlist in both directions, and stops at deterministic three-hop,
node, and path budgets. An exact symbol replaces the corresponding changed-hunk
fallback; unmapped hunks remain canonical evidence. File fallback is used only
when GitHub supplies no parseable hunk.

#### Structure-aware review using another checkout

The CLI may run from anywhere. Use `--repo-root` to point it at the checkout
and index belonging to the analyzed PR:

```bash
prismcode review \
  --repo owner/repository \
  --pr 123 \
  --repo-root /path/to/repository-at-pr-head \
  --output build/pr-123.html
```

This is also required when reviewing a historical or different PR while the
current directory is checked out at another commit. `--repo-root` does not
select or change a Git revision: the supplied checkout must already be at the
PR's head SHA, and PrismCode verifies that before using its index.

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
ReviewSourcePacket → canonical evidence → candidate bindings → ReviewBrief → renderer
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
