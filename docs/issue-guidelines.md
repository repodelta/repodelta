# Issues

Use an Issue as the requirement-source contract, not as a copy of the future
PR transition record. Describe the result and review boundary without assuming
the implementation.

## Focused Issue before PR

For new non-trivial RepoDelta work, create one focused Issue before opening its
implementation PR. That Issue is the requirement-source contract, and the PR
that implements it has exactly one GitHub closing reference:
`Closes #<focused-issue>`.

A focused Issue has at most one active implementation PR, including a Draft.
Other Issues do not supply focused implementation ownership; parent or
hierarchy semantics are outside this guidance.

For a RepoDelta Issue, use the canonical Markdown ATX headings and levels shown
below (`##`, not bare text labels):

```text
## Goal
## Requirements
## Guardrails
## Verification expectations
## Scope
## Out of scope
## Uncertainties
```

`Requirements`, `Acceptance criteria`, `Definition of done`, and `Success
criteria` remain accepted requirement aliases; prefer `## Requirements` for
consistent authoring. The parser continues to accept established compatible
ATX headings and aliases for backward compatibility. Bare labels such as
`Requirements` are context, not a formal section. RepoDelta reports a
source-backed warning when it sees a contract-looking bare label, but never
promotes its contents by inference.

Write one independently reviewable semantic obligation per list item. Goals
explain intent and guardrails constrain the solution; neither is a requirement.

Keep optional sections optional. Use Scope for included responsibility and Out
of scope for explicit exclusions. Verification expectations name the kind of
evidence required without claiming that evidence already exists. Uncertainties
record dynamic or external surfaces that cannot yet be covered. `Uncertainties`
is canonical authored context, not an R/G/V field or a PR T/CC declaration.

Do not put PR-level `Before`, `After`, authority transitions, migrations,
completion evidence, closure state, or `Completion conditions` in the Issue.
Those describe the implemented transition and belong in the PR. A PR may map
its transformation and completion claims to Issue requirements, but must not
copy the requirements as a second source of truth.

Mention a repository path or symbol only when it is part of the required
contract, not merely the expected implementation. Do not retrospectively create
a focused Issue for a PR that predates this rule or rewrite an older context
reference as ownership.
