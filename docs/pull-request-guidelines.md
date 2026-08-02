Write PR titles around the semantic responsibility transition, not only
the implementation mechanism or modified files.

In the PR description, include:

- semantic output and execution scope;
- selected responsibility-closed region and its boundaries;
- effective production authority before and after;
- before/after topology;
- migrated producers, consumers, projections, and tests;
- removed or classified alternate paths;
- preserved and changed external contracts;
- completion evidence;
- unresolved dynamic surfaces and coverage limitations.

Classify retained alternate paths as dormant, shadow, compatibility,
migration, rollback, experiment, annotation, or projection.

Do not call a producer or model canonical unless it controls the
production output in the resulting repository state. Do not claim that no
competing path exists beyond the available evidence.