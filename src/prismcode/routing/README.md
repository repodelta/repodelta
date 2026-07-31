# Routing

## Owns

Requirement profiles, fact eligibility, authority-aware association,
focus-relative evidence roles, and complete per-R/G typed candidate enumeration.
`FocusAnchorAssociationSet` is the one production authority for the closed
focus + claims + changed facts → changed-anchor relation region.
`TransformationAlignment` is the separate typed projection for T/CC claims to
canonical observed/closure facts; it reuses the same lexical association
authority without entering R/G routing.
`TransformationSubjectSelection` is narrower: it is the only authority that
resolves explicit transformation predicates to canonical changed structural
identities. It performs exact, revision-aware symbol/path matching and does not
use claim prose, traverse neighbors, or rank equally valid identities.

## Input / output

Canonical statements, scan results, `ObservedTransformation`, and
`EvidenceCatalog` → unselected `ProjectionCandidateSet` plus conclusion-free
`TransformationAlignment` and `TransformationSubjectSelection`.

## Invariants

Eligibility precedes association. Every explicit R/G is visited. Relations
reference canonical IDs, retain typed association reasons, and carry no
selection state. Phrase association requires two shared meaningful terms and at
least one review-focus discriminative term. Within each fact-profile lane, a
more discriminative changed-anchor phrase cohort replaces generic phrase
fan-out; otherwise anchors sharing one legitimate implementation meaning remain
a set. Documentation, production, and test facts never suppress one another.
This focus-relevant anchor relation set is the only authority that may seed
structural path, runtime, or test expansion.
Delivery requirements may use discriminative phrase association. Guardrails
require provider association, an exact identifier, or a deterministic bridge
through an already-associated PR claim; generic phrase overlap is not
implementation evidence for an out-of-scope boundary.
Document frequency is computed over unique semantic meanings, so duplicate
focus text retains the same authority. Exact identifiers, explicit references,
and provider associations do not depend on phrase distinctiveness. Claim
bridges require a term discriminative for both the claim and eligible-anchor
corpora.
Structural changed-anchor candidates come only from canonical
`structural_change` facts; revision-specific symbols are provenance and path
endpoints, not parallel candidates. Uncovered spans continue through the
canonical `change_relation` fallback.
Every changed-anchor relation is classified once as primary, test support, or
documentation support from the typed focus and fact profiles. Documents are
primary only for documentation focuses; tests are primary for test/verification
focuses. Other eligible documents and tests remain support evidence and never
disappear merely to reduce display counts. This role participates in
safety-boundary ordering before association authority.
Documentation and test profiles use explicit leading intent forms such as
`Document…`, `Documentation explains…`, `Tests verify…`, or `Verify…`.
The grammar requires an action or delivery predicate; an incidental
`document fact`, `test fact`, or `Documentation and test profiles…` subject
does not reclassify the focus.

## Must not

Collect providers, parse patches, order/truncate/select same-slot candidates,
score candidates globally, construct final layout, or render diagnostics.

## Diagnostics

Produces typed focus/slot source and association coverage diagnostics.
For G closure coverage it routes only canonical `closure_fact` evidence by
its provider-owned G association and preserves unavailable/partial coverage.
Transformation alignment reports `no_eligible_fact` and `no_association`
without interpreting either as partial, contradicted, or unverified. Current R
focuses receive no transformation or closure candidates.
Subject selection covers every explicit predicate value exactly once with one
or more matches or one `no_structural_match` diagnostic. Ordered-path values
remain ordered seeds; proving or expanding the connecting topology belongs to
bounded transformation closure.

## Extension points

The convergence stage consumes all typed candidates before projection.
