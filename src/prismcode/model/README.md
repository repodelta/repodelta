# Model

## Owns

Versioned contracts shared between pipeline stages and their consistency rules.

## Input / output

No transformation. Other stages exchange only the contracts defined here.

## Invariants

- statement role, purpose, kind, and display identity agree;
- each canonical diff relation owns one valid added/removed/replaced shape and
  changed evidence references its relation IDs;
- guardrail scan plans map one-to-one to canonical G statements and preserve
  their query text, executable selectors, and provenance;
- boundary scan observations identify plan, G, revision, coverage, and
  candidate locations without carrying a satisfaction conclusion;
- evidence authority, revision side, operation, role, and changed state agree;
- reference-only views point to canonical IDs.

## Must not

Collect sources, classify paths, route candidates, interpret diagnostics, or
format presentation copy.

## Diagnostics

Contract violations raise `ValueError` at the stage boundary.

## Extension points

Add versioned fields here only when one canonical stage owns their value.
