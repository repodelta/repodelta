# Structural focus attribution findings

Campaign v1.2 explains the memberships already emitted by the canonical focus
projection. It does not change selection, assessment, or HTML. The eight frozen
packets and observations are byte-equivalent to campaign v1.1 inputs, and all
3,571 observed node and exact-relation memberships have a supported production
path.

## What the counterfactuals show

The replay removes a membership only when every recorded path to it depends on
the disabled producer class. It therefore measures dependency on existing
producers; it does not predict memberships that a redesigned producer might add.

| Disabled producer | Affected subjects | Main observed trade-off |
| --- | --- | --- |
| `structural_path` | R, G, T | Removes 495 node false inclusions while adding 10 false exclusions. This is the strongest cross-subject signal that reachable closure is being admitted too broadly. |
| `distinctive_phrase` | R | Removes 516 node false inclusions but adds 79 false exclusions. Phrase evidence is both a major source of recall and a major source of over-selection, so deleting it is not a safe correction. |
| `claim_bridge` | R, G | Most visible for G: 183 fewer node false inclusions at the cost of 12 false exclusions. Requirement and guardrail association needs separate policy rather than one global threshold. |
| `transformation_selector` | T | Removes every observed T node and relation, while adding 29 node and 6 relation false exclusions. T/CC has an independent root authority and must not be corrected through R/G association rules. |
| `placement_ancestor` / `ownership_ancestor` | R, G, T | Together explain only 41 false-included nodes in this sample and cause no additional false exclusions when removed. They are secondary context expansion, not the primary defect. |
| `exact_relation` | R, G, T | Removes all observed exact relations and exposes 53 additional relation false exclusions. Relation selection is a separate correctness surface from node membership. |
| `relation_endpoint` | none | Every endpoint in this sample has another supported path. Disabling this producer alone changes no membership. |

Completion conditions have no observed false inclusions in this campaign and no
counterfactual changes. That is absence of evidence in three resolved CC cases,
not evidence that CC behavior is generally correct.

## Decision

The next production change should target how structural paths promote nodes
from reachable closure into focus membership. Direct association roots must be
preserved, while path-derived nodes need an explicit context boundary and
relation-aware admission rule. Phrase and claim-bridge matching should remain
separate inputs until that downstream expansion is corrected; otherwise a root
matching change would trade away confirmed recall while leaving the common
closure defect unresolved.

R/G and T/CC must remain distinct authorities. The same context-boundary model
may be shared, but requirement convergence and transformation selectors must
retain separate entry contracts and evaluation rows.

## Limits

- The references cover eight real RepoDelta pull requests, not arbitrary
  repositories or languages.
- Counterfactual replay only removes recorded paths; it does not rerun candidate
  generation or estimate newly discoverable evidence.
- Equivalent producer paths are intentionally preserved, so a producer may have
  no observable effect when another path independently admits the same member.
- These findings justify the next focused experiment, not an immediate semantic
  change to the production projection.
