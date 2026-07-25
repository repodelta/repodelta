# Intake

## Owns

Reading external GitHub and fixture data into `ReviewSourcePacket` and raw
supplied facts.

## Input / output

External API or fixture JSON → source packet and `AnalysisInput`.

## Invariants

Packet revision matches packet content. Intake preserves source authority and
does not produce review conclusions.

## Must not

Parse Markdown semantics, parse diff hunks, classify repository paths, route
facts, or format UI status.

## Diagnostics

Records source availability and collection coverage facts.

## Extension points

Additional source adapters produce the same packet contract.
