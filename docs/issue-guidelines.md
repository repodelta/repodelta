# Issues

Use an Issue as the requirement-source contract, not as a copy of the future
PR transition record. Describe the result and review boundary without assuming
the implementation.

Prefer these headings when applicable:

```text
Goal
Requirements
Guardrails
Verification expectations
Scope
Out of scope
Uncertainties
```

`Requirements`, `Acceptance criteria`, `Definition of done`, and `Success
criteria` are requirement aliases; prefer `Requirements` for consistent
authoring. Write one independently reviewable semantic obligation per list
item. Goals explain intent and guardrails constrain the solution; neither is a
requirement.

Keep optional sections optional. Use Scope for included responsibility and Out
of scope for explicit exclusions. Verification expectations name the kind of
evidence required without claiming that evidence already exists. Uncertainties
record dynamic or external surfaces that cannot yet be covered.

Do not put PR-level `Before`, `After`, authority transitions, migrations,
completion evidence, closure state, or `Completion conditions` in the Issue.
Those describe the implemented transition and belong in the PR. A PR may map
its transformation and completion claims to Issue requirements, but must not
copy the requirements as a second source of truth.

Mention a repository path or symbol only when it is part of the required
contract, not merely the expected implementation. An implementation PR may
exist without an Issue when it carries a valid standalone transformation
contract; do not invent Issue requirements after the fact.
