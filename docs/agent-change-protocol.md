# Agent Change Protocol

Use this protocol for changes affecting behavior, authority, contracts,
data flow, or multiple components.

## 1. Define

Identify the semantic output, execution scope, and production sinks.
Start from the observable responsibility, not the expected files or new
symbols.

## 2. Census

Using CodeGraph and available code, test, runtime, and documentation
evidence:

- trace backward from sinks to producers and decision paths;
- trace forward from the target authority to actual consumers;
- search laterally for paths that independently produce, write, override,
  project, or reconstruct the same output.

Identify candidate authorities, the effective current authority,
consumers, writers, projections, tests, classified alternatives,
unclassified bypasses, and unresolved dynamic surfaces.

## 3. Select and plan

Choose the smallest region that can complete the responsibility and
authority transition. Define:

- entry and exit boundaries;
- input and output contracts;
- before and target topology;
- preserved external contracts;
- producers, consumers, projections, and tests to migrate;
- paths to remove or classify;
- completion conditions and coverage limits.

If the region is not closed, recursively expand to the smallest enclosing
region that is.

## 4. Execute

Treat the selected region as one transformation. Internal responsibilities,
contracts, and topology may be moved, split, merged, or replaced.

If another authority, consumer, bypass, or boundary dependency appears,
stop local patching, expand the region, and update the plan.

## 5. Audit

Verify that:

- the resulting checkout has been re-synced or rebuilt in CodeGraph, and the
  backward, forward, and lateral census has been repeated against that tree;
- the target authority controls the intended production sinks;
- relevant production consumers have migrated;
- no unclassified path independently decides the same output;
- alternate paths satisfy their declared classification;
- external contracts are preserved or explicitly changed;
- unresolved and unobserved surfaces are reported.

Allowed classifications include dormant, shadow, compatibility,
migration, rollback, experiment, annotation, and projection.

## Planning output

- Semantic output and execution scope:
- Effective authority before:
- Candidate competing authorities:
- Production sinks and consumers:
- Selected closed region and boundaries:
- Before → target topology:
- Migrations, removals, and classifications:
- Preserved or changed external contracts:
- Completion evidence:
- Coverage limitations:
