# Closure

## Owns

The canonical executable scan plan and bounded base/head observation path for
guardrails, typed removal claims, and conservative negative completion
conditions.

## Input / output

Canonical G statements plus `TransformationContract` claims become
`ClosureScanPlanSet`; exact revision checkouts become one revision-aware
`ClosureScanResultSet`.

## Invariants

Each eligible statement owns one stable plan and one result. Guardrails and
negative completion conditions inspect head; removals preserve separate base
and head observations. Transformation plans consume the one-pass typed
`TransformationPredicateSet`; they never reparse normalized claim prose.
Plans retain source text and provenance. Every observed
match carries its predicate, target, revision, surface, canonical path profile,
and location. Each predicate owns one target plus an optional path-scope set;
the scanner evaluates the target only inside that set. A path scope without an
exact target is diagnostic rather than an executable absence assertion.
Unavailable or partial revision coverage stays explicit.

## Must not

Turn a claim into a repository fact, infer removal without base evidence,
interpret zero matches as repository absence, associate closure facts to R/G,
or decide demonstrated/partial/contradicted/unverified status.

## Diagnostics

Reports missing executable predicates, missing base input, stale or dirty checkouts, and
typed file/byte/match safety boundaries independently for each revision.

## Extension points

Additional statement kinds or scan surfaces must enter the same plan/result
contract and preserve revision-specific coverage; they must not add a second
scanner or fact authority.
