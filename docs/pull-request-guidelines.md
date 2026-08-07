# Pull requests

Title the PR around its responsibility or contract transition. Describe:

- parent transformation and this PR's responsibility;
- semantic output, sinks, before/after authority, and selected boundaries;
- affected producer/consumer contracts and before/after production flow;
- migrations, removals, and retained classified paths;
- counterfactual, contract, and sink-level evidence;
- unresolved dynamic/external surfaces;
- responsibility closure, contract closure, abandonment safety, and parent
  completion as separate states.

Use `Before` and `After` for general state transitions. Use the more specific
`Before topology` and `After topology` headings only when the statements claim
structural topology; generic state prose is preserved but not reclassified.

Explain why the resulting tree remains valid if the parent stops permanently.
Unsupported or incomplete semantics must fail closed.

Keep the PR Draft while its responsibility, affected contracts, or a merge gate
is unsettled. Mark it ready only after auditing the final candidate tree. If the
parent remains open, link a stable record owning its remaining obligations and
stop conditions.
