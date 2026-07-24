# Deterministic review projection

The projection layer turns the canonical candidate pool into a small review
slice. It is a view, not another evidence graph.

```text
ReviewBrief
  ├─ statements
  ├─ CandidateBindingSet
  ├─ EvidenceCatalog
  └─ optional StructuralGraphResult
          ↓ references only
     ReviewProjection
       └─ ReviewSlice per R/G
```

## Slice contract

A `ReviewSlice` references:

- its focus `R/G`;
- selected `requirement_claim` binding IDs;
- changed evidence IDs;
- unchanged runtime/test evidence IDs;
- CI evidence IDs;
- structural-path evidence IDs;
- projection-specific missing-candidate diagnostics.

No source text, patch, symbol, path, score, or URL is copied into the slice.
The renderer resolves every ID against the canonical brief.

## Selection

Selection is deterministic:

1. Rank candidate PR claims by score and stable identity.
2. Prefer changed symbol anchors, then changed hunks, then changed-file
   fallbacks.
3. Collect only structural paths referenced by selected changed anchors.
4. Prefer the shortest runtime path and shortest test/mixed path.
5. Include unchanged runtime/test symbols only when they have an existing
   statement binding and occur on a selected path.
6. Bound every group before rendering.

The HTML uses three compact columns:

```text
Issue contract / PR criterion → PR says → Repository facts
```

Edges are labelled as candidate relations, changed facts, structural facts,
or current-head observations. They are never acceptance conclusions.

## Graph-optional behavior

With Codegraph, an exact changed symbol can anchor selected runtime/test paths.
Without Codegraph, the same slice contains its canonical changed-hunk or
changed-file anchor and leaves structural groups empty. CI observations are
independent of Codegraph.

The offline evaluation suite locks both graph-enriched and hunk-fallback
projections to stable IDs.
