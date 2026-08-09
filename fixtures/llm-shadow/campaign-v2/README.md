# Real-PR LLM shadow campaign v2

This corpus extends campaign-v1 with directed public-PR strata and blinded
pre-execution labels. It is measurement evidence, not a production-enablement
threshold.

## Pre-execution protocol

1. Generate each `llm_shadow_labeling_packet.v1` artifact without enabling
   shadow execution.
2. Review the authored statement, complete bounded request, public PR diff,
   and coverage limits without reading any model output.
3. Assign every admitted candidate exactly once under
   `shadow-evidence-disposition.v1` and validate complete label coverage.
4. Commit the packets and human labels before any provider invocation.
5. Regenerate each packet and require exact equality before sending its bounded
   requests to the configured provider.

Provider execution is prohibited until the pre-execution packet and label
commit is frozen.

## Human disposition rubric

- `selected`: the supplied directional content is directly relevant to the
  authored statement. Evidence role and semantic role describe only that
  relationship; they do not assert implementation acceptance.
- `rejected`: the supplied content demonstrates that the candidate is
  unrelated to the statement. Missing proof is not rejection.
- `insufficient`: identity, direction, content, or coverage is too incomplete
  or ambiguous to determine relevance safely.

Admission tier, deterministic membership, structural reachability, and an
added line are not relevance proof. Coverage limits remain unresolved instead
of being inferred away.

## Directed sample

| PR | Primary stratum | Negative/ambiguity role |
| --- | --- | --- |
| #200 | documentation and artifact-authority semantics | incomplete and unrelated fallback candidates |
| #206 | abstract invariant-enforcement semantics | role-discrimination control |
| #205 | focused structural-provider fix | code/test relevance control |
| #218 | focused shadow-execution fix | compact code/test control |
| #193 | cross-predicate role convergence | cross-component ambiguity |
| #213 | cross-component generic-state admission | broad fallback ambiguity |
| #148 | governance migration | baseline false-positive filtering |
| #168 | baseline-heavy documentation region | deterministic-retention control |

The sample deliberately overlaps strata: #200 and #148 own the required
golden rejected/insufficient surfaces, while #193 and #213 stress semantic
selection across component boundaries.

## Frozen reference labels

The pre-execution corpus contains 38 complete request labels over 251 admitted
candidates:

- 134 selected;
- 92 rejected;
- 25 insufficient.

The packets contain no run or selection fields. These packet and label files
are committed before provider execution; later observations must regenerate an
exactly equal packet before any request is sent. The reference labels are an
independent manual judgment under the rubric above, not a model selection or a
production assessment.
