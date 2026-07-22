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
- separate public contracts for source requirements, evidence hints, and analysis-owned assessments;
- offline JSON fixture ingestion;
- live GitHub pull request metadata and changed-file ingestion;
- GitHub GraphQL Development-link Issue ingestion plus current-head REST check-run and commit-status observations;
- conservative requirement extraction in the analysis layer from explicit Markdown requirement sections;
- a deterministic analyzer that owns implementation and verification status;
- a requirement-first static HTML renderer;
- a local CLI;
- an Actions workflow for automatic PR reports and manually targeted reviews;
- clean-install CI with network-free tests.

The GitHub adapter intentionally emits source facts only. Linked Issues come from GitHub's `closingIssuesReferences` GraphQL field, not Issue numbers typed into PR prose. The analyzer prefers linked-Issue acceptance criteria, assigns delivery requirements `R1`, `R2`, ... and scope guardrails `G1`, `G2`, ..., then combines diff evidence with exact verification observation IDs. Requirements without requirement-specific execution remain verification `not_observed`, even when generic CI is green.

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

For a private repository, export a token that can read the repository. Public repositories may work without a token, subject to GitHub's unauthenticated rate limits.

```bash
export GITHUB_TOKEN=...
prismcode review \
  --repo owner/repository \
  --pr 123 \
  --output build/pr-123.html
```

The token is read from `GITHUB_TOKEN` by default. Use `--github-token-env OTHER_ENV_NAME` to select another environment variable. Use `--github-api-url` for GitHub Enterprise Server. When a token is present, an Enterprise host must also be explicitly trusted with `--trusted-github-api-host HOST`; only HTTPS URLs are accepted.

The adapter records explicit diagnostics when:

- GitHub omits a line-level patch for a changed file;
- `--max-files` prevents complete changed-file collection.
- no Development-linked Issue is present;
- no current-head Check Run or commit status exists, or the head SHA is unavailable.

It never converts missing patch, test, or execution evidence into a successful verification claim.

### Team trial workflow

`.github/workflows/review.yml` runs automatically for pull requests in this repository and can
also be started with **Actions → PrismCode review → Run workflow** for any readable repository
and PR number. Each run exposes a report link in the job summary and retains the HTML as a
GitHub Actions artifact for 14 days.

The built-in `GITHUB_TOKEN` covers pull requests in this repository. To review another private
repository, configure a `PRISMCODE_GITHUB_TOKEN` Actions secret with read access to that target.
The report includes a **Data sources & coverage** section so missing links, patches, head SHAs,
checks, and statuses remain visible to reviewers.

## Architectural boundary

```text
private managed services
        │ implement public protocols / call public core
        ▼
PrismCode open core
ReviewSourcePacket → criteria/evidence hints → analyzer → ReviewBrief → renderer
```

The open core must remain independently installable and runnable. Optional hosted capabilities should integrate through public protocols or an explicit HTTPS backend, never through an unavailable private import.

## Assessment semantics

Implementation and verification are separate axes:

- implementation: `observed`, `partial`, `not_observed`, `contradicted`;
- verification: `passed`, `failed`, `pending`, `not_observed`, `stale`, `manual_required`.

Adapters and providers cannot set these values. Only the deterministic analyzer produces assessments.

## Security note

Generated HTML only creates hyperlinks for absolute `http` and `https` URLs. Tokens are read from environment variables and are not stored in review metadata or generated output. A token is never sent to a custom API host unless that host is explicitly trusted.

## License

No open-source license has been selected yet. The repository remains private while licensing, contributor terms, and the public/private product boundary are reviewed.
