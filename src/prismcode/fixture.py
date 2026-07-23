from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import (
    AnalysisInput,
    ChangedFile,
    Diagnostic,
    Evidence,
    EvidenceHint,
    Requirement,
    ReviewSourcePacket,
    SourceRecord,
    SourceRef,
    VerificationObservation,
)


def _source(value: dict[str, Any]) -> SourceRef:
    return SourceRef(**value)


def _evidence(value: dict[str, Any]) -> Evidence:
    return Evidence(
        summary=value["summary"],
        kind=value["kind"],
        sources=tuple(_source(item) for item in value.get("sources", [])),
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
    if raw.get("schema_version") != "analysis_fixture.v2":
        raise ValueError("fixture must use schema_version analysis_fixture.v2")
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
    hints = tuple(
        EvidenceHint(
            requirement_id=item["requirement_id"],
            implementation=tuple(_evidence(value) for value in item.get("implementation", [])),
            verification_evidence_ids=tuple(item.get("verification_evidence_ids", [])),
            assertion_coverage=item.get("assertion_coverage", "not_established"),
            gaps=tuple(item.get("gaps", [])),
            provenance=tuple(_source(source) for source in item.get("provenance", [])),
        )
        for item in raw.get("evidence_hints", [])
    )
    known_ids = {requirement.id for requirement in requirements}
    unknown = sorted({hint.requirement_id for hint in hints} - known_ids)
    if known_ids and unknown:
        raise ValueError("evidence hints reference unknown requirements: " + ", ".join(unknown))
    return AnalysisInput(packet=packet, requirements=requirements, evidence_hints=hints)
