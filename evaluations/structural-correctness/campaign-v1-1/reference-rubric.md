# Campaign v1.1 reference rubric

Reference proposals and verification use the bounded packet, authored Issue/PR
contract, exact pull-request diff, and source identities. They do not consume
RepoDelta's separately stored observation, comparison HTML, or projected focus
membership before the verified reference is frozen. A verifier may be a person
or AI; correctness depends on evidence and isolation rather than identity.

## File overview

- Include a structurally applicable changed file as `changed` when its changed
  symbols belong to the reviewed implementation or verification boundary.
- Include an unchanged file as `retained_bridge` only when its canonical
  relations preserve a required changed-to-changed path.
- Include unchanged adjacent interpretation context as `retained_context` only
  when it is needed to understand the changed boundary.
- Exclude reachable, lexically similar, or repository-near files without one of
  those roles. Keep insufficient evidence unresolved.

## Subject focus

- A direct node implements, constrains, removes, or directly verifies the
  authored subject. A context node is an unchanged or unresolved intermediate
  identity needed to explain a direct node or selected relation.
- A selected exact relation is admitted only when it expresses the subject's
  changed structural path and both canonical endpoints are admitted by the same
  focus.
- Empty resolved focus is valid for non-structural prose, asserted absence of
  change, or an out-of-scope statement. Insufficient bounded evidence remains
  unresolved rather than forcing a mapping.
- Equivalent focuses require identical file membership, node roles, relations,
  and unresolved state.

## Coverage

Coverage describes only the collected surface. A resolved reference can still
have limited traversal coverage when exact diff/source evidence supports the
bounded decision; comparison findings must report that limit and cannot claim
repository-wide completeness.
