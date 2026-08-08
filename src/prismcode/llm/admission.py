from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from prismcode.llm.contracts import (
    MAX_CANDIDATES,
    ShadowEvidenceCandidate,
    ShadowEvidenceRequest,
)
from prismcode.llm.packet import build_shadow_code_packet
from prismcode.model.contracts import (
    EvidenceCatalog,
    EvidenceItem,
    ObservedTransformation,
    TransformationAlignment,
    TransformationAssessment,
    TransformationClaim,
    TransformationClaimAssessment,
    TransformationContract,
    TransformationEvidenceBinding,
)
from prismcode.routing.transformation import eligible_transformation_evidence


ShadowAdmissionState = Literal["ready", "ready_truncated", "empty", "blocked"]


@dataclass(frozen=True)
class ShadowAdmissionPolicy:
    max_candidates: int = MAX_CANDIDATES

    def __post_init__(self) -> None:
        if not 1 <= self.max_candidates <= MAX_CANDIDATES:
            raise ValueError(
                f"max_candidates must be between 1 and {MAX_CANDIDATES}"
            )


@dataclass(frozen=True)
class ShadowAdmissionDiagnostic:
    code: str
    message: str


@dataclass(frozen=True)
class ShadowCandidateAdmission:
    claim_id: str
    state: ShadowAdmissionState
    eligible_count: int
    deterministic_evidence_ids: tuple[str, ...] = ()
    request: ShadowEvidenceRequest | None = None
    diagnostics: tuple[ShadowAdmissionDiagnostic, ...] = ()


@dataclass(frozen=True)
class ShadowCandidateAdmissionSet:
    admissions: tuple[ShadowCandidateAdmission, ...]

    def by_claim_id(self) -> dict[str, ShadowCandidateAdmission]:
        return {item.claim_id: item for item in self.admissions}


def admit_shadow_candidates(
    contract: TransformationContract,
    observed: ObservedTransformation,
    evidence_catalog: EvidenceCatalog,
    alignment: TransformationAlignment,
    assessment: TransformationAssessment,
    *,
    policy: ShadowAdmissionPolicy = ShadowAdmissionPolicy(),
) -> ShadowCandidateAdmissionSet:
    """Admit typed fact candidates without changing association or assessment."""

    evidence = evidence_catalog.by_id()
    observed_ids = set(observed.evidence_ids())
    bindings = {item.id: item for item in alignment.bindings}
    assessments = assessment.by_claim_id()
    admissions = tuple(
        _admit_claim(
            claim,
            evidence_catalog,
            evidence,
            observed_ids,
            bindings,
            assessments[claim.id],
            policy,
        )
        for claim in contract.claims
    )
    result = ShadowCandidateAdmissionSet(admissions=admissions)
    _validate_admissions(result, contract)
    return result


