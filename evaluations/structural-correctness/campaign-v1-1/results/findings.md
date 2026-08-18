# Campaign v1.1 findings after the #289 observer rerun

## Decision boundary

The frozen v1.1 references remain the authority. This rerun evaluates the
current RepoDelta observation semantics against those references; it does not
relabel the references, change candidate generation, or change convergence and
structural selection.

## Selection invariance

All eight regenerated v1.1 packets are byte-for-byte equivalent to their
frozen packets. The selected candidate universe is therefore unchanged by
#289. This confirms that the membership-contract work did not silently change
retrieval or selection.

## Rerun result

- 8 real pull requests, 110 resolved focuses, and 3 unresolved focuses.
- File overview: 34 false inclusions, 0 false exclusions, and 0 role
  disagreements.
- Focus nodes: 1,453 false inclusions, 176 false exclusions, and 125
  direct/context role disagreements (14 before the observer rerun).
- Exact relations: 684 false inclusions and 49 false exclusions.
- Focus coverage: 3 complete for admitted direct seeds, 78 limited by
  truncated admitted seeds, 29 correctly empty, 0 unknown, and 3
  reference-unresolved.

The updated observations and comparison HTML are the committed artifacts in
this directory. The machine-readable totals are in
[`summary.json`](summary.json).

## Interpretation

The unchanged false-inclusion and false-exclusion counts are expected: #289
preserves the selected member universe. Its production change is a truth
boundary: heuristic association and reachable structure are no longer
serialized as direct mappings.

The role-disagreement increase is material merge evidence. The frozen rubric
defines a direct node by whether it implements, constrains, removes, or
directly verifies the authored subject. The new `is_direct_mapping` property
derives directness only from `asserted` and `matched`, so many previously
direct heuristic anchors now compare as context. This shows that provenance
confidence (`asserted`/`matched`/`suggested`) and semantic reference role
(`direct`/`context`) are not interchangeable dimensions for this evaluator.

Therefore this rerun validates selection invariance and context non-promotion,
but does not validate an accuracy improvement. The next correctness decision
must keep those dimensions separate—either by preserving semantic directness
alongside provenance confidence, or by defining an explicit comparison mapping
without treating heuristic provenance as acceptance proof. No new campaign or
reference relabeling is introduced here.

## Coverage interpretation

Most non-empty focuses have limited traversal coverage. False-exclusion counts
remain bounded to the collected candidates and cannot establish repository-wide
recall. The unchanged false-inclusion counts still show the existing
over-selection direction on the frozen surface.
