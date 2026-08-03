# Pull requests

Title the PR around its semantic responsibility transition, not files or
mechanisms. Record:

- parent transformation and this PR's child responsibility;
- output, scope, sinks, and authority / admission / proof / consumption;
- selected region, boundaries, and before/after topology;
- migrations, removals, and classified alternate paths;
- counterfactuals, completion evidence, and coverage limits;
- open parent obligations and unresolved dynamic surfaces;
- responsibility closure, abandonment safety, and parent completion separately.

Explain why the tree remains correct and meaningful if the parent stops.
Unsupported semantics must fail closed. Do not depend on future wiring, call a
non-authoritative path canonical, or claim unobserved coverage.

Keep the PR Draft while discovery, scope, or either merge gate is open. Mark it
ready only after the final candidate tree passes pre-merge census and both
responsibility closure and abandonment safety are true.

If parent completion is false, link a stable issue, plan, or design record that
owns the remaining obligations and stop conditions.
