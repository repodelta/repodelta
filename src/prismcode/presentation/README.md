# Presentation

## Owns

ID resolution, lossless grouping, escaping, link construction, and HTML/CLI
formatting.

## Input / output

`ReviewBrief` → HTML or terminal copy.

## Invariants

Missing references fail visibly. Both adapters consume the same canonical
overview and coverage facts. G scan-plan copy resolves an upstream plan ID and
does not infer execution or absence. Boundary observations resolve selected
fact IDs and display their typed per-surface coverage without interpreting
candidate matches.
The structural delta view resolves the shared canonical graph and focus-overlay
IDs. Its deterministic SVG layout includes only the projection-owned default
change backbone, including its executable edges and separate canonical
ownership hierarchy. The complete support graph remains available to overlays
without being independently reselected here. Operation styling,
isolated-anchor disclosure, and client-side focus highlighting are presentation only. Focus controls
toggle existing node/edge memberships and display the projection-owned
`StructuralFocusDisposition` when a focus has no visible backbone. Deferred
structural rows resolve the disposition's canonical relation IDs. The
Structure control only hides or shows ownership edges and ownership-only
context nodes. Neither control recalculates an association, disposition,
relation, or parentage. Presentation must not recover parentage from symbol
names, paths, or node kinds.
Standalone changed facts are grouped by the projection's primary, test-support,
and document-support references; presentation never reclassifies a fact from
its path, content, or label.

## Must not

Infer CI status, acceptance-source absence, diagnostic taxonomy, statement
purpose, provider coverage, relevance, graph membership, structural relation
truth, verification, or acceptance.

## Diagnostics

Presentation does not create review diagnostics.

## Extension points

Additional renderers consume the same brief without adding semantic rules.
