# Open-core boundaries

PrismCode has one canonical review path:

```text
fixture or GitHub
  -> conclusion-free ReviewSourcePacket
       -> linked Issue/Ticket + PR + changed files + CI/Actions observations
  -> parse unified-diff hunks
  -> optional StructuralGraphProvider
       -> exact changed-hunk / symbol-span overlaps
       -> bounded direction-aware paths to unchanged runtime/test neighbors
  -> canonical EvidenceCatalog
       -> exact symbol for each mapped hunk
       -> changed-hunk evidence for each unmapped hunk
       -> changed-file fallback only when no parseable hunk exists
       -> bounded paths + CI/runtime observations
  -> one-pass semantic extraction
       -> obligations and guardrails (R/G)
       -> objectives (O), scope context (S)
       -> implementation/boundary (C), baseline (B), verification (V) claims
       -> intent (I)
  -> deterministic CandidateBindingSet
       -> R/G/O/S/C/B/V -> evidence candidates
       -> R/G -> C candidates
  -> ReviewBrief
  -> HTML renderer
```

## Authority rules

1. Adapters collect facts; they never emit review conclusions.
2. `Requirement` is a provenance-bearing source assertion, not an assessment.
3. `EvidenceCatalog` is the only evidence store downstream of ingestion.
4. `CandidateBindingSet` records retrieval relevance and its reasons. It never
   means implemented, verified, satisfied, or in scope.
5. Renderers project the brief and never infer or upgrade a conclusion.
6. Structural providers return repository facts and diagnostics only.

## Semantic authority

Each Issue or PR Markdown body is parsed once into canonical
`ReviewStatement`s:

1. A selected linked Issue's Acceptance Criteria, Requirements, Definition of
   Done, or Success Criteria are authoritative obligations.
2. Only when no Issue obligation exists may the corresponding explicit
   PR-description sections become provisional obligations.
3. Goals and Objectives are objective retrieval context.
4. Scope and In scope are context, never obligations.
5. Out of scope and Boundary from a linked Issue are authoritative
   guardrails. The same headings in a PR are boundary claims, because the
   author cannot redefine the Issue contract by describing the implementation.
6. Summary, Implementation, Changes, What Changed, and Approach are
   implementation claims. Baseline/Results and Verification/Testing are typed
   baseline and verification claims.
7. The PR introduction and title are intent only.

Deliverables use stable IDs (`R1`, `R2`, ...), negative scope constraints use
`G1`, objectives use `O1`, scope uses `S1`, implementation and PR boundary
claims use `C1`, baselines use `B1`, and verification claims use `V1`. Role,
purpose, and authority are separate fields: for example, both `C1` and `V1`
are claims, but their purposes differ. If no explicit obligation exists, the
renderer reports the missing acceptance basis.

The linked-Issue relation comes from GitHub GraphQL
`PullRequest.closingIssuesReferences`; PR prose is not parsed to invent Issue
links. Changed files and patches, check runs, and commit statuses come from
GitHub REST endpoints.

## Structural graph boundary

`StructuralGraphProvider` is the read-only structure port.
`CodegraphProvider` reads a repository-local `.codegraph/codegraph.db` in
SQLite read-only mode. It validates the schema, compares indexed file hashes
with the checkout, and for live reviews verifies that the checkout revision
matches the PR head SHA.

Only exact changed lines from unified-diff hunks are joined to symbol spans.
The narrowest containing symbol wins. Module-level changes may map to the
indexed file symbol, which owns Codegraph import edges. Exact changed symbols
are the only traversal seeds.

Traversal is deterministic, direction-aware, and bounded to three hops, 80
unique nodes, and 120 paths by default. Eligible edges are `calls`, `imports`,
`instantiates`, `references`, and `extends`; container edges are excluded.
Each path retains direction, runtime/test/mixed classification, and head-line
sources.

Missing patches, stale or missing indexes, unindexed code, unmatched lines,
and deletion-only hunks remain explicit diagnostics. A graph failure never
prevents report generation.

## Canonical evidence and fallback

Each parseable changed hunk has exactly one canonical representation:

- when Codegraph maps it, the exact symbol represents it;
- otherwise, a `changed_hunk` item retains its path, ranges, bounded patch
  excerpt, and GitHub source;
- only an absent or unparsable patch produces a `changed_file` fallback.

This replacement rule prevents `CHANGED FILE`, `CHANGED HUNK`, and exact symbol
records from competing as parallel truths for the same diff. Documentation
hunks remain evidence with document classification; they are not forced into
code symbols.

Every `EvidenceItem` has a stable ID, kind, summary, classification, changed
flag, sources, structural-path IDs, and fact-only metadata. Duplicate symbols
and paths merge by identity.

## Candidate binding

`CandidateBindingSet` contains:

- `statement_evidence` relations from R/G/O/S/C/B/V to canonical evidence;
- `requirement_claim` relations from R/G to PR-authored C statements.

Direct retrieval uses one tokenizer over statement text and evidence content,
including changed-hunk excerpts. A matched exact symbol may expand through its
bounded Codegraph paths. Requirements can also inherit evidence candidates
through aligned claims, while direct R/G-to-evidence retrieval remains
available.

Each binding records feature-level reasons, weights, matched terms, stable IDs,
and relevant structural path IDs. Deterministic per-statement and total budgets
bound output. Coverage reports statements without candidates and evidence not
reached by any statement.

## Packet revisions

`packet_revision` is a deterministic SHA-256 consistency digest over semantic
packet content. It detects accidental content/revision mismatch; it is not a
signature or proof of GitHub origin.

## Private-code boundary

The open core must not import Workspace, Change Unit, semantic-spine,
persistence, webhook, or publisher packages from `interact-space/PrismCode`.
Reusable rules and test vectors may be adapted only through public contracts
and recorded provenance.
