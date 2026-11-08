# Agent protocol log (draft)

Running record of what each phase of `docs/agent-change-protocol.md` actually
caused an agent to find, what was ceremony, and where responsibility was
ambiguous. Process evidence, not product contract. Location in the repository
is provisional until the maintainers confirm it.

Each entry separates observed facts from interpretation.

## #308 — capability-aware federated evidence providers

Base: `upstream/main` at 70d65a8 (contains #297). Second provider: Alembic
migrations parsed with stdlib `ast`, chosen so corroboration and conflict can
be exercised by two real providers asserting the same table/column subject.

### OBSERVE / census

- Caused a finding: `sql_schema_coverage` and `sql_schema_capabilities` are
  populated on `EvidenceCatalog` but have no consumer; SQL gaps reach the
  overview only as untyped diagnostic text. Without tracing backward from sinks
  this would look like shipped coverage.
- Caused a finding: SQL file selection is a hard-coded `.sql` suffix filter in
  `pipeline.py`; files no provider claims are silently dropped.
- Caused a finding: `_put` merges same-ID items without recording which
  provider contributed, so corroboration is currently unobservable.
- Ceremony: none identified yet.
- Ambiguity: "routing" already names deterministic R/G fact routing in
  `docs/fact-routing.md`. Changed-file-to-provider dispatch is a different
  concept and needs a different name (`provider plan`).
- Unverified (carried forward, not treated as coverage): whether `routing`,
  `projection` or LLM packet code mishandles `sql_schema_statement` items;
  whether `evaluations/` artifacts pin the `authority` values.

### Plan delta 1 (before production-boundary mutation)

Verified by grep on the merge tree: nothing outside contracts, catalog and the
SQL provider reads `sql_schema_statement`; routing selects by `profile` in
{generated, verification, test, production} or `role == closure_fact`; pinned
`fixtures/llm-shadow/**` pin the `authority` value `structural_provider`, not the
`EvidenceItem` field set (strict field checks there apply to LLM responses).

Consequences for the plan:

- Authority for "which schema statement was observed" moves to one
  provider-neutral `schema_fact` (subject, attribute, value). The provider-local
  `sql_schema_statement` item and the `sql_schema_coverage` /
  `sql_schema_capabilities` catalog fields are stale duplicates with no consumer;
  they are removed, not kept beside the new path. `SqlSchemaResult` stays the
  SQL provider's own result (provider behavior unchanged).
- Permitted loss: `normalized_text` and the statement kind are not carried on the
  neutral fact; line and path remain in `sources`.
- Conflict is defined only across different providers on the same
  (subject, attribute, revision side) with different values. Two contradictory
  facts from one provider stay separate facts (sequential statements) and are not
  a conflict.
- `providers` (concrete identities) on every provider-authored item; empty for
  `github_diff` and `supplied`. Identity is set where it is known
  (`index.provider`, `VerificationIdentity.provider`), not derived from `authority`.

### Counterexample phase (before review)

Eleven counterexamples were generated from the contract before any code and
became tests (`tests/test_provider_federation.py`, `tests/test_alembic_migration_provider.py`).

What they caught: nothing in the implementation on first run. All passed except
one test that tampered with the wrong item (its own bug). Read this as a weak
signal, not as evidence of correctness: the counterexamples were written by the
same author who then wrote the code, from the same mental model.

What only a different probe caught:

- Mutation of the production code (12 single-point mutants, one per invariant)
  found two survivors. One was an equivalent mutant: a "fact outside dispatch"
  check that coverage validation already implies, so it was deleted rather than
  tested. The other was a vacuous test: the "other side" provider was never
  dispatched, so the same-side scoping of conflicts was untested. Both were
  invisible to the counterexample list.
- Running the real CLI found that the second provider was not registered in the
  composition root, so it could never route or report in production. No unit or
  end-to-end test at the analyzer level could see this; a CLI-level test now pins
  it. This is the protocol's "sink evidence" step doing real work, but only
  because the sink was actually executed.

What still depends on a human reviewer: whether the counterexample list is
complete. Nothing here generates counterexamples independently of the author;
mutation testing checks the tests against the code, not the contract against
the world. Expect review to add cases (quoting and case rules of identifiers,
Alembic idioms such as `op.batch_alter_table`, multi-statement `ALTER TABLE`).

### Census and plan: what each phase earned

- OBSERVE / census: high value. Three findings changed the design (no consumer
  for SQL coverage; silent `.sql` filter; `_put` erasing provenance).
- Plan delta: high value, and cheap. Recording "replace, do not add beside"
  before touching code is what removed `sql_schema_statement`, the two
  `sql_schema_*` catalog fields and `unavailable_sql_schema_result` instead of
  leaving duplicate producers.
- Provenance/scope/owner classification: earned its keep once, deciding that the
  neutral `schema_fact` is cross-provider and derived, while coverage rows are
  provider-owned. Otherwise it was ceremony for the smaller results.
- Ceremony: the four separate completion states are mostly one judgement here.

### Where responsibility was ambiguous

- Contract types live in `model/contracts.py`, not `providers/`, because
  `providers` already imports `model` and the catalog type must embed them. The
  protocol has no rule for placing a type that two layers must share.
- Removing `sql_schema_statement` could be read as expanding the region beyond
  #308. It was kept inside: it is the same responsibility (which schema
  statement was observed), and leaving it would have created a second authority.
