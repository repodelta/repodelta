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
    ShadowExecutionObservation,
    ShadowExecutionPolicy,
    execute_shadow_admissions,
    execute_shadow_review,
    load_shadow_execution,
    unavailable_shadow_execution,
    write_shadow_execution,
)
from prismcode.llm.labeling import (
    SHADOW_LABELING_PACKET_SCHEMA_VERSION,
    ShadowLabelingPacket,
    load_shadow_labeling_packet,
    prepare_shadow_labeling_packet,
    write_shadow_labeling_packet,
)
from prismcode.llm.openai import OpenAIShadowConfig, OpenAIShadowProvider
from prismcode.llm.provider import (
    ShadowEvidenceProvider,
    ShadowProviderExecutionPolicy,
    ShadowProviderFailure,
    ShadowProviderFailureKind,
    ShadowProviderResponse,
)
from prismcode.llm.runner import (
    ShadowRunRecord,
    ShadowRunner,
    ShadowSelectionComparison,
)

__all__ = [
    "ShadowEvidenceCandidate",
    "ShadowExecutionBundle",
    "ShadowExecutionObservation",
    "ShadowExecutionPolicy",
    "ShadowLabelingPacket",
    "OpenAIShadowConfig",
    "OpenAIShadowProvider",
    "ShadowAdmissionDiagnostic",
    "ShadowAdmissionPolicy",
    "ShadowCandidateAdmission",
    "ShadowCandidateAdmissionSet",
    "ShadowEvidenceRequest",
    "ShadowEvidenceProvider",
    "ShadowProviderExecutionPolicy",
    "ShadowProviderFailure",
    "ShadowProviderFailureKind",
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
    "load_shadow_execution",
    "unavailable_shadow_execution",
    "write_shadow_execution",
    "SHADOW_LABELING_PACKET_SCHEMA_VERSION",
    "load_shadow_labeling_packet",
    "prepare_shadow_labeling_packet",
    "write_shadow_labeling_packet",
]
