# Assessment stage

## Owns

Conservative deterministic status for typed transformation claims.

## Input / output

Consumes the transformation contract, typed alignment, canonical evidence catalog,
closure plans, and reviewed head SHA. Emits one `TransformationAssessment`.

## Invariants

Every authored claim receives exactly one status. Missing evidence is unverified,
not contradicted. Repository-wide absence is demonstrated only by a complete,
revision-aware closure scan. Verification is authoritative only for the reviewed
head. Removal and negative conclusions evaluate complete target predicates;
path scopes constrain targets and never become absence targets themselves.

## Must not

Extract claims, rebuild facts, rank candidates, decide mergeability, or render UI.

## Diagnostics

Typed assessment reasons preserve positive, conflicting, incomplete, stale, and
missing evidence without converting uncertainty into success.

## Extension points

Additional deterministic policies may consume new typed facts when their authority
and coverage boundaries are explicit.
