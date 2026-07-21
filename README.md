# PrismCode

PrismCode generates requirement-first, evidence-linked pull request review briefs.

This repository is the standalone open-core implementation. It does not import company-private packages and its deterministic fixture workflow requires no network, model API, or company credentials.

## Current scope

The initial implementation provides:

- public review contracts for requirements, evidence, verification, gaps, and provenance;
- an offline JSON fixture adapter;
- a deterministic analyzer contract;
- a requirement-first static HTML renderer;
- a local CLI;
- a clean-install CI workflow.

GitHub PR ingestion and optional semantic-provider adapters are intentionally planned as follow-up work after the public contracts and renderer stabilize.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pytest -q
prismcode review --fixture fixtures/pr574.json --output build/pr574.html
```

Open `build/pr574.html` in a browser.

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

PrismCode does not convert missing execution evidence into a successful verification claim.

## License

No open-source license has been selected yet. The repository remains private while licensing, contributor terms, and the public/private product boundary are reviewed.
