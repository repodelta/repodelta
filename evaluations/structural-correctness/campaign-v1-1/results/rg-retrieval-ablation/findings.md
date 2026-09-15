# PR #208 R/G retrieval ablation

This Issue #322 experiment is evaluation-only. The seven diagnostic IDs were selected by historical calibration, but no semantic label, proof value, or admission decision enters query generation. Q0 is broad lexical candidate generation only within the frozen pre-association candidate universe and its reviewed source spans; it is not general requirement-to-code retrieval.

## Bounded result

| Mechanism | Recovered | Incremental | Additional candidate memberships | Unresolved |
| --- | ---: | ---: | ---: | ---: |
| Baseline current association | 0 | 0 | 0 | 7 |
| Explicit identifier variants | 0 | 0 | 0 | 7 |
| Authored terms → bounded reviewed-head lexical spans | 7 | 7 | 10 | 0 |
| Historical vocabulary → reviewed-head lexical spans | 7 | 0 | 13 | 0 |

All seven diagnostics are recovered by normalized authored R/G terms searched only inside the frozen pre-association candidate universe's source spans at the frozen PR #208 head. This is bounded candidate generation, not a general requirement-to-code retrieval result.

## Post-hoc Q0 extra characterization

The existing historical calibration is used here only as an evaluation oracle after Q0 membership has been fixed. It did not enter query terms, lexical matching, or membership selection, and its `proposed` dispositions are not verified semantic truth.

| Q0 extra disposition in historical calibration | Count |
| --- | ---: |
| historical declared direct | 2 |
| historical declared non direct | 8 |
| historical declared insufficient | 0 |

Of Q0's 10 extras, eight are historically declared non-direct contextual support and two are historically declared direct. That mixture means cheap lexical search gives sufficient bounded recall for these seven diagnostics, but downstream semantic resolution remains necessary.

Historical Issue/PR vocabulary also finds reviewed-head candidates but adds no incremental recovery in this set (0). It is therefore not part of the minimum retrieval substrate. There are no residual misses, so Q3 current-vocabulary expansion, Q4 structural expansion, and Q5 semantic/LLM/agentic search were not run. Semantic or agentic search was not required to recover these seven bounded diagnostics; this experiment does not determine whether it is required for general retrieval or semantic resolution.

## History/current boundary

Present repository state classifies historical vocabulary and controls; it never overwrites the source fact at the reviewed PR head.

| Control | Resolution | Current fact emitted? |
| --- | --- | --- |
| `NC:former-seed-owner` | `superseded` | `False` |
| `NC:rejected-primary-gate` | `superseded` | `False` |
| `NC:renamed-path` | `renamed_or_replaced` | `False` |
| `NC:renamed-product-term` | `renamed_or_replaced` | `False` |

The renamed `src/prismcode/...` path, old `PrismCode` name, former relation/evidence-role seed owner, and primary-only gate remain historical or superseded. None is emitted as a current responsibility, membership rule, semantic relation, or admission fact.

## Next bounded hypothesis

A later, separately scoped production experiment can add provenance-preserving reviewed-head lexical R/G candidates as `suggested` retrieval evidence, paired with a separate semantic resolution stage and without changing proof or admission authority. This experiment does not itself justify a production change or a general conclusion about LLM/embedding retrieval.
