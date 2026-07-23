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
  -> deterministic criteria extraction + optional EvidenceHints
  -> DeterministicAnalyzer
  -> ReviewBrief
  -> HTML renderer
```

## Authority rules

1. Adapters collect facts. `ReviewSourcePacket` contains source records, changed files,
   revisions, collection diagnostics, and metadata; it contains no review conclusion.
2. `Requirement` is a source assertion. It cannot contain implementation, verification,
   gaps, or status.
3. Fixture or provider evidence enters through `EvidenceHint`. A hint identifies evidence
   and provenance but cannot declare an implementation status.
4. `DeterministicAnalyzer` is the only status authority. It emits separate implementation
   and verification assessments.
5. Renderers consume `ReviewBrief` and never infer or upgrade an assessment.
6. Structural graph providers return repository facts and diagnostics only. A
   hunk-symbol overlap is not, by itself, an implementation conclusion.

Acceptance criteria from an explicit linked Issue are primary. Deliverables receive stable
display IDs (`R1`, `R2`, ...); negative scope constraints are separated as guardrails
(`G1`, `G2`, ...). A verification result can pass a requirement only when an evidence hint
names that exact observation, it belongs to the analyzed head, it succeeded, and assertion
coverage is explicitly adequate. Generic green CI never verifies every requirement.

The linked-Issue relation is collected from GitHub GraphQL
`PullRequest.closingIssuesReferences`. PR body text is not parsed to invent Issue links.
Changed files and patches, check runs, and commit statuses come from GitHub REST endpoints.

## Structural graph boundary

`StructuralGraphProvider` is the open-core port for read-only code structure.
`CodegraphProvider` is the first adapter and reads a repository-local
`.codegraph/codegraph.db` in SQLite read-only mode. It verifies the expected
schema and compares indexed content hashes with the current checkout before
mapping evidence.

Only exact new-file changed lines from GitHub unified-diff hunks are joined to
symbol `[start_line, end_line]` spans. When symbols are nested, the narrowest
symbol containing each changed line is selected. Missing patches, missing or
stale indexes, unindexed files, unmatched lines, and deletion-only hunks are
reported explicitly. Deletion-only mapping requires a future base-revision
index and is never guessed from the head index.

This layer does not traverse callers/callees, bind symbols to requirements, or
call an LLM. Those remain separate follow-up stages so structural observations
cannot silently become review conclusions.

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
