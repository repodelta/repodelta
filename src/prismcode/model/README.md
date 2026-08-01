# Model

## Owns

Versioned contracts shared between pipeline stages and their consistency rules.

## Input / output

No transformation. Other stages exchange only the contracts defined here.

## Invariants

- statement role, purpose, kind, and display identity agree;
- transformation claims retain PR authority, typed kind, T/CC identity, source
  state, and provenance without carrying observed or assessed state;
- transformation predicates retain their owning claim, explicit selector kind,
  expected revision state, ordered values, and provenance; missing explicit
  selectors remain typed diagnostics rather than inferred identities;
- transformation subject selection partitions every predicate selector into
  exact canonical changed-structure matches or one typed no-match diagnostic;
- transformation structural closure preserves every T/CC claim once, partitions
  every seed-owned collected path into retained or explicitly deferred
  identities, and references only canonical relation and ownership facts;
- observed transformation references canonical fact identities and Base/Head
  provenance without carrying authored claims or assessment state;
- transformation alignment references only typed claims and canonical observed
  or closure facts, preserves association reasons, and carries no selection or
  assessment state;
- each canonical diff relation owns one valid added/removed/replaced shape and
  changed evidence references its relation IDs;
- closure scan plans map one-to-one to eligible G/removal/negative-completion
  statements and preserve query text, executable selectors, and provenance;
- closure scan observations identify plan, statement, revision, coverage, and
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
Shared canonical structural symbol/path reference accessors also live here so
facts, convergence, and projection do not recreate identity rules.
