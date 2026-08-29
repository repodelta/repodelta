# R/G semantic candidate-universe extraction

This is an evaluation-only extraction for [Issue #304](https://github.com/repodelta/repodelta/issues/304). It does not modify RepoDelta's production association, convergence, structural projection, assessment authority, HTML report, or frozen v1.1 structural-correctness reference.

All eight source PRs were re-run with the current code. Each regenerated
ordinary structural-correctness packet matched the corresponding frozen v1.1
packet byte-for-byte before the new artifacts were copied. The candidate and
retrieval sidecars are therefore bound to the same ordinary review inputs as
the existing campaign, rather than a changed sample.

| Surface | Count |
| --- | ---: |
| R/G subjects | 76 |
| Profile-eligible changed-anchor candidates | 4,871 |
| Candidates with canonical graph nodes | 3,597 |
| Candidates without a node-backed structural identity | 1,274 |
| Current selected retrievals | 636 |
| Current deferred retrievals | 554 |
| Current non-retrievals | 3,681 |

The large difference between 4,871 frozen candidates and 1,190 observed
retrievals is intentional evidence, not an error: the new artifact freezes the
earlier profile-eligibility surface that existing R/G association later filters.
It makes missed semantic candidates and overly broad lexical associations
measurable without changing either behavior.

Current association observations are distributed as 180 `exact_identifier`,
726 `distinctive_phrase`, 284 `claim_bridge`, and 3,681 non-retrievals. These
are retrieval observations only. They do not prove that any candidate directly
implements or constrains its subject.

No semantic reference has been committed. The old v1.1 reference labels
canonical structural membership, but it does not independently label every
pre-association changed-anchor candidate with a semantic relation and
proofability basis. Recasting the old labels as those new answers would
manufacture authority and invalidate the independent-evidence boundary. A
labeler can generate a blind template from each committed candidate universe
with `repodelta prepare-rg-semantic-reference`.

Consequently this extraction reports **no semantic FI/FE metric yet**. The next
valid step is an isolated semantic/proofability labeling pass using
[`rg-semantic-reference-rubric.md`](../../rg-semantic-reference-rubric.md),
without opening the retrieval sidecars. That reference may also report direct
expectations that lie outside the bounded candidate universe and direct
candidates that cannot map to a graph node. Only after that freeze can
`compare-rg-semantic-candidates` measure retrieval recall and current
direct-attempt precision.
