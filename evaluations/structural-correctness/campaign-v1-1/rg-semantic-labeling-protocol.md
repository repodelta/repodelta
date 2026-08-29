# R/G semantic reference labeling and verification protocol

This protocol governs the evidence-production campaign in Issue #306. It
operationalizes the [`rg-semantic-reference-rubric.md`](rg-semantic-reference-rubric.md)
for the frozen v1.1 R/G candidate universes. It is frozen before the first
labeling batch is opened.

The protocol does not change the candidate universe, current retrieval
observation, formal report, or production R/G admission. Its purpose is to make
the semantic reference credible enough to measure those existing artifacts.

## Authority boundary

The candidate universe is a derived, bounded source-fact inventory. The
retrieval sidecar is an observed copy of the system under test. A proposed
semantic reference is a declared judgment. A verified reference is an
evaluation authority only for the comparison command; it is never production
proof.

| Result | Owner | Permitted inputs | It does not establish |
| --- | --- | --- | --- |
| Candidate universe | RepoDelta extraction | frozen packet and profile-eligible changed anchors | semantic relevance or repository completeness |
| Proposed reference | labeler | allowed source packet, authored contract, reviewed source/diff evidence, rubric | production direct mapping |
| Verified reference | independent verifier | proposal, allowed evidence, protocol run record; never retrieval output | that `direct_capable` is production proof |
| Comparison | RepoDelta | verified reference and frozen retrieval observation | a redesigned retrieval/admission policy |

Schema and digest validation prove that artifacts are complete and bound to the
same candidate universe. They do **not** prove that a semantic judgment is
correct. Semantic verification is a source-evidence review performed under the
rules below.

## Roles and independence

Every batch has a named proposer/labeler and a named verifier. They must be
different review identities. A review identity is either a person, or a
reproducibly configured model run identified by its provider, model, prompt
version, configuration digest, and execution record.

- A proposer labels candidates and records source witnesses.
- A verifier inspects the proposed labels against source evidence and the
  rubric. The verifier may accept, challenge, or send a row to adjudication.
- An adjudicator is distinct from the proposer and verifier whenever a
  high-risk or unresolved disagreement needs another judgment.
- A human, AI system, or controlled combination may perform any role. Identity
  separation and inspectable evidence, not a label such as “human”, establish
  independence.

The named human Issue owner accepts the campaign method and its published
limitations. That acceptance does not convert any individual semantic label
into production authority.

## Isolation and allowed evidence

Before a batch begins, the proposer receives an input manifest containing only:

- the selected frozen `rg-candidate-universes/pr-<n>.json` artifacts;
- the authored Issue/PR contract and exact base/head source or diff evidence
  identified by candidate source links;
- this protocol and the semantic-reference rubric;
- a batch manifest listing candidate IDs and source-revision identities.

The proposer must not open or receive:

- `rg-retrieval-observations/`;
- association-attribution, structural-focus observation, provenance, policy
  shadow, or comparison artifacts;
- generated RepoDelta HTML reports or any prior retrieval/admission decision;
- a previous label, verifier decision, or aggregate metric for the same batch.

The run record lists the allowed input paths and their SHA-256 values. If the
proposer accesses a forbidden surface, the batch is invalid. Do not silently
repair labels after seeing that surface: discard the batch or record a new,
isolated batch with a different identity.

## Labeling procedure

1. Freeze the batch manifest before any labels are produced. It declares the
   candidate-universe digest, candidate IDs, authored subject IDs, source
   revisions, proposer identity, and the rubric/protocol revision.
2. For each candidate, inspect the authored statement and the cited source/diff
   evidence. Choose the semantic relation and proofability exactly as defined
   by the rubric, then mark the row `reviewed`.
3. A semantic-direct label (`implements`, `constrains`, `removes`, or
   `directly_verifies`) always includes a stable, inspectable source witness.
   A `direct_capable` label additionally names one permitted deterministic
   proof basis. A candidate cannot become direct merely because its name, path,
   graph position, or model confidence looks relevant.
4. For `contextual_support`, `unrelated`, and reviewed `insufficient` rows,
   keep the rubric's required proofability/basis values. Do not leave a
   semantic judgment as `pending`.
5. Record a semantically direct changed fact missing from the candidate
   universe as an `out_of_universe` coverage entry with witnesses; do not force
   it into an unrelated candidate row.

