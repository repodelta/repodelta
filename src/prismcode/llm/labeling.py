from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from prismcode.llm.admission import (
    DEFAULT_REVIEW_SHADOW_ADMISSION_POLICY,
    ShadowAdmissionDiagnostic,
    ShadowAdmissionPolicy,
    ShadowCandidateAdmission,
    ShadowCandidateAdmissionSet,
    admit_shadow_candidates,
)
from prismcode.llm.contracts import (
    ShadowEvidenceCandidate,
    ShadowEvidenceRequest,
    shadow_candidate_from_mapping,
)
from prismcode.llm.runner import canonical_shadow_evidence_ids
from prismcode.model.contracts import ReviewBrief


SHADOW_LABELING_PACKET_SCHEMA_VERSION = "llm_shadow_labeling_packet.v1"


@dataclass(frozen=True)
class ShadowLabelingPacket:
    """Pre-execution requests whose model-independent identity is frozen."""

    repository: str
    pull_request: int | None
    head_sha: str | None
    base_sha: str | None
    admissions: tuple[ShadowCandidateAdmission, ...]
    schema_version: str = SHADOW_LABELING_PACKET_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SHADOW_LABELING_PACKET_SCHEMA_VERSION:
            raise ValueError("unsupported shadow labeling packet schema_version")
        if not self.repository.strip():
            raise ValueError("shadow labeling packet repository must be non-empty")
        if self.pull_request is not None and self.pull_request <= 0:
            raise ValueError("shadow labeling packet pull_request must be positive")
        claim_ids = tuple(item.claim_id for item in self.admissions)
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("shadow labeling packet claim IDs must be unique")
        for admission in self.admissions:
            _validate_admission(admission)

    @property
    def admission_set(self) -> ShadowCandidateAdmissionSet:
        return ShadowCandidateAdmissionSet(admissions=self.admissions)

    @property
    def requests_by_claim_id(self) -> dict[str, ShadowEvidenceRequest]:
        return {
            item.claim_id: item.request
            for item in self.admissions
            if item.request is not None
        }

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def prepare_shadow_labeling_packet(
    brief: ReviewBrief,
    *,
    admission_policy: ShadowAdmissionPolicy = DEFAULT_REVIEW_SHADOW_ADMISSION_POLICY,
) -> ShadowLabelingPacket:
    """Freeze the exact review admissions before any provider invocation."""

    admissions = admit_shadow_candidates(
        brief.transformation_contract,
        brief.observed_transformation,
        brief.evidence_catalog,
        brief.transformation_alignment,
        brief.transformation_assessment,
        policy=admission_policy,
    )
    packet = brief.packet
    return ShadowLabelingPacket(
        repository=packet.repository,
        pull_request=packet.pull_request,
        head_sha=packet.head_sha,
        base_sha=packet.base_sha,
        admissions=admissions.admissions,
    )


