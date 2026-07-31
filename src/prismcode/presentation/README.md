# Presentation

## Owns

ID resolution, escaping, link construction, deterministic graph layout, and
HTML/CLI formatting. HTML consumes the projection-owned
`VerificationWorkspace` as its only subject/status/inspection authority.

## Input / output

`ReviewBrief` with canonical `ReviewProjection.verification_workspace` → HTML
or terminal copy.

## Invariants

Missing references fail visibly. The HTML presents one verification accordion,
the projection-owned structural graph, and a collapsed Evidence Appendix.
Accordion headings and expanded claim/observation/assessment details are copied
from one verification workspace; the renderer does not rebuild alignment or
assessment.
The structural delta view resolves the shared canonical graph and focus-overlay
IDs. Its deterministic SVG layout includes only the projection-owned default
change backbone, including its executable edges and separate canonical
ownership hierarchy. The complete support graph remains available to overlays
without being independently reselected here. Operation styling,
isolated-anchor disclosure, canonical structural placement, and client-side
focus highlighting are presentation only. Compound containment consumes only
projection-owned revision-local placements; the renderer never recovers
parentage from paths, names, or node kinds. A Head-observed placement owns the
current visual container when a moved symbol also has a Base-only parent; that
secondary placement remains explicit without duplicating the symbol. Container
roots are layered by projected executable topology, and orthogonal edge routes
consume the resulting node/container geometry. Node labels and links resolve
only the projection-owned canonical display evidence. Focus controls toggle
existing node/edge memberships; a container's own focus is shown as direct
evidence while descendant-only membership is shown as presentation context.
Opening an accordion subject drives the graph focus for its projected overlay.
Controls do not recalculate an association, status, relation, or parentage.
Graph coverage text formats the existing review-level
`StructuralCoverage`; it does not inspect provider diagnostics.

## Must not

Infer CI status, acceptance-source absence, diagnostic taxonomy, statement
purpose, provider coverage, relevance, graph membership, structural relation
truth, transformation status, verification, acceptance, or mergeability. It
must not read raw transformation contract, observation, alignment, or
assessment models after projection.

## Diagnostics

Presentation does not create review diagnostics.

## Extension points

Additional renderers consume the same brief without adding semantic rules.
