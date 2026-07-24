from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import (
    AnalysisInput,
    ChangedFile,
    Diagnostic,
    EvidenceItem,
    Requirement,
    ReviewSourcePacket,
    SourceRecord,
    SourceRef,
    VerificationObservation,
)
from .evidence_graph import provided_evidence


def _source(value: dict[str, Any]) -> SourceRef:
    return SourceRef(**value)


def _evidence(value: dict[str, Any]) -> EvidenceItem:
    kind = value["kind"]
    return provided_evidence(
        summary=value["summary"],
        kind=kind,
        classification=(
            "test"
            if kind in {"test", "related_test"}
            else value.get("classification", "code")
        ),
        sources=tuple(_source(item) for item in value.get("sources", [])),
        statement_ids=tuple(value.get("statement_ids", ())),
    )


def _diagnostic(value: dict[str, Any]) -> Diagnostic:
    return Diagnostic(
        code=value["code"],
        message=value["message"],
        severity=value.get("severity", "warning"),
        sources=tuple(_source(item) for item in value.get("sources", [])),
    )


def load_fixture(path: str | Path) -> AnalysisInput:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("schema_version") != "analysis_fixture.v3":
        raise ValueError("fixture must use schema_version analysis_fixture.v3")
    packet_raw = raw["source_packet"]
    packet = ReviewSourcePacket(
        repository=packet_raw["repository"],
        pull_request=packet_raw.get("pull_request"),
        title=packet_raw["title"],
        source_records=tuple(SourceRecord(**item) for item in packet_raw.get("source_records", [])),
        changed_files=tuple(ChangedFile(**item) for item in packet_raw.get("changed_files", [])),
        verification_observations=tuple(
            VerificationObservation(**item)
            for item in packet_raw.get("verification_observations", [])
        ),
        source_url=packet_raw.get("source_url"),
        head_sha=packet_raw.get("head_sha"),
        base_sha=packet_raw.get("base_sha"),
        diagnostics=tuple(_diagnostic(item) for item in packet_raw.get("diagnostics", [])),
        metadata=packet_raw.get("metadata", {}),
        schema_version=packet_raw.get("schema_version", "review_source_packet.v1"),
        packet_revision=packet_raw.get("packet_revision", ""),
    )
    packet.validate_consistency()
    requirements = tuple(
        Requirement(
            id=item["id"],
            text=item["text"],
            role=item.get("role", "obligation"),
            authority=item.get("authority", "provided"),
            kind=item.get("kind", "deliverable"),
            sources=tuple(_source(source) for source in item.get("sources", [])),
        )
        for item in raw.get("requirements", [])
    )
    raw_evidence = tuple(raw.get("evidence", []))
    supplied = tuple(_evidence(value) for value in raw_evidence)
    known_ids = {requirement.id for requirement in requirements}
    unknown = sorted(
        {
            statement_id
            for item in raw_evidence
            for statement_id in item.get("statement_ids", ())
        }
        - known_ids
    )
    if known_ids and unknown:
        raise ValueError("evidence references unknown requirements: " + ", ".join(unknown))
    return AnalysisInput(
        packet=packet,
        requirements=requirements,
        supplied_evidence=supplied,
    )
