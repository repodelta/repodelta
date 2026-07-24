from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import (
    AnalysisInput,
    ChangedFile,
    Diagnostic,
    EvidenceItem,
    EvidenceHint,
    Requirement,
    ReviewSourcePacket,
    SourceRecord,
    SourceRef,
    VerificationObservation,
)
from .evidence_graph import (
    build_evidence_catalog,
    provided_evidence,
    verification_evidence_id,
)


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
    raw_hints = tuple(raw.get("evidence_hints", []))
    implementations = tuple(
        tuple(_evidence(value) for value in item.get("implementation", []))
        for item in raw_hints
    )
    supplied = tuple(evidence for group in implementations for evidence in group)
    catalog = build_evidence_catalog(packet, supplied=supplied)
    hints = tuple(
        EvidenceHint(
            requirement_id=item["requirement_id"],
            implementation_evidence_ids=tuple(evidence.id for evidence in implementation),
            verification_evidence_ids=tuple(
                verification_evidence_id(observation_id)
                for observation_id in item.get("verification_evidence_ids", [])
            ),
            assertion_coverage=item.get(
                "assertion_coverage", "not_established"
            ),
            gaps=tuple(item.get("gaps", [])),
            provenance=tuple(
                _source(source) for source in item.get("provenance", [])
            ),
        )
        for item, implementation in zip(raw_hints, implementations)
    )
    known_ids = {requirement.id for requirement in requirements}
    unknown = sorted({hint.requirement_id for hint in hints} - known_ids)
    if known_ids and unknown:
        raise ValueError("evidence hints reference unknown requirements: " + ", ".join(unknown))
    return AnalysisInput(
        packet=packet,
        requirements=requirements,
        evidence_hints=hints,
        evidence_catalog=catalog,
    )
