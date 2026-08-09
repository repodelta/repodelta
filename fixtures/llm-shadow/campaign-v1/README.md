# Real-PR LLM shadow campaign v1

This corpus is the first blinded, live-provider sample for issue #211. It is
measurement evidence, not a production-enablement threshold.

## Human disposition rubric

The label author reads the authored statement, the complete bounded request,
the referenced public PR diff, and the recorded coverage limits. The author
must not read `run.selection`, `run.comparison`, model rationales, or aggregate
model metrics until the corresponding label file has been written and
validated.

Each admitted candidate is assigned exactly once:

- `selected`: the supplied content is directly relevant to the authored
  statement. `supporting`, `contradicting`, or `context` describes only its
  evidence-to-statement relationship. The semantic role describes what the
  evidence does, not its filename or admission provenance.
- `rejected`: the supplied content demonstrates that the candidate is
  unrelated to the statement. Lack of proof is not rejection.
- `insufficient`: direction, identity, content, or coverage is too incomplete
  or ambiguous to determine relevance safely.

The author does not treat deterministic membership, admission tier, structural
reachability, an added line, or a passing test as proof. Removed and added code
retain their direction. Coverage limits are preserved as unresolved surfaces;
the author does not infer repository, runtime, or external coverage that the
packet does not contain.

`rubric_version` is `shadow-evidence-disposition.v1`. The public artifact
records only `human_review` authority and contains no reviewer identity.

## Sample

| PR | Stratum | Capture result | Human labels |
| --- | --- | --- | --- |
| #203 | documentation-only governance transition | 2 accepted | 2 requests / 6 candidates |
| #208 | focused production fix with tests and structural paths | 3 accepted, 1 deferred | 4 requests / 10 candidates |
| #215 | cross-component provider and serialization contract | 3 provider errors, 1 deferred | none; no validated model selection |
| #184 | deletion-heavy structural refactor | pre-artifact contract failure | none; tracked by #216 |

The live observations use `deepseek-v4-flash`, the explicit `deepseek` API
profile, disabled thinking, a 1,200-token output limit, and the execution-policy
identity `shadow-policy:f5d9af55c704e40e04a6`. Raw provider error text and
credentials are not retained.

## Recorded result

Across the six independently labeled requests, 16 candidate dispositions were
scored. Five requests executed and one was deferred by the three-request review
limit.

- selection precision: `1.0000`
- selection recall: `0.7500` including the deferred request
- complete-disposition accuracy: `0.7500`
- semantic/evidence role accuracy: `0.5000`
- false-rejection rate: `0.0000`
- deterministic-baseline retention: `0.6000` including the deferred request
- live usage: 8,852 input tokens, 1,654 output tokens, 16,872.64 ms

For the five executed labeled requests alone, selection precision and recall
were both `1.0000`: all ten human-selected claim-evidence relationships were
selected and no unrelated candidate was added. The most important marginal
recovery is PR #203, where deterministic selection contained no evidence and
the model selected all six human-valid documentation relationships. PR #208
did not demonstrate selection gain over deterministic evidence; it showed
retention on executed claims. Role accuracy on executed requests was `0.6667`.

All 16 admitted candidates in the labeled subset were human-selected. This
generation therefore contains no golden rejected or insufficient candidate and
cannot establish false-positive filtering or ambiguity handling. Those strata,
more accepted cross-component runs, and a second independent label author
remain obligations of #211 rather than conclusions hidden by a zero
denominator.

The result does not justify product enablement. Role agreement was only 50%,
model-authored unresolved surfaces did not match the bounded human coverage
contract, PR #215 produced no validated selections, and PR #184 could not emit
an artifact. The HTML for PR #208 was byte-identical after normalizing the
header text from `LLM shadow: off` to `LLM shadow: partial`; no model selection
is currently consumed by the report.

The bounded conclusion is therefore: the sample contains real evidence that
LLM selection can recover documentation semantics missed by the deterministic
baseline, but not evidence that the current LLM path improves the user-visible
HTML or is reliable enough for production influence.

Run the offline corpus contract with:

```bash
.venv/bin/pytest tests/test_llm_shadow_campaign.py
```
