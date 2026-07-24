# Open-core boundaries

PrismCode has one canonical path:

```text
fixture or GitHub
  -> ReviewSourcePacket
       -> linked Issue/Ticket + PR + changed files + CI/Actions observations
  -> optional StructuralGraphProvider
       -> unified-diff hunks + exact changed lines
       -> repository-local graph index status
       -> changed hunk / symbol-span overlaps
       -> bounded, direction-aware structural paths
  -> canonical EvidenceCatalog
       -> changed files + changed/unchanged symbols
       -> structural paths + CI/runtime observations
  -> one-pass semantic extraction + optional EvidenceHints
       -> Issue/PR obligations (R/G)
       -> objectives (O), claims (C), intent (I)
  -> deterministic CandidateBindingSet
       -> R/G/O/C -> Evidence candidates
       -> R/G -> C candidates
  -> DeterministicAnalyzer
  -> ReviewBrief
  -> HTML renderer
```

## Authority rules

1. Adapters collect facts. `ReviewSourcePacket` contains source records, changed files,
   revisions, collection diagnostics, and metadata; it contains no review conclusion.
2. `Requirement` is a source assertion. It cannot contain implementation, verification,
   gaps, or status.
3. Source and provider facts are normalized once into an ID-addressed
   `EvidenceCatalog`. `EvidenceHint` contains evidence IDs and provenance; it
   cannot copy evidence content or declare an implementation status.
4. `DeterministicAnalyzer` is the only status authority. It emits separate implementation
   and verification assessments.
5. Renderers consume `ReviewBrief` and never infer or upgrade an assessment.
6. Structural graph providers return repository facts and diagnostics only. A
   hunk-symbol overlap is not, by itself, an implementation conclusion.

## Semantic authority

Each Issue or PR Markdown body is parsed once into the canonical
`ReviewStatement` model. A statement carries its role, authority, exact section
source, and line. The analyzer applies the hierarchy rather than maintaining
separate parsers or copies:

1. A selected linked Issue's Acceptance Criteria, Requirements, Definition of
   Done, or Success Criteria are authoritative obligations.
2. Only when no Issue obligation exists may the same explicit PR-description
   sections become provisional obligations.
3. Goals and Objectives are retrieval context, not acceptance criteria.
4. Summary, Implementation, Changes, What Changed, and Approach are
   PR-authored claims to be checked against evidence.
5. The PR introduction or title is intent only. A title is never manufactured
   into `R1`.

Deliverables receive stable display IDs (`R1`, `R2`, ...); negative scope
constraints are separated as guardrails (`G1`, `G2`, ...), objectives use
`O1`, and claims use `C1`. When no explicit obligation exists, assessments are
empty and the renderer reports the missing acceptance basis. A verification
result can pass a requirement only when an evidence hint names that exact
observation, it belongs to the analyzed head, it succeeded, and assertion
coverage is explicitly adequate. Generic green CI never verifies every
requirement.

The linked-Issue relation is collected from GitHub GraphQL
`PullRequest.closingIssuesReferences`. PR body text is not parsed to invent Issue links.
Changed files and patches, check runs, and commit statuses come from GitHub REST endpoints.

## Structural graph boundary

`StructuralGraphProvider` is the open-core port for read-only code structure.
`CodegraphProvider` is the first adapter and reads a repository-local
`.codegraph/codegraph.db` in SQLite read-only mode. It verifies the expected
schema and compares indexed content hashes with the current checkout before
mapping evidence. For live GitHub reviews, the checkout revision must also
match the analyzed PR head SHA.

Only exact new-file changed lines from GitHub unified-diff hunks are joined to
symbol `[start_line, end_line]` spans. When symbols are nested, the narrowest
symbol containing each changed line is selected. Module-level changes such as
imports fall back to the indexed file symbol, which owns Codegraph's import
edges. Documentation files are reported as not applicable and do not reduce
code-structure coverage. Missing patches, missing or stale indexes, unindexed
code files, unmatched lines, and deletion-only hunks are reported explicitly.
Deletion-only mapping requires a future base-revision index and is never
guessed from the head index.

