# Model

## Owns

Versioned contracts shared between pipeline stages and their consistency rules.

## Input / output

No transformation. Other stages exchange only the contracts defined here.

## Invariants

- statement role, purpose, kind, and display identity agree;
- guardrail scan plans map one-to-one to canonical G statements and preserve
  their query text and provenance;
- evidence authority, revision side, operation, role, and changed state agree;
- reference-only views point to canonical IDs.

## Must not

Collect sources, classify paths, route candidates, interpret diagnostics, or
format presentation copy.

## Diagnostics

Contract violations raise `ValueError` at the stage boundary.

## Extension points

Add versioned fields here only when one canonical stage owns their value.
