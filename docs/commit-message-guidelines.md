# Commit messages

Commits in a branch or Draft PR are checkpoints; merge acceptance applies to
the final tree. Squash exploratory checkpoints when policy permits.

Name the responsibility or contract transition, not the edited files:

```text
<type>(<responsibility>): <imperative transition>
```

Examples:

- `refactor(verification-identity): unify selector and observation contracts`
- `fix(topology-proof): require ordered edge witnesses`
- `refactor(review-projection): consume canonical membership directly`

When useful, mention migrated endpoints, changed boundaries, removed bypasses,
and preserved contracts. Never call unconsumed or exploratory code canonical.
