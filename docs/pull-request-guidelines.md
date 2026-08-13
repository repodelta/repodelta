# Pull requests

Title the PR around its responsibility or contract transition. Describe the
following items when they apply to this PR; do not fill non-applicable fields
with template noise:

- parent transformation and this PR's responsibility;
- semantic output, sinks, before/after authority, and selected boundaries;
- each new or changed derived semantic result: provenance, authority scope,
  canonical owner, and authorized semantic dependencies;
- each changed semantic decision's high-risk orthogonal dependency and the
  counterfactual used to test its independence;
- affected producer/consumer contracts and before/after production flow;
- migrations, removals, and retained classified paths;
- any material re-plan: what evidence invalidated the recorded plan and what
  changed in the target, authority, owner, contract, region, or merge evidence;
- counterfactual, contract, and sink-level evidence;
- stable invariants affected by the PR, their current and target enforcement,
  and why that enforcement is sufficient without freezing uncertain semantics;
- unresolved dynamic/external surfaces;
- responsibility closure, contract closure, abandonment safety, and parent
  completion as separate states.

A derived result is not automatically cross-consumer truth. State when its
scope is intentionally consumer-local and why the consumer is allowed to own
that projection. Consumers must not silently produce or re-decide semantics
whose scope is upstream.

Use `Before` and `After` for general state transitions. Use the more specific
`Before topology` and `After topology` headings only when the statements claim
structural topology; generic state prose is preserved but not reclassified.
When a general state statement refers to a concrete file or symbol, put that
identity in a Markdown code span so RepoDelta can focus the Base-side `Before`
or Head-side `After` structure without treating the state prose as proof.

Explain why the resulting tree remains valid if the parent stops permanently.
Unsupported or incomplete semantics must fail closed.

Keep the PR Draft while its responsibility, affected contracts, or a merge gate
is unsettled. Mark it ready only after auditing the final candidate tree. If the
parent remains open, link a stable record owning its remaining obligations and
stop conditions.
