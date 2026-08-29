# Identifier specificity shadow

This is an evaluation-only result for [Issue #302](https://github.com/repodelta/repodelta/issues/302). It does not change RepoDelta's production association, structural projection, assessment, or the frozen v1.1 reference.

The eight frozen v1.1 samples contain 180 `exact_identifier` candidate rows.
The historical packets do not include raw diff text, so all probe artifacts are
marked `origin_completeness: partial`; missing origin is recorded as
`unobserved`, never guessed as canonical.

The live probe now follows `structural_change.change_relation_ids` to the
canonical `change_relation` evidence item before assigning `diff_text`. If
that identity or preview is absent it records `signature_unattributed` or
`unobserved` and remains partial; it never assigns an origin by matching a
summary or path heuristically.

| Direct-node policy | False inclusions | False exclusions |
| --- | ---: | ---: |
| Current observed policy | 38 | 212 |
| No suffix-only terms | 38 | 212 |
| Canonical origin + low fanout | 0 | 227 |
| Qualified-name token present | 0 | 227 |
| Full token + low fanout | 0 | 227 |
| Canonical token unique match | 0 | 227 |

The 38 current direct false inclusions are split into 31 requirements and 7
guardrails. The strict shadow removes those false inclusions, but introduces 15
additional direct false exclusions. This is a policy trade-off, not proof that
the strict policy should be promoted: the comparison projects only observed
direct admission and does not replay selected membership, structural context,
relation groups, closure, or semantic interpretation.

The `no_suffix` shadow is identical to the current policy on this historical
sample. That means suffix aliases alone do not explain the observed direct
false inclusions. The evidence supports the narrower hypothesis that broad
lexical identifier overlap is being treated as direct authority, but the
historical packet cannot separate qualified-name, path, and changed-line origins
for every row.

The orthogonal qualified-name-origin and low-fanout shadows have the same
per-focus direct membership and aggregate result on this sample: each removes
all 38 false inclusions while adding 15 false exclusions. The frozen replay
therefore does not distinguish qualified-name origin from exact-association
fanout as the operative discriminator; the two features are observationally
confounded here. Uniqueness adds no additional separation beyond those strict
shadows. The result remains a direct-only projection over partial historical
origin data, not a production policy recommendation. A production fix should
therefore wait for a live probe with raw evidence origins and a semantic-recall
design, rather than deleting the shared high-recall identifier primitive.

The `canonical_resolution` count is repository-wide: it counts changed-symbol
qualified-name token occurrences across the packet, not only symbols eligible
for the current focus. Likewise, `fanout` is the number of candidate nodes in
the focus's recorded `exact_identifier` rows sharing the term. These are bounded
shadow measurements, not a production canonical-identity resolver or a replay
of the full candidate universe.
