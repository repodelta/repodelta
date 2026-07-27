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
IDs. Its deterministic SVG layout, operation styling, isolated-anchor
disclosure, and client-side focus highlighting are presentation only. Focus
controls toggle existing node/edge memberships and never recalculate an
association or relation.

Canonical ownership edges are currently contract input but are not yet laid
out as SVG hierarchy. The hierarchy renderer atom will consume those IDs
directly; presentation must not recover parentage from symbol names or paths.

## Must not

Infer CI status, acceptance-source absence, diagnostic taxonomy, statement
purpose, provider coverage, relevance, graph membership, structural relation
truth, verification, or acceptance.

## Diagnostics

Presentation does not create review diagnostics.

## Extension points

Additional renderers consume the same brief without adding semantic rules.
