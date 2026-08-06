"""Dormant contracts for bounded LLM shadow reasoning."""

from prismcode.llm.admission import (
    ShadowAdmissionDiagnostic,
    ShadowAdmissionPolicy,
    ShadowCandidateAdmission,
    ShadowCandidateAdmissionSet,
    admit_shadow_candidates,
)
from prismcode.llm.contracts import (
    ShadowEvidenceCandidate,
    ShadowEvidenceRequest,
    ShadowEvidenceSelection,
    ShadowEvidenceSelectionItem,
    ShadowSelectionDiagnostic,
    ShadowSelectionValidation,
    parse_shadow_selection,
)
from prismcode.llm.replay import load_shadow_replay, serialize_shadow_replay
from prismcode.llm.provider import ShadowEvidenceProvider, ShadowProviderResponse
from prismcode.llm.runner import (
    ShadowRunRecord,
    ShadowRunner,
    ShadowSelectionComparison,
)

__all__ = [
    "ShadowEvidenceCandidate",
    "ShadowAdmissionDiagnostic",
    "ShadowAdmissionPolicy",
    "ShadowCandidateAdmission",
    "ShadowCandidateAdmissionSet",
    "ShadowEvidenceRequest",
    "ShadowEvidenceProvider",
    "ShadowEvidenceSelection",
    "ShadowEvidenceSelectionItem",
    "ShadowSelectionDiagnostic",
    "ShadowProviderResponse",
    "ShadowRunRecord",
    "ShadowRunner",
    "ShadowSelectionComparison",
    "ShadowSelectionValidation",
    "load_shadow_replay",
    "admit_shadow_candidates",
    "parse_shadow_selection",
    "serialize_shadow_replay",
]