def _admit_claim(
    claim: TransformationClaim,
    evidence_catalog: EvidenceCatalog,
    evidence: dict[str, EvidenceItem],
    observed_ids: set[str],
    bindings: dict[str, TransformationEvidenceBinding],
    claim_assessment: TransformationClaimAssessment,
    policy: ShadowAdmissionPolicy,
) -> ShadowCandidateAdmission:
    if claim.kind == "uncertainty":
        return ShadowCandidateAdmission(
            claim_id=claim.id,
            state="empty",
            eligible_count=0,
            diagnostics=(
                ShadowAdmissionDiagnostic(
                    code="shadow_admission_not_applicable",
                    message="Authored uncertainty is context, not an evidence-selection task.",
                ),
            ),
        )

    baseline_binding_ids = tuple(
        dict.fromkeys(
            (
                *claim_assessment.supporting_binding_ids,
                *claim_assessment.contradicting_binding_ids,
            )
        )
    )
    baseline_ids = tuple(
        dict.fromkeys(bindings[item].evidence_id for item in baseline_binding_ids)
    )
    eligible_ids = tuple(
        item.id
        for item in evidence_catalog.items
        if (
            item.id in observed_ids
            and eligible_transformation_evidence(claim, item)
        )
        or (
            item.role == "closure_fact"
            and claim.id in item.associated_statement_ids
        )
        or item.id in baseline_ids
    )
    if not eligible_ids:
        return ShadowCandidateAdmission(
            claim_id=claim.id,
            state="empty",
            eligible_count=0,
            diagnostics=(
                ShadowAdmissionDiagnostic(
                    code="shadow_admission_no_eligible_fact",
                    message="No typed observed fact is eligible for this claim kind.",
                ),
            ),
        )

    if len(baseline_ids) > policy.max_candidates:
        return ShadowCandidateAdmission(
            claim_id=claim.id,
            state="blocked",
            eligible_count=len(eligible_ids),
            deterministic_evidence_ids=baseline_ids,
            diagnostics=(
                ShadowAdmissionDiagnostic(
                    code="shadow_admission_baseline_over_budget",
                    message=(
                        "The deterministic evidence baseline exceeds the candidate "
                        "safety budget; no shadow request was created."
                    ),
                ),
            ),
        )

    ordered_ids = tuple(
        dict.fromkeys((*baseline_ids, *eligible_ids))
    )
    selected_ids = ordered_ids[: policy.max_candidates]
    truncated = len(ordered_ids) > len(selected_ids)
    coverage_limits: list[str] = []
    diagnostics: list[ShadowAdmissionDiagnostic] = []
    if truncated:
        detail = (
            f"Candidate admission retained {len(selected_ids)}/{len(ordered_ids)} "
            "typed evidence identities within the safety budget."
        )
        coverage_limits.append(detail)
        diagnostics.append(
            ShadowAdmissionDiagnostic(
                code="shadow_admission_budget_truncated",
                message=detail,
            )
        )
    if any(
        evidence[item].kind == "structural_path"
        and evidence[item].structural_traversal_coverage != "complete"
        for item in eligible_ids
    ):
        coverage_limits.append(
            "Structural traversal coverage is incomplete for eligible evidence."
        )

    candidates, packet_limits = build_shadow_code_packet(
        tuple(evidence[item] for item in selected_ids),
        evidence_catalog,
    )
    coverage_limits.extend(packet_limits)
    request = ShadowEvidenceRequest(
        request_id=_request_id(claim, candidates, coverage_limits),
        subject_id=claim.id,
        subject_kind=claim.kind,
        authored_statement=claim.text,
        candidates=candidates,
        coverage_limits=tuple(coverage_limits),
    )
    return ShadowCandidateAdmission(
        claim_id=claim.id,
        state="ready_truncated" if truncated else "ready",
        eligible_count=len(eligible_ids),
        deterministic_evidence_ids=baseline_ids,
        request=request,
        diagnostics=tuple(diagnostics),
    )


def _request_id(
    claim: TransformationClaim,
    candidates: tuple[ShadowEvidenceCandidate, ...],
    coverage_limits: list[str],
) -> str:
    canonical = json.dumps(
        {
            "claim_id": claim.id,
            "claim_kind": claim.kind,
            "claim_text": claim.text,
            "candidates": [item.to_dict() for item in candidates],
            "coverage_limits": coverage_limits,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"shadow:{claim.id}:{digest}"


def _validate_admissions(
    result: ShadowCandidateAdmissionSet,
    contract: TransformationContract,
) -> None:
    claim_ids = tuple(item.id for item in contract.claims)
    if tuple(item.claim_id for item in result.admissions) != claim_ids:
        raise ValueError("shadow admission must preserve every claim exactly once")
    for admission in result.admissions:
        if (admission.request is not None) != admission.state.startswith("ready"):
            raise ValueError("only ready shadow admissions may carry a request")
        if admission.request is not None:
            candidate_ids = {
                item.evidence_id for item in admission.request.candidates
            }
            if not set(admission.deterministic_evidence_ids) <= candidate_ids:
                raise ValueError(
                    "shadow request must retain every deterministic baseline identity"
                )
