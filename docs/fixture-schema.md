# Analysis fixture v3

An offline fixture is an envelope around the same conclusion-free
`ReviewSourcePacket` used by live GitHub ingestion:

```json
{
  "schema_version": "analysis_fixture.v3",
  "source_packet": { "schema_version": "review_source_packet.v1" },
  "requirements": [],
  "evidence": []
}
```

`requirements` are optional explicit obligation statements. Each may include
`role` (default `obligation`) and `authority` (default `provided`). When the
array is empty, the analyzer applies the normal semantic authority hierarchy:
linked-Issue criteria first, then explicit PR Acceptance Criteria,
Requirements, Definition of Done, or Success Criteria. Goals, claims, and
intent remain separate; a PR title never becomes a requirement.

`evidence` contains supplied facts that are normalized into the same canonical
`EvidenceCatalog` as changed hunks, exact symbols, structural paths, and
execution observations. An item may list `statement_ids` to record an explicit
provided association. That association affects retrieval ordering only; it
does not assert implementation, verification, or acceptance.

Loading fails when the packet revision is inconsistent or supplied evidence
names an unknown explicit requirement. Fixtures support deterministic replay;
they are not proof of source authenticity.
