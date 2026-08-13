# Campaign v1 proposed result

This corpus compares the canonical structural overview with independently
prepared, packet-bound reference decisions for eight real pull requests. The
decisions remain proposed until the designated maintainer reviews and merges
their pull request. Merge records human acceptance; generation by an agent does
not.

## Result

| Surface | Proposed result |
| --- | ---: |
| File candidates | 224 |
| File matches | 192 |
| File false inclusions | 24 |
| File false exclusions | 0 |
| File role disagreements | 8 |
| Focus subjects | 113 |
| Coverage-limited/unresolved focuses | 47 |
| Scored focuses | 66 |
| Exact focus memberships | 21 |
| Focus false-inclusion memberships | 250 |
| Focus false-exclusion memberships | 42 |

These counts do not support adding explanatory provenance as the first product
change. Only 21 of 66 scored focuses have exact file membership, and large
false-inclusion counts remain even after coverage-limited subjects are removed
from exact scoring. The next correction should therefore tighten the canonical
focus membership contract and make coverage limits truthful at the focus sink.

Provenance remains useful after membership is corrected: it can explain exact
symbol, explicit file, structural closure, and unresolved origins. Large-change
clustering is deferred because grouping an inaccurate focus would make the
error easier to read rather than make the result correct. Parent-Issue workflow
traceability remains an independent later capability.

## Review protocol

Review `decisions.json` using only the frozen packet, linked PR/Issue, and diff.
Do not use `observations/` or `results/` to revise labels unless the revision is
recorded as adjudication rather than blind labeling. `prepare_labels.py`
mechanically converts reviewed paths to packet identities. `summarize.py`
recomputes `results/summary.json`; the HTML files are standalone views of the
same admitted packet, labels, and observation.

The full per-PR and total counts are in `results/summary.json`.