def write_shadow_labeling_packet(
    packet: ShadowLabelingPacket,
    output: str | Path,
) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(packet.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def load_shadow_labeling_packet(path: str | Path) -> ShadowLabelingPacket:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("shadow labeling packet must be an object")
    _reject_fields(
        raw,
        {
            "repository",
            "pull_request",
            "head_sha",
            "base_sha",
            "admissions",
            "schema_version",
        },
        "packet",
    )
    if raw.get("schema_version") != SHADOW_LABELING_PACKET_SCHEMA_VERSION:
        raise ValueError(
            "shadow labeling packet must use schema_version "
            f"{SHADOW_LABELING_PACKET_SCHEMA_VERSION}"
        )
    raw_admissions = raw.get("admissions")
    if not isinstance(raw_admissions, list):
        raise ValueError("shadow labeling packet admissions must be a list")
    return ShadowLabelingPacket(
        repository=str(raw.get("repository", "")),
        pull_request=_optional_positive_int(
            raw.get("pull_request"), "pull_request"
        ),
        head_sha=_optional_string(raw.get("head_sha"), "head_sha"),
        base_sha=_optional_string(raw.get("base_sha"), "base_sha"),
        admissions=tuple(_load_admission(item) for item in raw_admissions),
        schema_version=str(raw["schema_version"]),
    )


def _load_admission(raw: object) -> ShadowCandidateAdmission:
    if not isinstance(raw, Mapping):
        raise ValueError("shadow labeling admission must be an object")
    _reject_fields(
        raw,
        {
            "claim_id",
            "state",
            "eligible_count",
            "deterministic_evidence_ids",
            "request",
            "diagnostics",
        },
        "admission",
    )
    request = _load_request(raw.get("request"))
    raw_diagnostics = raw.get("diagnostics", ())
    if not isinstance(raw_diagnostics, list):
        raise ValueError("shadow labeling admission diagnostics must be a list")
    if any(not isinstance(item, Mapping) for item in raw_diagnostics):
        raise ValueError("shadow labeling admission diagnostic must be an object")
    for item in raw_diagnostics:
        _reject_fields(item, {"code", "message"}, "admission diagnostic")
    raw_evidence_ids = raw.get("deterministic_evidence_ids", ())
    if not isinstance(raw_evidence_ids, list) or any(
        not isinstance(item, str) for item in raw_evidence_ids
    ):
        raise ValueError(
            "shadow labeling deterministic_evidence_ids must be a string list"
        )
    return ShadowCandidateAdmission(
        claim_id=str(raw.get("claim_id", "")),
        state=raw.get("state"),
        eligible_count=int(raw.get("eligible_count", -1)),
        deterministic_evidence_ids=tuple(raw_evidence_ids),
        request=request,
        diagnostics=tuple(
            ShadowAdmissionDiagnostic(
                code=str(item.get("code", "")),
                message=str(item.get("message", "")),
            )
            for item in raw_diagnostics
        ),
    )


def _load_request(raw: object) -> ShadowEvidenceRequest | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError("shadow labeling admission request must be an object")
    _reject_fields(
        raw,
        {
            "request_id",
            "subject_id",
            "subject_kind",
            "authored_statement",
            "candidates",
            "coverage_limits",
            "schema_version",
        },
        "request",
    )
    raw_candidates = raw.get("candidates", ())
    if not isinstance(raw_candidates, list):
        raise ValueError("shadow labeling request candidates must be a list")
    if any(not isinstance(item, Mapping) for item in raw_candidates):
        raise ValueError("shadow labeling request candidate must be an object")
    for item in raw_candidates:
        _reject_fields(
            item,
            set(ShadowEvidenceCandidate.__dataclass_fields__),
            "request candidate",
        )
    coverage_limits = raw.get("coverage_limits", ())
    if not isinstance(coverage_limits, list) or any(
        not isinstance(item, str) for item in coverage_limits
    ):
        raise ValueError("shadow labeling coverage_limits must be a string list")
    return ShadowEvidenceRequest(
        request_id=str(raw.get("request_id", "")),
        subject_id=str(raw.get("subject_id", "")),
        subject_kind=str(raw.get("subject_kind", "")),
        authored_statement=str(raw.get("authored_statement", "")),
        candidates=tuple(
            shadow_candidate_from_mapping(item)
            for item in raw_candidates
        ),
        coverage_limits=tuple(coverage_limits),
        schema_version=str(raw.get("schema_version", "")),
    )


def _validate_admission(admission: ShadowCandidateAdmission) -> None:
    if not admission.claim_id:
        raise ValueError("shadow labeling admission requires claim_id")
    if admission.state not in {"ready", "ready_truncated", "empty", "blocked"}:
        raise ValueError("shadow labeling admission has unsupported state")
    if admission.eligible_count < 0:
        raise ValueError("shadow labeling admission eligible_count cannot be negative")
    if (admission.request is not None) != admission.state.startswith("ready"):
        raise ValueError("only ready shadow labeling admissions carry a request")
    if admission.request is not None:
        if admission.request.subject_id != admission.claim_id:
            raise ValueError("shadow labeling request must match its claim")
        canonical = canonical_shadow_evidence_ids(
            admission.request,
            admission.deterministic_evidence_ids,
        )
        if canonical != admission.deterministic_evidence_ids:
            raise ValueError(
                "shadow labeling deterministic evidence must be canonical"
            )
        if admission.eligible_count < len(admission.request.candidates):
            raise ValueError(
                "shadow labeling eligible_count cannot omit request candidates"
            )
    elif admission.deterministic_evidence_ids:
        if admission.state != "blocked":
            raise ValueError(
                "only blocked shadow labeling admissions preserve evidence IDs"
            )
        if (
            any(not item for item in admission.deterministic_evidence_ids)
            or len(admission.deterministic_evidence_ids)
            != len(set(admission.deterministic_evidence_ids))
        ):
            raise ValueError(
                "blocked shadow labeling evidence IDs must be non-empty and unique"
            )
        if admission.eligible_count < len(admission.deterministic_evidence_ids):
            raise ValueError(
                "blocked shadow labeling evidence cannot exceed eligible evidence"
            )


def _optional_string(value: Any, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"shadow labeling packet {name} must be non-empty or null")
    return value


def _optional_positive_int(value: Any, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"shadow labeling packet {name} must be positive or null")
    return value


def _reject_fields(
    raw: Mapping[str, Any],
    allowed: set[str],
    context: str,
) -> None:
    unexpected = set(raw) - allowed
    if unexpected:
        raise ValueError(
            f"shadow labeling {context} contains unsupported fields: "
            + ", ".join(sorted(unexpected))
        )
