# Pull requests

Title the PR around the semantic responsibility or contract transition.

Record:

- parent transformation and this PR's responsibility;
- semantic output and production sinks;
- responsibility before and after;
- selected region and boundaries;
- affected observed producer/consumer contracts;
- migrations, removals, and retained classified paths;
- before/after production flow;
- counterfactual, contract, and sink-level evidence;
- unresolved dynamic or external surfaces;
- responsibility closure, boundary-contract closure, abandonment safety, and
  parent completion separately.

Explain why the resulting tree remains correct and meaningful if the parent
stops permanently. Unsupported or incomplete semantics must fail closed.

Keep the PR Draft while the responsibility, affected contracts, or any merge
gate remains unsettled. Mark it ready only after the final candidate tree passes
the pre-merge audit. If the parent remains open, link a stable record that owns
its remaining obligations and stop conditions.
