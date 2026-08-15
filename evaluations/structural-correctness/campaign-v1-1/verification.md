# Campaign v1.1 independent verification record

## Method

The v1 proposed labels supplied the initial candidate decisions. A separate
source-review pass loaded only each v3 packet, its proposal, the exact GitHub PR
contract, and the base-to-head diff. RepoDelta observation JSON and comparison
HTML remained unopened until all verified reference artifacts were written.

The review checked subject meaning, direct/context roles, changed operation,
file ownership, exact relation relevance, relation endpoint closure, unresolved
decisions, revision identity, and per-seed coverage. Machine checks then
rejected unknown identities, invalid roles, relation-without-endpoint decisions,
and verification records without evidence or system-under-test isolation.

## Proposal correction discovered before verification

The v1 proposals selected some exact relations without admitting both endpoint
nodes. The affected proposals were corrected before their new digest was
verified: PR #208 added `build_review_projection`; PR #250 added omitted call
endpoints including `_request_json`, `push_head`, and `create_app_jwt`; PR #235
added retained `isolated_review_roots` context; and PR #267 added
`project_structural_overview`. No observation was consulted to find or correct
these omissions.

## Per-PR evidence

- **PR #208:** exact diff for canonical backbone seed derivation and its sink
  tests; direct changed anchors, retained `_change_backbone` context, and call
  endpoints agree with the authored membership contract.
- **PR #238:** exact diff for state predicate extraction, revision expectation,
  assessment preservation, and base/head counterexample tests; resolved empty
  guardrails remain absence claims rather than invented structure.
- **PR #245:** exact PR metadata and README-only file list; the packet has no
  structural candidates or subjects, so the empty reference is resolved within
  that bounded surface.
- **PR #250:** exact App-submission contract, changed-file list, added symbols,
  credential tests, and canonical call relations; absence guardrails remain
  empty while implementation and verification subjects select their concrete
  functions and tests.
- **PR #235:** exact remote-workspace contract, changed-file list, workspace and
  CLI symbols, retained lifecycle context, revision/authentication tests, and
  call relations.
- **PR #262:** exact single-inspector presentation transition, renderer symbols,
  source/assessment preservation tests, and renderer call relations; excluded
  semantic changes remain empty.
- **PR #267:** exact canonical-overview contract, typed producer/consumer
  symbols, bridge/context counterexamples, validation tests, and projection call
  relations.
- **PR #240:** exact repository-wide identity migration contract and changed-file
  inventory. Narrow CLI/configuration/gate decisions are resolved; the three
  repository-wide mechanical memberships remain unresolved because the bounded
  packet cannot justify an exhaustive symbol-level selection.

Evidence identities and proposal digests are also embedded in each verified
reference artifact. Coverage limitations are reported separately from reference
authority and do not become correctness claims.