- Three copies of `_checkout_revision` already exist (closure, codegraph, SQL).
  Only SQL and Alembic now share `providers/checkout.py`; closure and codegraph
  are outside the region because their contracts did not change. Left as-is on
  purpose, not by oversight.

### Prose versus executable form

Executable: capability declaration validated at ingestion; conflict as a type
recomputed by `EvidenceCatalog.validate_consistency`; unclaimed files as a
recorded field of `ProviderPlan`; provider identity required by item validation;
symlink, stale and dirty checkout guards shared by both providers.

Still prose only (enforced by tests and `docs/architecture.md`, not by a type):
same-provider differing values are not a conflict; identifier case-folding as a
permitted loss; "only `upgrade()` is examined" for Alembic.

### Unresolved surfaces (not treated as covered)

- Schema facts appear to be inert downstream of the catalog: the profile and
  role filters in `routing/candidates.py` select generated, verification, test,
  production and closure facts, and `schema` items match none of them. Inferred
  from those filters, not traced end to end. They reach the overview and HTML
  (verified by test), but probably not requirement assessment. The same held for
  #297 statements and is not changed here.
- Conflict semantics for a provider overlapping the structural graph's own
  domain: unaddressed, no such provider exists.
- Selector vocabulary is path-only (suffix, exact, glob). A provider whose
  applicability is not path-shaped is not expressible.
- `SqlSchemaResult`'s flat capability list: resolved by opaque capability
  strings per descriptor plus per-fact validation, not by a shared vocabulary.
  Two providers name equivalent capabilities differently (`alter_column_set_not_null`
  vs `op.alter_column.nullable`); corroboration keys on the neutral fact, not on
  capability names.
- Alembic coverage is intentionally narrow: no `op.batch_alter_table`, no
  conditionals, no schema-qualified names; each is an explicit gap.
- `evaluations/` artifacts were checked for schema pins: none reference the
  bumped versions.

### Plan delta 2 (review of PR #327, before production-boundary mutation)

Invalidating evidence, from maintainer review and verified on `a2323b4`:

- Ingestion validated an observation against the descriptor shipped in the
  same `ProviderContribution`, not against the declaration used for planning.
  `ProviderPlanEntry` kept only identity and paths, `run_providers` called
  `descriptor()` a second time, and a contribution from a provider absent from
  the plan was accepted with whatever capabilities it carried. The recorded
  contract ("validated against the pre-run declaration") was not enforced.
- `derive_evidence_conflicts` decided "conflict" from provider identity, an
  orthogonal dependency: two statements from distinct files with different
  values were a conflict when two providers read them and not when one did.
  Neither case establishes a shared migration instant or effective database
  state; the statements are the same either way. Agreement across files has
  the symmetric overclaim for corroboration.
- `Closes #308` contradicted `Parent completion: open`. The repository rule
  requires the closing reference; the open state was a misclassification, since
  every listed unresolved surface is either an Uncertainty recorded in #308
  itself, unchanged from #297, or an explicit provider gap.

Changed contract and owners:

- Authority for "what a provider declared before it ran" moves into
  `ProviderPlan.descriptors` (declared, domain-wide, owner `plan_providers`).
  Ingestion rejects a contribution whose descriptor differs from the planned
  one, a contribution from an unplanned provider, and a planned provider with
  no contribution. `EvidenceCatalog` recomputes coverage capabilities and
  identities against the persisted plan instead of trusting the coverage rows.
- The cross-provider derived result is renamed and re-scoped to what the
  observations establish: `EvidenceDivergence` (derived, domain-wide, owner
  `derive_evidence_divergences`) records that different providers assert
  different values for one (side, subject, attribute) in their sources. It
  does not claim contradictory or effective database state. Grouping is
  unchanged; the provider-identity dependency is now the definition of the
  signal, not an accident of it. Agreement is described as agreeing assertions,
  not proof of effective state. Presentation labels follow.
- Rejected alternative: a same-source comparable scope. It needs a
  statement-level identity across two parsers, has no production instance
  (SQL and Alembic never claim the same file), and would leave the #308
  end-to-end requirement without a real provider pair.

Region unchanged. `evidence_catalog.v21` / `review_brief.v60` are unreleased in
this PR and are not bumped again. Excluded on review guidance: requirement
assessment of schema facts and wider Alembic support.

Evidence for delta 2:

- Counterexamples written before the fix (drifted declaration, unplanned
  contribution, planned-but-silent idle provider, persisted coverage
  capabilities widened, persisted plan dispatching an unclaimed path): all five
  failed on `a2323b4` with "DID NOT RAISE", i.e. the gaps were real.
- Mutation of the new guards (descriptor equality, unplanned, missing, claims
  check, coverage-vs-plan check, plan recording its descriptors) and of the
  divergence presentation (caveat removed, old label, provider-identity
  requirement dropped): nine mutants, all killed.
- Final tree: 685 passed (baseline 680 rerun independently on `a2323b4`); the
  CI fixture review via the real CLI still renders.
- What this does not show: whether "divergence" is the signal reviewers need.
  It is shaped by the observations available now; separating proven
  contradiction from divergence waits for a provider pair that reads the same
  source.
