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

`source_packet` is conclusion-free. `requirements` are explicit source assertions.
`evidence_hints` are separate annotations with provenance. Loading fails when the packet
revision is inconsistent or a hint names an unknown requirement.

When `requirements` is empty, the analyzer extracts acceptance criteria from a
`linked_issue`/`ticket` source record (falling back to the PR body). The packet may contain
current-head `verification_observations`; hints bind a requirement to observations by exact
ID and cannot turn unrelated green CI into a passing requirement.

Fixtures are for deterministic replay, not proof of source authenticity. The next golden
vertical slice will replace the current small PR #574 example with a complete source packet.
