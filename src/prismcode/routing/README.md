# Routing

## Owns

Requirement profiles, fact eligibility, authority-aware association, and
complete per-R/G typed candidate enumeration.

## Input / output

Canonical statements and `EvidenceCatalog` → unselected
`ProjectionCandidateSet`.

## Invariants

Eligibility precedes association. Every explicit R/G is visited. Relations
reference canonical IDs, retain typed association reasons, and carry no
selection state. Phrase association requires two shared meaningful terms and at
least one term authorized by the review-local discriminative vocabulary.
Document frequency is computed over unique semantic meanings, so duplicate
focus text retains the same authority. Exact identifiers, explicit references,
and provider associations do not depend on phrase distinctiveness. Claim
bridges require a term discriminative for both the claim and eligible-anchor
corpora.

## Must not

Collect providers, parse patches, order/truncate/select same-slot candidates,
score candidates globally, construct final layout, or render diagnostics.

## Diagnostics

Produces typed focus/slot source and association coverage diagnostics.
For G boundary coverage it references the canonical upstream scan-plan ID and
continues to disclose that no execution fact was collected.

## Extension points

The convergence stage consumes all typed candidates before projection.
