# Routing

## Owns

Requirement profiles, fact eligibility, authority-aware association,
focus-relative evidence roles, and complete per-R/G typed candidate enumeration.

## Input / output

Canonical statements, scan results, and `EvidenceCatalog` → unselected
`ProjectionCandidateSet`.

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
For G boundary coverage it routes only canonical `boundary_fact` evidence by
its provider-owned G association and preserves unavailable/partial coverage.
Non-G focuses receive no boundary candidates.

## Extension points

The convergence stage consumes all typed candidates before projection.
