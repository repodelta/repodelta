# Commit messages

Commits within a branch or Draft PR are implementation checkpoints. Merge
acceptance is evaluated against the final candidate tree. Squash exploratory
checkpoints before delivery when repository policy permits.

Describe the responsibility or contract transition, not only modified files:

```text
<type>(<responsibility>): <imperative transition>
```

Examples:

- `refactor(verification-identity): unify selector and observation contracts`
- `fix(topology-proof): require ordered edge witnesses`
- `refactor(review-projection): consume canonical membership directly`

When useful, state migrated producers or consumers, updated boundaries,
removed mappings or bypasses, and preserved external contracts. Do not call
exploratory or unconsumed code canonical or merge-safe.
