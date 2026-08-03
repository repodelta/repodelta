# Commit messages

Commits in branches or Draft PRs are implementation checkpoints; merge
acceptance applies to the final candidate tree. Keep commits buildable when
repository policy requires; reorder or squash exploratory checkpoints before
delivery.

Describe the responsibility transition, not only modified files:

```text
<type>(<responsibility>): <imperative behavior or authority transition>
```

Examples:

- `refactor(transformation-topology): make closure authoritative`
- `fix(review-projection): prevent alignment from adding members`

Use the body when useful for migrated consumers, removed paths, and preserved
boundaries. Do not call an intermediate producer canonical or imply that an
exploratory commit is merge-safe.
