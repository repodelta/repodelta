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

Fixtures are for deterministic replay, not proof of source authenticity. The next golden
vertical slice will replace the current small PR #574 example with a complete source packet.
