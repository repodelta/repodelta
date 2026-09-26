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
