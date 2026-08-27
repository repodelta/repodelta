# Verification record

## Source and corpus integrity

- Pre-v1.2 protocol source pinned to `479d48c1e92443d4705cbdf55466cc83094217b1`,
  the base of PR #272.
- Candidate v1.2 source pinned to `ceefd9c26f8964668df8b7926b0b799da7080ee6`,
  the merged `main` tree containing PR #272.
- Seven cases are present: four source-backed historical/positive controls and
  three declared synthetic controls; two synthetic controls are held out.
- The evaluator checks all profile source markers with `git show` before
  scoring. On a shallow CI checkout it fetches only the pinned commit, then
  performs the same exact source check; if that fetch fails, evaluation fails
  closed.

## Commands

```bash
python evaluations/protocol-v1-2/evaluate.py
PYTHONPATH=src python -m pytest -q tests/test_protocol_v1_2_evaluation.py
git diff --check
```

Observed results:

```text
replay acceptance: true
protocol evaluation test: 1 passed
git diff --check: clean
```

## Responsibility closure

- **Responsibility closure:** complete for the protocol decision-replay
  artifact and its machine-derived summary.
- **Contract closure:** complete for corpus schema, pinned profiles, source
  marker validation, metrics, and acceptance gates.
- **Abandonment safety:** complete; this path is evaluation-only and does not
  change runtime/product or merge authority.
- **Parent completion:** Issue #270 remains open until this evaluation PR is
  reviewed and merged; live-agent execution quality remains an explicit later
  study rather than an unrecorded assumption.
