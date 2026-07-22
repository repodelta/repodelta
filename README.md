# PrismCode

PrismCode generates requirement-first, evidence-linked pull request review briefs.

This repository is the standalone open-core implementation. It does not import company-private packages. The fixture workflow requires no network, model API, or company credentials; the GitHub workflow talks only to the configured GitHub API.

## Current scope

The open core provides:

- public contracts for requirements, evidence, verification, gaps, changed files, diagnostics, and provenance;
- offline JSON fixture ingestion;
- live GitHub pull request metadata and changed-file ingestion;
- conservative requirement extraction from explicit Markdown checklists and requirement-like sections;
- a deterministic analyzer contract;
- a requirement-first static HTML renderer;
- a local CLI;
- clean-install CI with network-free tests.

The GitHub adapter intentionally does **not** infer requirement-to-code alignment. Requirements collected from a live pull request remain `unresolved` until requirement-specific implementation and verification evidence is supplied by a fixture or a future semantic provider.

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

The token is read from `GITHUB_TOKEN` by default. Use `--github-token-env OTHER_ENV_NAME` to select another environment variable. Use `--github-api-url` for GitHub Enterprise Server.

The adapter records explicit diagnostics when:

- no checklist or requirement-section bullets exist and the PR title is used as a fallback;
- GitHub omits a line-level patch for a changed file;
- `--max-files` prevents complete changed-file collection.

It never converts missing patch, test, or execution evidence into a successful verification claim.

## Architectural boundary

```text
private managed services
        │ implement public protocols / call public core
        ▼
PrismCode open core
contracts → adapters → analyzer → renderer → HTML
```

The open core must remain independently installable and runnable. Optional hosted capabilities should integrate through public protocols or an explicit HTTPS backend, never through an unavailable private import.

## Status semantics

- `verified`: implementation and relevant verification evidence are present.
- `partial`: some evidence exists, but a requirement is not fully demonstrated.
- `unresolved`: available evidence is insufficient for a conclusion.
- `not_implemented`: evidence indicates that the requirement is absent.

## Security note

Generated HTML only creates hyperlinks for absolute `http` and `https` URLs. Tokens are read from environment variables and are not stored in review metadata or generated output.

## License

No open-source license has been selected yet. The repository remains private while licensing, contributor terms, and the public/private product boundary are reviewed.
