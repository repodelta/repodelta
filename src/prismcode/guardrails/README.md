# Guardrails

## Owns

Canonical executable scan plans compiled one-to-one from authoritative G
statements, plus deterministic bounded execution against a PR-head checkout.

## Input / output

Canonical guardrail `Requirement`s → `GuardrailScanPlanSet` → typed
`GuardrailScanResultSet`.

## Invariants

Each G owns exactly one stable plan targeting the PR head and repository root.
Every plan preserves the complete guardrail text and source provenance and
owns the only executable selector representation. The scanner consumes those
selectors without reinterpreting prose. Results identify revision, root,
per-surface coverage, safety limits, and candidate locations. File enumeration
uses the tracked head inventory and never inspects untracked checkout files or
symlink targets. A matching HEAD pointer is insufficient: tracked working-tree
content must also be clean before scanning begins. Path, file-content, and
lexical symbol-name surfaces are always present in result coverage.

## Must not

Associate changed code, normalize evidence, infer whether a candidate violates
a guardrail, or infer satisfaction, repository absence, verification, or
acceptance.

## Diagnostics

Reports missing executable selectors, stale or dirty checkouts, and exact
typed file/byte/match safety boundaries with limits and observed counts.

## Extension points

Additional scan surfaces plug into the same typed plan/result contract without
adding provider-local query semantics.
