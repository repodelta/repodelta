# Campaign v1.1 findings after the provenance-separated rerun

## Decision boundary

The frozen v1.1 references remain unchanged and remain the semantic reference
authority. This rerun changes only the observation schema and its downstream
consumers: `asserted`/`matched` stay direct, while `suggested`, `context`, and
`unresolved` remain separately observable. It does not relabel references or
change candidate generation, convergence, or structural selection.

## Selection invariance

All eight regenerated packets are byte-for-byte identical to the frozen
packets. The committed
[`selection-invariance-baseline.json`](selection-invariance-baseline.json)
also checks, for all 113 focuses, that selected file IDs, selected node IDs,
exact relation IDs, and disposition state are unchanged from the pre-#289
observation. This is a direct membership check, not an inference from packet
identity.

## Rerun result

The following are comparison false-inclusion/false-exclusion counts over the
frozen candidate/reference surface, not raw membership totals:

- File overview: **34 / 0** false inclusions/exclusions; **0** file-role
  disagreements.
- Selected focus-file membership: **458 / 77** false
  inclusions/exclusions.
- Selected focus-node membership: **1,453 / 176** false
  inclusions/exclusions.
- Exact relation IDs: **684 / 49** false inclusions/exclusions.

The separated dimensions are:

- Claimed-direct nodes: **352 / 289** false inclusions/exclusions; claimed
  direct files: **217 / 169**.
- Structural-context nodes: **761 / 12** false inclusions/exclusions;
  structural-context files: **151 / 3**. File-level context is disjoint from
  direct/suggested/unresolved file categories; member-level provenance remains
  available in the HTML inspection.
- Suggestions observed: **465 node suggestions** and **199 file suggestions**
  across **43 resolved focus rows**. Suggestions are reported as an epistemic/provenance
  behavior; they are not promoted to direct mappings and are not relabeled as
  context.
- Production unresolved memberships remain a separate observed dimension in
  the comparison HTML. They are reported, not compared to frozen direct/context
  labels or silently folded into structural context.

The legacy binary role comparison is retained only as a diagnostic: 1,101 / 289
node false inclusions/exclusions and 12 role disagreements. It is not the
selected-membership result and is not an optimization target.

Coverage remains 3 complete for admitted direct seeds, 78 limited by truncated
admitted seeds, 29 correctly empty, 0 unknown, and 3 reference-unresolved.

## Interpretation

The invariant selected universe confirms that preserving provenance downstream
did not change what the structural pipeline selected. The new evaluator now
answers separate questions: did RepoDelta select the right member universe,
which members did it claim as direct, what suggestions did it expose, and which
members did it present as structural context? A heuristic suggestion may be
semantically direct in the frozen reference while RepoDelta still correctly
refuses to claim that as a deterministic direct mapping.

Consequently, the rerun is evidence for a truthful provenance boundary, not an
accuracy improvement claim. Any future association or closure change must be
evaluated against the selected-membership invariant and the four dimensions
separately. No new campaign or reference relabeling is introduced here.

## Coverage interpretation

Most non-empty focuses have limited traversal coverage. False-exclusion counts
remain bounded to the collected candidates and cannot establish repository-wide
recall. The unchanged comparison counts still show the existing over-selection
direction on the frozen surface; the separated direct/context/suggestion counts
explain how that over-selection is represented without collapsing provenance.
