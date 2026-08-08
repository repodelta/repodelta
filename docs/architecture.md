# Open-core boundaries

PrismCode has one canonical review path:

```text
fixture or GitHub
  -> conclusion-free ReviewSourcePacket
       -> linked Issue/Ticket + PR + changed files + CI/Actions observations
  -> one-pass source semantics
       -> obligations and guardrails (R/G)
       -> objectives (O), scope context (S)
       -> implementation/boundary (C), baseline (B), verification (V) claims
       -> PR-authored typed transformation contract (T/CC)
       -> explicit target/path-scope predicates and missing-selector diagnostics
       -> intent (I)
  -> canonical closure scan planning
       -> one source-backed plan per eligible G/removal/negative CC
       -> typed base/head revision scope
       -> canonical transformation predicates reused without prose reparsing
  -> bounded closure scanning
       -> validated clean base/head checkouts
       -> scoped target path/content/symbol-name inspection
       -> typed file/byte/match safety limits
       -> revision-aware coverage, path profiles, and candidate locations
  -> one canonical DiffHunkCollection
  -> optional StructuralGraphProvider
       -> exact changed-hunk / symbol-span overlaps
       -> exact opposite-revision symbol counterparts
       -> bounded direction-aware paths to unchanged runtime/test neighbors
   -> canonical EvidenceCatalog
       -> exact symbol for each mapped hunk
       -> changed-hunk evidence for each unmapped hunk
       -> changed-file fallback only when no parseable hunk exists
        -> bounded paths + CI/runtime observations
   -> claim-independent observed transformation reconstruction
        -> changed anchors + uncovered diff facts
        -> Base/Head symbol, executable relation, and ownership topology
        -> replacement candidates + structural paths + verification observations
  -> canonical transformation structural subject selection
       -> explicit selector values only; never claim-prose inference
       -> exact Base/Head-aware symbol and repository-path matches
       -> complete match/no-match coverage without traversal or ranking
  -> bounded transformation structural closure
       -> already-collected paths reachable from selected subject identities
       -> whole path identities within three-hop and review safety limits
       -> canonical relation and bounded ownership change support
       -> explicit deferral diagnostics; no second provider traversal
  -> deterministic transformation alignment
       -> typed T/CC-to-observed-fact bindings with association reasons
       -> provider-owned T/CC-to-closure-fact bindings
       -> explicit no-eligible-fact / no-association coverage
  -> deterministic transformation assessment
       -> exactly one conservative status per typed T/CC claim
       -> complete revision-aware closure for absence/transition conclusions
       -> current-head verification identity for execution conclusions
       -> typed reasons and explicit uncertainty; never merge approval
  -> deterministic typed fact routing
       -> eligibility by fact profile and projection slot
       -> per-R/G claim, changed-anchor, runtime, test, CI, path, closure candidates
       -> complete typed relations with association reasons
  -> deterministic candidate convergence
       -> same-R/G, same-slot typed dominance
       -> claim/anchor/path bridge reachability
       -> bounded inspection, display selection, and explicit ambiguity
  -> bounded ReviewProjection
       -> one unified R/G + T/CC verification matrix
       -> one evidence-inspector record per subject
       -> shared structural graph overlays by canonical evidence identity
       -> one architectural change topology over the complete structural backbone
       -> path-bounded component classifications with exact internal and contextual
          canonical relation-group membership
       -> explicit classification authority and unclassified semantics
  -> canonical ReviewOverview
  -> ReviewBrief
  -> HTML / CLI presentation
       -> Structural delta graph cells display typed architectural classifications
       -> component focus consumes exact internal and contextual node/relation IDs
          from the architectural projection
       -> each Verification subject focuses the same graph through its canonical
          structural overlay and carries one projection-owned structural
          disposition when no graph focus applies; no second architectural
          subject overlay is produced
       -> renderer interaction focuses the one graph workspace and never
          reclassifies paths, relations, labels, or prose
```

An optional, dormant `llm` boundary derives one claim-kind-eligible candidate
set from canonical observed transformation facts. Deterministic assessment
evidence is retained first; remaining typed candidates are admitted in catalog
order under an explicit safety budget and coverage limits. The boundary may
then run a provider behind a transport-only port. The runner
validates cited canonical evidence identities, records deterministic-only,
shadow-only, and shared selections plus usage and latency, and isolates every
provider or validation failure from deterministic output. Its result carries
no formal assessment status and has no production consumer. A later integration
change must connect admitted requests to measured shadow execution.

Each stage owns one transformation. Typed models, boundary validation, and
counterfactual tests define its executable local contract; this document is the
single narrative map of how those stages compose. Stage-local prose must not
become a parallel authority that can drift from the production pipeline.