The proposal remains non-authoritative after every row is reviewed. It must not
be compared with retrieval until independent semantic verification succeeds.

## Model-assisted labeling

AI assistance is allowed only as a reproducible proposer or verifier process.
For every model-assisted batch, the run record must state:

- provider and model identifier, endpoint class, and execution date;
- prompt template revision and SHA-256 digest;
- declared decoding/configuration values and their normalized digest;
- exact allowed-input manifest and source-revision identities;
- batch candidate IDs, structured label-output digest, and any transport or
  failure category;
- whether a person reviewed, modified, or accepted the model's labels.

Never use hidden chain-of-thought as evidence. Store the structured labels,
their cited source witnesses, and reproducibility metadata; do not store
secrets or raw provider error text. A model's confidence or rationale is not a
proof basis by itself.

## Semantic verification and risk review

The verifier validates more than JSON shape:

- the stated witness resolves to the reviewed revision and actually supports
  the selected semantic relation;
- semantic-direct labels satisfy the authored statement rather than merely
  sharing vocabulary or a nearby structural component;
- the proofability and basis follow from the cited evidence, not from the
  current retrieval result;
- `out_of_universe`, `node_unresolved`, `not_node_backed`, and reviewed
  `insufficient` cases remain visible as coverage or uncertainty.

Every semantic-direct row is high risk. Before a reference is verified, the
campaign also predeclares a stratified audit sample covering at least the
following risk surfaces present in that batch:

- direct versus contextual/unrelated boundary;
- Requirements and Guardrails;
- broad lexical or alias-like wording;
- changed anchors with no graph node;
- direct-capable versus suggested-only proofability.

Each high-risk row receives a second independent review. That review may be by
a person or a distinct model configuration, but it must have a separate run
record and source-evidence inspection. The sample design, candidate IDs, and
acceptance rule are frozen before its labels are compared.

## Disagreement and adjudication

Do not overwrite or silently converge conflicting judgments. Preserve the
proposer's label, verifier's challenge, source witnesses, and adjudication
decision in a committed adjudication ledger keyed by candidate ID.

- If the evidence resolves the disagreement, the ledger records the reasoning
  and the final reviewed label cites that evidence.
- If evidence cannot responsibly resolve it, use reviewed `insufficient` only
  when the insufficiency is about the evidence itself. The row note links the
  disagreement record.
- If the campaign cannot establish isolation, witness validity, or a reliable
  final label, keep the batch/reference unverified. It must not emit metrics.

Disagreement rate and unresolved/adjudicated counts are campaign findings, not
noise to be removed from the final report.

## Freeze, verification, and stop conditions

After every candidate in a proposal is explicitly `reviewed`, the independent
verifier checks the run records and semantic evidence. The verifier may invoke:

```bash
repodelta verify-rg-semantic-reference \
  --candidate-universe <frozen-universe.json> \
  --reference-labels <reviewed-proposal.json> \
  --verified-by <independent-reviewer> \
  --verification-method <protocol-and-evidence-record> \
  --verification-evidence <committed-run-record> \
  --system-under-test-isolated \
  --output <verified-reference.json>
```

The command validates lifecycle state, universe digest, proposal digest, and
metadata. It does not replace the verifier's source-evidence review. A
verifier must not invoke it unless the protocol evidence above is recorded.

Only verified references can be sent to
`compare-rg-semantic-candidates`. If any batch fails a stop condition—missing
metadata, invalid isolation, unresolved high-risk review, or insufficient
evidence to stand behind the completed proposal—publish that limit and do not
claim semantic FI/FE.

## Campaign records

When the first artifacts are frozen, add only the records needed to reproduce
the campaign:

```text
campaign-v1-1/
├── rg-semantic-labeling-protocol.md
├── rg-semantic-labeling-runs/     # input manifests and model/human run records
├── rg-semantic-proposals/         # complete reviewed, non-authoritative labels
├── rg-semantic-references/        # independently verified labels
├── rg-semantic-adjudications/     # disagreements and their disposition
└── results/rg-semantic-reference/ # comparison outputs and findings
```

Do not create empty placeholder artifacts. Each committed record must bind its
candidate-universe digest and identify the rubric/protocol revision used.
