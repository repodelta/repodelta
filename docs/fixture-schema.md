# Analysis fixture v2

An offline fixture is an envelope around the same `ReviewSourcePacket` used by live GitHub
ingestion:

```json
{
  "schema_version": "analysis_fixture.v2",
  "source_packet": { "schema_version": "review_source_packet.v1" },
  "requirements": [],
  "evidence_hints": []
}
```

`source_packet` is conclusion-free. `requirements` are explicit obligation
statements and may include `role` (default `obligation`) and `authority`
(default `provided`).
`evidence_hints` are separate annotations with provenance. Their legacy inline
`implementation` objects are converted once by the fixture loader into
deterministically identified provided evidence; the resulting hints retain
only canonical evidence IDs. Loading or analysis fails when the packet revision
is inconsistent, a hint names an unknown requirement, or a hint references an
unknown evidence ID.

When `requirements` is empty, the analyzer applies the semantic authority
hierarchy: linked-Issue criteria first, then explicit PR Acceptance
Criteria/Requirements/Definition of Done as provisional obligations. Goals,
claims, and intent are retained separately; a PR title never becomes a
requirement. The packet may contain current-head `verification_observations`;
hints bind a requirement to observations by exact ID and cannot turn unrelated
green CI into a passing requirement.

Fixtures are for deterministic replay, not proof of source authenticity. The next golden
vertical slice will replace the current small PR #574 example with a complete source packet.