`pipeline.py` orchestrates these contracts without owning a semantic
transformation. A dependency-boundary test prevents downstream stages from
becoming alternate intake, classification, routing, or presentation paths.

## Authority rules

1. Adapters collect facts; they never emit review conclusions.
2. `Requirement` is a provenance-bearing source assertion, not an assessment.
3. `EvidenceCatalog` is the only evidence store downstream of ingestion.
4. `ProjectionCandidateSet` records typed retrieval relevance and its reasons.
   It never means implemented, verified, satisfied, or in scope.
5. Renderers project the brief and never infer or upgrade a conclusion.
6. Structural providers return repository facts and diagnostics only.
7. Closure scan plans own execution intent and target/path-scope predicates. Observed scans
   become revision-aware closure facts; neither plans nor zero-match observations prove
   satisfaction or repository-wide absence. A scope is never assessed as the
   target whose absence was claimed.
8. `TransformationAssessment` is the only authority for deterministic T/CC
   status. Missing association is unverified, local change is not global
   absence proof, and no status implies acceptance or mergeability.

## Semantic authority

Each Issue or PR Markdown body is parsed once into canonical
`ReviewStatement`s:

1. A selected linked Issue's Acceptance Criteria, Requirements, Definition of
   Done, or Success Criteria are authoritative obligations.
2. Only when no Issue obligation exists may the corresponding explicit
   PR-description sections become provisional obligations.
3. Common Goal, Objective, Aim, Purpose, Motivation, and Outcome heading
   variants normalize to objective retrieval context.
4. Common Scope, In Scope, Included Work, and Covered Area heading variants
   normalize to scope context, never obligations.
5. Out of scope and Boundary from a linked Issue are authoritative
   guardrails. The same headings in a PR are boundary claims, because the
   author cannot redefine the Issue contract by describing the implementation.
6. Issue Verification/Validation/Testing variants are authored verification
   expectations. The same headings in a PR are typed verification claims, never
   observed execution.
7. Summary, Implementation, Changes, What Changed, and Approach are
   implementation claims. Baseline/Results are typed baseline claims.
8. The PR introduction and title are intent only.
9. Generic Before/After sections form typed before/after state context without
   implying topology, authority, migration, or completion. Structured Change,
   Selected region, Before/After topology, Canonical authority, Production
   path, Migration, Removed legacy paths, Completion conditions, and
   Uncertainty sections form the explicitly classified portion of the same
   PR-authored `TransformationContract`.
10. Routing and assessment fail closed for generic state context. For explicit
    transformation kinds, selector predicates come only from Markdown code
    spans and arrow paths in those sections. They are authored lookup intent,
    not repository observations. Unmarked prose produces a typed diagnostic;
    semantics never guesses an identifier, and downstream consumption remains
    a separate pipeline change.

Deliverables use stable IDs (`R1`, `R2`, ...), negative scope constraints use
`G1`, objectives use `O1`, scope uses `S1`, and Issue verification expectations
use `V1`. Implementation and PR boundary claims use `C1`, baselines use `B1`,
and PR verification claims use `VC1`. Role, purpose, and authority remain
separate fields. If no explicit obligation exists, the renderer reports the
missing acceptance basis.

The linked-Issue relation comes from GitHub GraphQL
`PullRequest.closingIssuesReferences`; PR prose is not parsed to invent Issue
links. Changed files and patches, check runs, and commit statuses come from
GitHub REST endpoints.

## Structural graph boundary

`StructuralGraphProvider` is the read-only structure port.
`CodegraphProvider` reads a repository-local `.codegraph/codegraph.db` in
SQLite read-only mode. It validates the schema, compares indexed file hashes
with its checkout, and verifies that checkout against the corresponding PR
revision. For live reviews, `--repo-root` is only a Git object/worktree source.
The workspace boundary creates exact private head and base worktrees, initializes
Codegraph inside each, and feeds both providers into one revision-aware
`StructuralGraphCollection`.

The same `finally` boundary covers collection, analysis, rendering, and removal
of both temporary revision roots. Caller-owned indexes never enter the live
provider path. Workspace preparation never becomes a second structural
provider or a semantic fallback. `--no-structural-graph` uses the same isolated
head lifecycle without initializing Codegraph or creating a base root.

Only exact changed lines from unified-diff hunks are joined to symbol spans:
head providers map added lines and base providers map removed lines.
The same directional lines define revision-applicable coverage: head requests
only files with added structural lines and base requests only files with
removed structural lines. Added-only and removed-only files are not missing
from the opposite revision; they are explicitly not applicable there.
The narrowest containing symbol wins. Module-level changes may map to the
indexed file symbol, which owns Codegraph import edges. Exact changed symbols
are the only traversal seeds.

