# Source provenance

The structural graph foundation is an open-core rewrite informed by structural
observation rules previously exercised in `interact-space/PrismCode`:

- `infrastructure/github/diff_observations.py` — unified-diff hunk line tracking.
- `prismcode/span_matching.py` — repository-path and line-span matching rules.
- `prismcode/detection/adapters/codegraph_context.py` — separation between
  structural observations and product conclusions.
- `prismcode/detection/adapters/codegraph_runtime.py` — read-only Codegraph
  SQLite schema discovery.

The implementation in this repository uses the public
`StructuralGraphProvider` contract and was rewritten for the standalone
requirement-first pipeline. It does not import Workspace, Change Unit,
semantic-spine, persistence, webhook, publisher, or other private runtime
packages from `interact-space/PrismCode`.
