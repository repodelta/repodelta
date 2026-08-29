# R/G semantic candidate reference rubric

This rubric labels the bounded R/G candidate universe introduced for Issue
#304. It is not a second interpretation of RepoDelta's projection. A labeler
works from the authored Issue statement, the exact reviewed diff/source
identities, and the candidate-universe packet. Do not open the retrieval
observation, structural-focus observation, association sidecar, comparison
output, or generated report until the reference is frozen.

## Candidate universe boundary

Every entry is a profile-eligible changed-anchor fact. It is a deliberately
bounded structural candidate surface, not a claim that every entry is
semantically relevant and not a repository-wide semantic universe.

Each candidate preserves its evidence ID, classification/profile, revision,
change operation, source links, and any canonical review-symbol/graph-node
mapping. A candidate with `node_unresolved` or `not_node_backed` remains
labelable: lack of a graph node is coverage information, not a reason to
discard a source fact.

Structural paths, relation endpoints, ownership/placement ancestors, retained
topology, and Guardrail closure/current-head scans are intentionally absent.
They may support a later explanation or proof, but they are not direct semantic
candidates in this reference.

## Semantic relation

Choose exactly one for every candidate:

- `implements`: the changed fact directly realizes the requirement.
- `constrains`: the changed fact directly enforces or preserves the guardrail.
- `removes`: the changed fact directly removes the prohibited/legacy behavior.
- `directly_verifies`: the changed fact directly verifies the authored subject.
- `contextual_support`: related supporting structure, but not a direct
  realization/constraint/removal/verification.
- `unrelated`: no supported semantic relation to the subject.
- `insufficient`: bounded evidence cannot support a responsible decision.

Lexical overlap, path similarity, canonical-node uniqueness, graph reachability,
and a model's confidence are candidate evidence only. None is, by itself, a
semantic-direct label.

## Proofability

For a semantic-direct label, separately record whether RepoDelta could
eventually treat the relation as direct authority:

- `direct_capable`: a source-linked, deterministic basis exists. Use one of
  `explicit_authoring`, `typed_predicate`, `bounded_evidence`, or
  `deterministic_mapping`, and cite concrete witnesses.
- `suggested_only`: the semantic relation is plausible, but only heuristic or
  model-suggestion evidence is available. It must remain non-authoritative.

For `contextual_support` or `unrelated`, use `not_applicable` and `none`.
For `insufficient`, use `insufficient` and `none`.

Witnesses must identify the source evidence used for the label (candidate
source link, exact diff/source region, or another stable reviewed identity).
They must not cite a RepoDelta association/membership as proof.

## Coverage gaps

If independent review identifies a semantically direct changed fact that does
not appear in the candidate universe, record an `out_of_universe` entry with
the subject, intended direct relation, stable source identity, and witnesses.
Do not force it into an arbitrary candidate row. The comparison reports this as
coverage, not as a candidate-retrieval false exclusion.

## Freeze and verification

The template begins with every candidate `insufficient`. A proposed reference
is complete only when it disposes every candidate. It becomes verified only
after a separate verifier records method, evidence, and isolation from the
retrieval observation, then binds the exact proposal digest. A human, AI, or
controlled combination may verify it; reproducible evidence and isolation are
the authority conditions.
