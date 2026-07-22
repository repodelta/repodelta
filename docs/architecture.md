# Open-core boundaries

PrismCode has one canonical path:

```text
fixture or GitHub
  -> ReviewSourcePacket
  -> deterministic criteria extraction + optional EvidenceHints
  -> DeterministicAnalyzer
  -> ReviewBrief
  -> HTML renderer
```

## Authority rules

1. Adapters collect facts. `ReviewSourcePacket` contains source records, changed files,
   revisions, collection diagnostics, and metadata; it contains no review conclusion.
2. `Requirement` is a source assertion. It cannot contain implementation, verification,
   gaps, or status.
3. Fixture or provider evidence enters through `EvidenceHint`. A hint identifies evidence
   and provenance but cannot declare an implementation status.
4. `DeterministicAnalyzer` is the only status authority. It emits separate implementation
   and verification assessments.
5. Renderers consume `ReviewBrief` and never infer or upgrade an assessment.

## Packet revisions

`packet_revision` is a deterministic SHA-256 consistency digest over the semantic packet
content. It detects accidental corruption or content/revision mismatch. It is not a
signature and does not prove GitHub origin or resist a party that can rewrite both content
and digest.

## Private-code boundary

The open core must not import Workspace, Change Unit, semantic-spine, persistence, webhook,
or publisher packages from `interact-space/PrismCode`. Reusable rules and test vectors may
be adapted only through public contracts and with source provenance recorded before public
release.
