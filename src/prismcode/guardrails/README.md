# Guardrails

## Owns

Canonical, source-backed scan plans compiled one-to-one from authoritative G
statements.

## Input / output

Canonical guardrail `Requirement`s → `GuardrailScanPlanSet`.

## Invariants

Each G owns exactly one stable plan targeting the PR head and repository root.
Every plan preserves the complete guardrail text and source provenance and
declares the conservative path, file-content, and symbol-name scan surfaces.

## Must not

Read the checkout, execute scans, set budgets, emit evidence or absence facts,
associate changed code, or infer guardrail satisfaction.

## Diagnostics

Planning itself is total for canonical G statements. Downstream routing
distinguishes an available plan with no execution fact from a non-applicable
non-guardrail focus.

## Extension points

Bounded scan providers consume these plans and return separately typed facts
with explicit revision and coverage.
