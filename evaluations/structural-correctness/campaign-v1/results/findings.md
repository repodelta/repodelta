# Campaign v1 findings

The frozen human labels and separately generated canonical observations show
that the next investment must be correction of the underlying focus projection,
not richer provenance labels, workflow semantics, or large-change clustering.
This conclusion is evaluation-only and does not change a production assessment.

## Result

The eight-PR sample contains 110 resolved and 3 human-unresolved focus
judgements. The default overview had 34 false file inclusions, no false
exclusions, and no role disagreements. Focus projections had 1,458 false node
inclusions, 170 false node exclusions, 13 node-role disagreements, 684 false
exact-relation inclusions, and 49 false exact-relation exclusions. Detailed,
machine-checked totals are in [`summary.json`](summary.json); each PR also has a
standalone comparison report in this directory.

Two negative controls bound the conclusion. PR #245, a documentation-only
change, correctly produced an empty structural result. PR #240's 100-file
mechanical-migration overview matched the human file set, while three broad
focuses remained human-unresolved and the resolved focuses still over-selected
nodes. Structural collection can therefore produce useful overview truth; the
dominant failure is focus membership rather than universal collection failure.

## Observed responsibility failures

The counterexamples identify two independent upstream failure classes:

1. **Direct association is too permissive for generic authored language.**
   `routing/focus_anchors.py` admits `exact_identifier` and
   `distinctive_phrase` matches as direct changed anchors. Corpus-relative
   distinctiveness does not establish that a symbol implements, constrains,
   removes, or verifies the selected subject. In PR #262, G5 is an out-of-scope
   statement about evidence collection and LLM behavior; the canonical result
   projected 31 nodes where the frozen human label is empty. In PR #240, broad
   migration wording similarly admitted large direct sets.
2. **Closure preserves reachability without a necessary-context contract.**
   `convergence/structural.py` unions selected paths and every relation change
   whose endpoints are in the resulting relevant-node set.
   `projection/build.py` then adds placement and ownership ancestors and labels
   nodes without a selected evidence relation as `intermediate`. That preserves
   graph continuity, but it cannot distinguish a necessary bridge from merely
   reachable or containing structure. PR #235 T7 had the expected direct nodes
   plus 43 false context nodes; PR #238 T2 and T3 each added 39 context nodes.

The renderer is downstream of both decisions and correctly exposes the
canonical overlay it receives. Changing HTML filtering would create a second
semantic authority and hide, rather than repair, these errors.

## Recommended follow-up boundaries

Open production work as separate responsibility-closed changes:

- tighten direct-anchor admission with counterexamples for generic lexical
  overlap while preserving exact authored identifiers and explicit provider
  associations;
- define and enforce a minimal necessary-context contract for structural paths,
  placements, and ownership, with retained-bridge sink evidence;
- rerun this frozen campaign after each correction and require improvement at
  file, node-role, and exact-relation levels independently.

Only after membership is truthful should provenance UI, large-change
clustering, or workflow traceability become the next investment.
