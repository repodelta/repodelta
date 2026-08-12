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

## External runtime and APIs

The default live structural path invokes
[Codegraph](https://github.com/colbymchenry/codegraph) through either an
installed `codegraph` executable or the external npm package
[`@colbymchenry/codegraph`](https://www.npmjs.com/package/@colbymchenry/codegraph).
The unrelated `codegraph` distribution on PyPI is not a RepoDelta dependency.
Codegraph is MIT licensed and is not imported, vendored, or redistributed in
the RepoDelta Python package; RepoDelta consumes its temporary SQLite index
through the `StructuralGraphProvider` boundary.

GitHub REST and GitHub GraphQL are network APIs rather than bundled libraries.
RepoDelta uses Python's standard-library HTTP client for both. GraphQL is used
only to read the PR's Development-linked Issues; pull-request metadata,
patches, checks, and statuses come from REST endpoints.