Exact changed symbols are the only traversal seeds. `CodegraphProvider` loads
complete unchanged neighbor symbols with a direction-aware breadth-first
search. Traversal is deterministic and bounded to three hops, 80 unique nodes,
and 120 paths by default. Only `calls`, `imports`, `instantiates`, `references`,
and `extends` edges are eligible; container edges such as `contains` are
excluded to prevent file-wide fan-out. Each path records incoming/outgoing
direction, runtime/test/mixed classification, and head-revision GitHub line
sources.

This layer does not bind paths to requirements or call an LLM. Paths remain
candidate repository facts, so structural observations cannot silently become
review conclusions.

## Canonical evidence

`EvidenceCatalog` is the only downstream evidence store. It assigns
deterministic IDs to changed files, exact symbols, unchanged structural
neighbors, bounded paths, and verification observations. Repeated hunks,
symbols, files, and paths merge by identity; sources and structural-path
references are unioned rather than copied into parallel records.

Each `EvidenceItem` records:

- stable ID, kind, summary, and code/test/document/CI/runtime/mixed
  classification;
- whether the underlying item changed in the PR;
- exact source links and any bounded structural path IDs;
- kind-specific source metadata without an analysis conclusion.

`EvidenceHint` and assessments resolve catalog IDs. Legacy fixture
implementation objects are accepted only at the fixture adapter boundary,
converted to provided evidence with deterministic IDs, and then referenced by
ID. The catalog does not bind evidence to R/G/O/C; candidate binding remains a
separate follow-up stage.

## Candidate binding

`CandidateBindingSet` connects semantic statements to the evidence catalog
without changing either source. It emits two many-to-many relation kinds:

- `statement_evidence` for R/G/O/C to canonical evidence;
- `requirement_claim` for R/G to PR-authored C statements.

Direct lexical candidates share one tokenizer with the legacy deterministic
assessment hints. Every binding records feature-level reasons, integer weights,
matched terms, stable IDs, and any bounded structural path IDs. A lexical
symbol match may expand to symbols on the same bounded Codegraph path. A
requirement may also receive a candidate through an aligned claim, but claims
are optional: direct R/G-to-evidence retrieval always remains available.

Candidate generation has deterministic per-statement/per-kind and total
budgets. Coverage records requirements without evidence candidates, claims
without requirement candidates, and evidence not reached by any statement.
`candidate_support` means retrieval relevance only; it never means implemented,
verified, satisfied, or in scope. The analyzer remains the sole status
authority.

The HTML consistency report is a projection of this data. Requirement cards
retain their existing implementation/test/CI status chips and add a separate
candidate area for related claims, canonical evidence, exact source links,
retrieval scores, and binding reasons. Scores are labeled as relevance and are
never rendered as confidence or acceptance status. Candidate gaps are
aggregated vertically in Needs attention, including requirements without claim
or evidence candidates, claims without requirement or evidence candidates,
changed evidence without statement candidates, and budget diagnostics.
Guardrails remain aggregated rather than becoming a second per-item report.

The `review` CLI enables this read-only mapping by default, using `--repo-root`
(the current directory unless specified) to locate the target checkout. The
result travels through `AnalysisInput` into `ReviewBrief` for downstream stages,
while the current lexical requirement binding remains authoritative. The CLI
prints one structural-coverage line to stderr. `--no-structural-graph` disables
the probe explicitly; missing, stale, partial, invalid, and unreadable indexes
degrade without failing report generation.

## Packet revisions

`packet_revision` is a deterministic SHA-256 consistency digest over the semantic packet
content. It detects accidental corruption or content/revision mismatch. It is not a
signature and does not prove GitHub origin or resist a party that can rewrite both content
and digest.

## Private-code boundary

The open core must not import Workspace, Change Unit, semantic-spine, persistence, webhook,
or publisher packages from `interact-space/PrismCode`. Reusable rules and test vectors may
be adapted only through public contracts and with source provenance recorded before public
release.
