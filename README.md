# PrismCode

PrismCode generates requirement-first, evidence-linked pull request review briefs.

This repository is the standalone open-core implementation. It does not import company-private packages. The fixture workflow requires no network, model API, or company credentials; the GitHub workflow talks only to the configured GitHub API.

## Current scope

The open core provides:

- a versioned, conclusion-free `ReviewSourcePacket` shared by fixture and GitHub ingestion;
- separate public contracts for source requirements, evidence hints, and analysis-owned assessments;
- offline JSON fixture ingestion;
- live GitHub pull request metadata and changed-file ingestion;
- conservative requirement extraction in the analysis layer from explicit Markdown requirement sections;
- a deterministic analyzer that owns implementation and verification status;
- a requirement-first static HTML renderer;
- a local CLI;
- clean-install CI with network-free tests.

The GitHub adapter intentionally emits source facts only. It cannot create requirements, evidence bindings, or final review status. Requirements without explicit evidence hints are reported as implementation and verification `not_observed`.

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

It never converts missing patch, test, or execution evidence into a successful verification claim.

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
