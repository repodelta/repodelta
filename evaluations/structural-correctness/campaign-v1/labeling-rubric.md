# Campaign v1 human-labeling rubric

This rubric is frozen before any campaign observation is opened. Human labels
judge the bounded candidate universe in each packet against the authored Issue
and PR contract, the pull-request diff, and source identities. They do not try
to reproduce RepoDelta's selection algorithm.

## File overview

- Include a structurally applicable changed file as `changed` when its changed
  symbols belong to the reviewed implementation or verification boundary.
- Include an unchanged file as `retained_bridge` only when its canonical
  relations are needed to preserve a continuous changed-to-changed path.
- Include an unchanged file as `retained_context` only when it is directly
  adjacent structural context needed to interpret the changed boundary.
- Exclude reachable, lexically similar, or repository-near files that do not
  satisfy one of those roles.
- Use `unresolved` when the packet or recorded coverage is insufficient to
  judge the file role; do not convert truncation into exclusion.

## Subject focus

- A `direct` node is a changed anchor whose observed change implements,
  constrains, removes, or directly verifies the authored subject.
- A `context` node is an unchanged or intermediate identity needed to explain
  a direct node or a selected exact relationship. Reachability alone is not
  context.
- A direct file contains at least one direct node, or is itself the most
  precise available direct identity. A context file contains only context
  nodes for that subject.
- Include an exact relation only when its canonical endpoints are admitted and
  that relation is needed to express the subject's changed structural path.
- An empty resolved focus is correct for non-structural prose, a guardrail that
  asserts absence of change, an out-of-scope statement, or an authored claim
  with no matching bounded structural identity.
- Mark a focus `unresolved` only when bounded evidence or coverage prevents a
  human judgment. Do not force a mapping merely because a subject exists.
- Mark focuses equivalent only when their file membership, node roles,
  relations, and unresolved state are exactly equal. Similar prose is not
  structural equivalence.

## Independence and coverage

Label files, nodes, and relations from the packet and source contract before
opening the separately stored observation. Packet candidates bound what can be
judged; they do not prove relevance. Coverage states describe only the observed
collection surface and never establish repository-wide completeness.
