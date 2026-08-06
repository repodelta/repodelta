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
from prismcode.llm.replay import (
    ReplayShadowProvider,
    load_shadow_replay,
    load_shadow_replay_provider,
    serialize_shadow_replay,
)
from prismcode.llm.execution import (
    ShadowExecutionBundle,
    execute_shadow_admissions,
    execute_shadow_review,
    unavailable_shadow_execution,
    write_shadow_execution,
)
from prismcode.llm.provider import ShadowEvidenceProvider, ShadowProviderResponse
from prismcode.llm.runner import (
    ShadowRunRecord,
    ShadowRunner,
    ShadowSelectionComparison,
)

__all__ = [
    "ShadowEvidenceCandidate",
    "ShadowExecutionBundle",
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
    "ReplayShadowProvider",
    "ShadowSelectionComparison",
    "ShadowSelectionValidation",
    "load_shadow_replay",
    "load_shadow_replay_provider",
    "admit_shadow_candidates",
    "parse_shadow_selection",
    "serialize_shadow_replay",
    "execute_shadow_admissions",
    "execute_shadow_review",
    "unavailable_shadow_execution",
    "write_shadow_execution",
]
