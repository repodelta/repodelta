# Campaign v1 reconciliation

Campaign v1 is a proposed reference baseline, not independently verified truth.
PR #281 preserved a useful node-role and exact-relation comparison,
but its labels were prepared by an agent and the v2 packet recorded only the
review-wide coverage state. Maintainer merge accepted the repository change; it
did not establish that every reference membership had been independently
reviewed.

PR #273 is not an alternate campaign authority. It recorded richer aggregate
coverage and explicitly proposed decisions, but its evaluator stopped at file
membership and its review-wide traversal counters could not determine which
individual R/G/T/CC focus was complete. Its duplicate artifacts and results are
therefore not migrated.

The current result still supports one bounded conclusion: canonical focus
membership needs correction before explanatory provenance or clustering.
Thirty-four focuses that both proposed label sets treated as resolved with the
same file membership still contained 230 node false inclusions and 134 exact
relation false inclusions under the finer #281 comparison. Those counts are a
reconciliation diagnostic, not a product accuracy claim.

Future campaign output must bind complete review coverage, exact per-seed
mapping, and explicit proposed/verified reference authority. Verification may
be performed by a person or AI, but must record reproducible evidence and remain
isolated from the RepoDelta projection being evaluated. Focus coverage
is derived only from seeds admitted by that reference decision; aggregate
truncation alone cannot resolve or invalidate a focus.
