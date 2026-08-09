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

Provider execution was prohibited until the pre-execution packet and label
commit was frozen. Commit `e1462d0` is that boundary; it was pushed before any
campaign-v2 provider request. The observation artifacts were produced only
after that remote checkpoint existed.

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

## Recorded execution

The live run used the repository's generic OpenAI-compatible adapter with the
DeepSeek API profile. The recorded policy is
`shadow-policy:f49ded2093e7837149c4`:

- endpoint profile: `deepseek` at
  `https://api.deepseek.com/chat/completions`;
- model ID: `deepseek-v4-flash`;
- thinking mode: `disabled`;
- maximum output tokens: 4,000;
- request timeout: 180 seconds;
- unchanged campaign guardrail: at most three live requests per PR.

The 4,000-token output bound is part of this observation, not a validated
product default. Campaign-v2 does not establish that the repository's smaller
default output bound is sufficient.

Every live command regenerated the labeling packet from the public PR and
required exact equality with the frozen packet before provider invocation.
Only those bounded public-PR requests were sent. No provider response or
provider error text is an input to the human labels.

The eight artifacts contain 20 accepted requests and 18 policy-deferred
requests. There were no provider, transport, status, rate-limit, decoding, or
invalid-output failures. Accepted requests consumed 60,435 input tokens and
10,971 output tokens in 99,335.875 ms.

| PR | Accepted / deferred | Deterministic TP / FP | LLM TP / FP | LLM precision | Observed role |
| --- | ---: | ---: | ---: | ---: | --- |
| #148 | 3 / 4 | 12 / 1 | 12 / 1 | 0.9231 | baseline false positive retained; no incremental selection |
| #168 | 1 / 0 | 15 / 0 | 15 / 0 | 1.0000 | baseline-retention control; no incremental selection |
| #193 | 3 / 5 | 0 / 0 | 5 / 3 | 0.6250 | recovered cross-predicate relevance but selected ambiguity |
| #200 | 3 / 7 | 0 / 0 | 2 / 1 | 0.6667 | recovered documentation relevance but selected ambiguity |
| #205 | 2 / 0 | 0 / 0 | 12 / 0 | 1.0000 | recovered focused code/test relevance |
| #206 | 3 / 0 | 3 / 0 | 15 / 0 | 1.0000 | added 12 correct abstract-semantic selections |
| #213 | 3 / 2 | 0 / 0 | 13 / 21 | 0.3824 | broad generic-state candidates caused severe over-selection |
| #218 | 2 / 0 | 0 / 0 | 4 / 0 | 1.0000 | recovered compact code/test relevance |

Only accepted requests measure model semantic behavior. Treating deferred
requests as empty model answers would conflate the three-request safety budget
with model quality. Across the accepted slice:

- the manual reference contains 78 selected candidates among 108 candidates;
- deterministic evidence selected 31: 30 true positives, 1 false positive,
  and 48 false negatives (precision 0.9677, recall 0.3846);
- the LLM selected 104: 78 true positives, 26 false positives, and no false
  negatives (precision 0.7500, recall 1.0000);
- LLM-only evidence contains 48 true positives and 25 false positives
  (precision 0.6575);
- complete-disposition accuracy is 0.7593 and role accuracy is 0.7051;
- all 16 manually insufficient candidates were selected by the LLM; of 14
  manually rejected candidates, 10 were selected and 4 were rejected;
- all 30 manually relevant deterministic candidates were retained, and the
  model never rejected a manually selected candidate.

The result is therefore not “deterministic is already sufficient,” and it is
not “the LLM cannot add evidence.” Deterministic selection is high precision
but misses 48 manually relevant candidates in the executed slice. The model
recovers all 48, including documentation, abstract semantics, and focused code
changes. Its present behavior is a high-recall expansion, not a reliable
filter: it over-selects ambiguous candidates and does not use the
`insufficient` disposition.

## HTML audit and product decision

For each PR, campaign-v2 generated a deterministic-only formal review, an
LLM-shadow formal review, and an independent comparison HTML. After normalizing
the header's `LLM shadow` execution state, every deterministic/shadow formal
HTML pair is byte-identical. This is the intended authority boundary: model
output changes neither formal evidence nor assessment.

The comparison reports expose deterministic-only, LLM-only, shared, unselected,
human disposition, model disposition, role agreement, execution state, and
unresolved surfaces without feeding any value back into the formal report. In
the worst control, PR #213, the accepted comparison rows show 34 LLM-only
selections, including 12 manually insufficient and 9 manually rejected
candidates, plus 8 role mismatches. This report makes the failure mode visible;
the formal report correctly remains unchanged.

Campaign-v2 does not justify broad formal LLM integration. The product should
retain deterministic assessment authority and keep LLM output non-authoritative
and opt-in. A future semantic-suggestions surface must first demonstrate
materially better negative and `insufficient` discrimination on the frozen
campaign-v2 corpus; candidate admission alone is not a confidence signal. The
current observations do justify continued shadow evaluation because the model
adds real recall that deterministic matching does not provide.

These conclusions are bounded by one model/profile, one independently authored
manual reference set, the first three admitted requests per PR, and eight
public PRs. A second human adjudicator and another provider/profile remain
external validation, not implied evidence.
