# LLM shadow evaluation

RepoDelta's supported review path is deterministic. The LLM path is an opt-in
research surface that compares model selections with deterministic evidence
selection and frozen human labels. It does not change formal assessment,
verification, HTML conclusions, or mergeability.

The active experiment and results are tracked in
[#211](https://github.com/repodelta/repodelta/issues/211). Future semantic
intake, R/G-to-subgraph mapping, architectural overlays, and grounded
explanations are tracked independently in
[#224](https://github.com/repodelta/repodelta/issues/224),
[#225](https://github.com/repodelta/repodelta/issues/225),
[#226](https://github.com/repodelta/repodelta/issues/226), and
[#227](https://github.com/repodelta/repodelta/issues/227).

## Run bounded shadow selection

Configure an OpenAI-compatible provider explicitly:

```bash
export OPENAI_API_KEY=...
export REPODELTA_LLM_MODEL=...
export OPENAI_BASE_URL=https://api.openai.com/v1
export REPODELTA_LLM_API_PROFILE=openai  # openai | siliconflow | deepseek

# Optional provider-neutral execution policy.
export REPODELTA_LLM_TIMEOUT_SECONDS=180
export REPODELTA_LLM_MAX_OUTPUT_TOKENS=1200
export REPODELTA_LLM_THINKING_MODE=disabled  # default | enabled | disabled
export REPODELTA_LLM_REASONING_EFFORT=default  # default | high | max

# SiliconFlow-only and valid only with thinking enabled.
# export REPODELTA_LLM_THINKING_BUDGET=1024

repodelta review \
  --repo owner/repository \
  --pr 123 \
  --llm-shadow \
  --output build/pr-123.html
```

Omitting `--llm-shadow` performs no provider call and writes no shadow artifact.

## Prepare a blinded labeling packet

Freeze the exact model-independent requests before any provider call:

```bash
repodelta review \
  --repo owner/repository \
  --pr 123 \
  --llm-shadow-labeling-output build/pr-123.labeling.json \
  --output build/pr-123-deterministic.html
```

The prepare command cannot invoke a model. An independent reviewer completes
every disposition in a human-label artifact without seeing the corresponding
model answer.

Then execute against the frozen packet:

```bash
repodelta review \
  --repo owner/repository \
  --pr 123 \
  --llm-shadow \
  --llm-shadow-labeling-input build/pr-123.labeling.json \
  --llm-shadow-human-labels build/pr-123.human-labels.json \
  --output build/pr-123-shadow.html
```

Execution fails before provider invocation if the source revision, request
identity, candidate admission, candidate membership, coverage limits, or human
label coverage differs from the frozen packet.

## Render the independent comparison

After execution, compare the frozen human labels, deterministic selection, and
model dispositions offline:

```bash
repodelta compare-shadow \
  --labeling-packet build/pr-123.labeling.json \
  --execution build/pr-123-shadow.html.llm-shadow.json \
  --human-labels build/pr-123.human-labels.json \
  --output build/pr-123-shadow-comparison.html
```

The command revalidates that the execution preserved every frozen admission,
then shows deterministic-only, LLM-only, shared, and unselected candidates
beside the human disposition and semantic-role judgment. Provider failures and
unresolved surfaces remain visible. The comparison HTML is an evaluation
artifact only: it is not consumed by `ReviewBrief`, the production review HTML,
or any assessment authority.

## Replay a recorded transport

For an exact offline transport replay, add:

```bash
--llm-shadow-replay path/to/exact-request-replay.json
```

Replay explicitly overrides live provider configuration.

## Safety and data boundary

The shadow request contains bounded canonical candidate IDs, catalog-owned file
and symbol context, directional changed lines, and bounded structural-path
summaries. A request is limited to 40 candidates and a review to three provider
requests. Truncation remains an explicit coverage limit.

The provider output must partition every admitted identity exactly once as
selected, rejected, or insufficient. It may assign an evidence relationship and
semantic role, but never an acceptance conclusion. Unknown identities,
overlapping dispositions, missing dispositions, invalid structured output, and
request-identity drift fail closed.

The transport uses structured JSON, `store: false`, and no tools. RepoDelta
records typed execution state, request identity, usage, deferrals, failures,
coverage limits, and a non-secret policy identity beside the deterministic
report. It does not store raw provider error text or secrets.

The formal HTML remains deterministic. Independent comparison reports are the
only surface where deterministic-only, model-only, shared, rejected,
insufficient, and human dispositions are compared.