Traversal is deterministic and direction-aware. A depth-phased scheduler
finishes direct relations before deeper expansion and gives each exact
changed-symbol seed a fair turn within a depth under explicit per-seed and
review-level safety limits; the default review remains bounded to 80 unique
nodes and 120 paths. The provider emits one typed complete/truncated coverage
record per seed and distinguishes seed-level from review-level node/path
boundaries. Eligible edges are `calls`, `imports`, `instantiates`, `references`,
and `extends`; container edges are excluded. Each path retains direction,
runtime/test/mixed classification, and head-line sources.

Codegraph symbols first normalize to an exact review identity over
repository-relative path, qualified name, and symbol kind. Base/head provider
IDs and spans remain provenance. Same-revision collisions, renames, and moves
are not merged. Changed anchors, executable relation changes, ownership
changes, and projected nodes all reference this one review identity.

Codegraph `contains` edges have a separate, non-executable contract:
`StructuralOwnershipRelation`. For exact changed symbols and symbols retained
by bounded traversal, the provider collects deterministic parent ancestry up
to explicit depth and relation-count safety limits. It removes duplicates,
rejects cycles, and preserves revision-line provenance. Ownership relations do
not enter `StructuralPath`, path classification, or runtime traversal budgets.
`StructuralOwnershipCoverage` records the exact observed-symbol applicability
set plus complete/truncated/unavailable state and limiting dimensions. Facts
normalizes each revision relation as provenance, then emits at most one
review-level `StructuralOwnershipChangeIdentity` per provider parent/child
pair. Added/removed ownership requires an added/removed endpoint or complete,
applicable opposite-revision coverage; otherwise the observation remains
provenance with a partial-coverage diagnostic. Projection owns the canonical
review hierarchy; presentation consumes its IDs without recovering ownership
from paths, names, or symbol kinds.

Missing patches, stale or missing indexes, unindexed code, unmatched lines,
and unavailable base input remain explicit diagnostics. A graph failure never
prevents report generation.

## Canonical evidence and fallback

Each parseable changed hunk is split into contiguous directional change spans.
Each changed line has exactly one canonical representation:

- when Codegraph maps a head-side changed line, its exact symbol represents it
  and receives the covered line's association signature;
- otherwise, a `change_relation` item retains the uncovered lines, typed
  base-to-head operation, bounded display
  previews, complete head/base association signatures, and GitHub source;
- only an absent or unparsable patch produces a `changed_file` fallback.

This line-level replacement rule prevents changed-file, change-relation, and exact
symbol records from competing as parallel truths for the same diff. A partially
mapped span preserves only its uncovered changed lines. Documentation spans
remain evidence with document classification; they are not forced into code
symbols.

Every `EvidenceItem` has a stable ID plus one semantic identity:

- authority (`github_diff`, structural provider, verification provider, or
  supplied);
- revision side (`head`, `base`, `review`, or `unchanged`);
- change operation (`added`, `modified`, `removed`, `renamed`, `retained`,
  `observed`, or `unchanged`);
- fact role and profile.

Changed anchors retain complete normalized head- and base-side retrieval
signatures. Structural provider anchors are review-level change identities
that reference their optional base/head symbol facts; the revision facts are
not routed independently. With complete opposite-revision directional line
mapping for every associated replacement relation, exact symbol presence is the
structural change operation authority: every symbol in a GitHub-declared added
or removed file inherits that file-existence fact; otherwise head-only is added,
base-only is removed, and presence on both sides is modified. Mapping an
unrelated relation in the
same hunk is never absence proof. File symbols retain GitHub changed-file status
so module-level overlap does not relabel a modified file as added. Without
applicable opposite mapping, directional hunk provenance supplies the bounded
operation.
Revision-specific path steps converge once into review-level directed relation
identities with retained, added, or removed
operation and base/head path provenance. Added and removed relations require
an added/removed endpoint or complete opposite-revision traversal; incomplete
coverage remains diagnostic rather than evidence of absence. Relation changes
are the sole edge truth for the review-level change-support graph and are not
independently routed in the R/G pipeline. Projection includes one only when its
path provenance intersects a focus's selected structural support; it never
reconstructs edges from path-step metadata. Their bounded previews are never
used for association. Base-side
signatures are not eligible as current implementation unless the focus is
explicitly about removal, deprecation, cleanup, or a guardrail. Duplicate
symbols and paths merge by identity.

## Typed fact routing

`ProjectionCandidateSet` contains one group per R/G. Routing enumerates
relations without selecting or truncating them:

