# Campaign v1.1 findings

## Decision

Correct canonical focus association before investing in richer provenance,
large-change clustering, or workflow traceability. The independently verified
reference still shows severe focus over-selection. This conclusion is bounded
to the frozen candidate and coverage surface and does not change production
assessment or mergeability.

## Verified result

- 8 real pull requests, 110 resolved focuses, and 3 unresolved focuses.
- File overview: 34 false inclusions, 0 false exclusions, and 0 role
  disagreements.
- Focus nodes: 1,453 false inclusions, 176 false exclusions, and 14 direct/context
  role disagreements.
- Exact relations: 684 false inclusions and 49 false exclusions.
- Focus coverage: 3 complete for admitted direct seeds, 78 limited by truncated
  admitted seeds, 29 correctly empty, 0 unknown, and 3 reference-unresolved.

## Difference from campaign v1

Campaign v1 used agent-prepared proposed labels and reported 1,458 node false
inclusions, 170 node false exclusions, and 13 role disagreements. Independent
review found that several selected exact relations omitted one endpoint from
the proposed membership. Closing those invalid references changed the verified
result to 1,453 false inclusions, 176 false exclusions, and 14 role
disagreements. Exact-relation counts remain 684 false inclusions and 49 false
exclusions.

The changed numbers are expected: v1.1 is not a new authority label placed over
the old answer. It corrects the answer, binds the corrected proposal digest,
and records the evidence and isolation used to verify it.

## Coverage interpretation

Most non-empty focuses have limited traversal coverage. Their false-exclusion
counts therefore cannot establish repository-wide recall and must remain
bounded to collected candidates. That limitation does not explain the false
inclusions: those nodes and relations were actually projected by RepoDelta but
were excluded by the independently verified reference. The direction of the
over-selection finding is therefore robust even though exhaustive recall is
not established.

## Next product experiment

Change direct-anchor association so exact authored selectors and direct changed
evidence remain direct while closure/reachable support stays context or outside
the focus. Re-run this frozen campaign after that change. Accept the change only
if verified false inclusions fall substantially without increasing bounded
false exclusions or converting limited coverage into an unsupported completeness
claim.
