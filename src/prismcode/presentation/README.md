# Presentation

## Owns

ID resolution, lossless grouping, escaping, link construction, and HTML/CLI
formatting.

## Input / output

`ReviewBrief` → HTML or terminal copy.

## Invariants

Missing references fail visibly. Both adapters consume the same canonical
overview and coverage facts. G scan-plan copy resolves an upstream plan ID and
does not infer execution or absence.

## Must not

Infer CI status, acceptance-source absence, diagnostic taxonomy, statement
purpose, provider coverage, relevance, verification, or acceptance.

## Diagnostics

Presentation does not create review diagnostics.

## Extension points

Additional renderers consume the same brief without adding semantic rules.
