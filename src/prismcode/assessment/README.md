# Assessment stage

## Owns

Conservative deterministic status for typed transformation claims.

## Input / output

Consumes the transformation contract, typed alignment, canonical evidence catalog,
closure plans, canonical subject selection, and reviewed head SHA. Emits one
`TransformationAssessment` with one typed predicate assessment for every
target predicate and one conservative aggregate claim status.

## Invariants

Every authored claim receives exactly one aggregate status and every target
predicate receives exactly one polarity-preserving status. Missing evidence is
unverified, not contradicted. Repository-wide absence is demonstrated only by a
complete, revision-aware closure scan. Verification is authoritative only for
the reviewed head. Removal and negative conclusions evaluate complete target
predicates; path scopes constrain targets and never become absence targets
themselves. A word such as `without` cannot change unrelated positive
predicates in the same claim into absence assertions.

## Must not

Extract claims, rebuild facts, rank candidates, decide mergeability, or render UI.

## Diagnostics

Typed assessment reasons preserve positive, conflicting, incomplete, stale, and
missing evidence without converting uncertainty into success.

## Extension points

Additional deterministic policies may consume new typed facts when their authority
and coverage boundaries are explicit.