- PR-authored claims;
- changed anchors;
- runtime and test context;
- current-head verification;
- structural paths;
- G closure facts plus explicit unavailable/partial scan coverage.

Eligibility is determined from canonical fact and requirement profiles.
Typed association kinds include explicit provider association, explicit R/G
reference, exact identifier, distinctive phrase, claim bridge, structural
bridge, and current-head observation. Explicit R/G references are recognized
only across authored statement boundaries, never in arbitrary code or fixture
text. Phrase relations require two shared terms plus a term discriminative
among the review's unique focus meanings. If the eligible changed-anchor corpus
offers a more discriminative phrase cohort within the same fact-profile lane,
it replaces generic phrase fan-out in that lane. Otherwise anchors sharing one
legitimate implementation meaning remain a set. Production, test,
documentation, and other typed lanes do not suppress one another. Claim
bridges require a term discriminative for the selected authored claim and its
eligible anchors. The resulting typed changed-anchor relation set is the only
authority that may sponsor focus-level structural paths or runtime/test
context. This is deterministic set convergence, not a relevance score or
top-k selector.

`CandidateConvergence` then applies typed dominance, bridge reachability, and
identity safety limits inside one R/G and one slot at a time. Claims remain
compact competitive selections. Changed anchors form a canonical evidence set:
distinct direct anchors remain visible together, claim-bridged anchors use a
separate expansion budget, and duplicate relations to one evidence target
collapse. Structural paths and structurally bridged runtime/test contexts form
one terminal-aware convergence unit. Shortest canonical anchor-terminal
connections cover distinct terminal identities before redundant alternatives,
then apply per-anchor, total-path, and context limits. Together their selected
relation IDs and bridge IDs are the reference-only evidence subgraph.
Verification is a set slot keyed by first-class provider,
kind, and normalized name: distinct current-head checks remain visible
together, equivalent duplicates collapse, and conflicting completed outcomes
remain explicit.
Verification has a separate identity-count safety limit and different identities
never create semantic ambiguity.

Changed-anchor, structural-path, context, and verification identity safety
limits emit coverage truncation, never equivalent-tier ambiguity. Context
reachable only through a safety-deferred path is `upstream_deferred`. When an
equivalent claim tier crosses the display budget, stable source order is
disclosed as a tie-break through an `ambiguous` diagnostic. There is no
all-statement/all-evidence numeric score or global candidate budget.

`ReviewProjection` references only IDs selected by `CandidateConvergence`.
Convergence directly emits one typed terminal support set; deferred relation IDs
are the only omitted-path provenance. Projection consumes the support set
without reconstructing terminal relevance or selecting paths, then builds
canonical symbol nodes and typed edges. `ReviewProjection` owns these identities
once in one review-level graph; each slice references them through a focus overlay.
Shared paths and cross-focus overlap collapse by deterministic edge identity,
while global and per-focus path provenance remain explicit. Every selected
changed symbol uses its canonical structural node identity, even without a
selected edge. File, hunk, span, and GitHub line locations remain provenance
rather than parallel evidence. Documents, configuration, unsupported-language
changes, and genuinely unmapped code changes remain standalone changed facts.

Canonical ownership identities form a separate parent/child edge collection.
Projection follows only typed review-level ownership from each selected
structural node to its ancestors, stores shared hierarchy once, and exposes
focus-specific ownership edge IDs. It does not query Codegraph, re-run
head/base convergence, or infer hierarchy from names and paths.
The single structural SVG lays out executable and ownership edges together.
Its focus and Structure controls only change emphasis or visibility of those
canonical IDs; they do not create a second graph truth.
Context facts join an overlay only when selected structural support connects
them.
Profiles remain canonical in `ProjectionCandidateSet`; convergence and routing
diagnostics remain in their own canonical contracts. `ReviewOverview` owns
review-wide CI, source, empty-state, and structural coverage facts. HTML and CLI
resolve and format these contracts; they do not match, classify, join or select
paths, interpret provider codes, or infer why a slot is empty.

Attention normalization preserves diagnostic scope and provider. Aggregation
requires the same scope, provider, slot, and state, so review-wide provider
coverage cannot collapse into focus-level convergence coverage with a similar
message. Synthetic review focus IDs are not exposed as R/G attention targets.

## Packet revisions

`packet_revision` is a deterministic SHA-256 consistency digest over semantic
packet content. It detects accidental content/revision mismatch; it is not a
signature or proof of GitHub origin.

## Private-code boundary

The open core must not import Workspace, Change Unit, semantic-spine,
persistence, webhook, or publisher packages from `interact-space/PrismCode`.
Reusable rules and test vectors may be adapted only through public contracts
and recorded provenance.
