"""Dormant contracts for bounded LLM shadow reasoning."""

from repodelta.llm.admission import (
    ShadowAdmissionDiagnostic,
    ShadowAdmissionPolicy,
    ShadowCandidateAdmission,
    ShadowCandidateAdmissionSet,
    admit_shadow_candidates,
)
from repodelta.llm.contracts import (
    ShadowEvidenceCandidate,
    ShadowEvidenceRequest,
    ShadowEvidenceSelection,
    ShadowEvidenceSelectionItem,
    ShadowSelectionDiagnostic,
    ShadowSelectionValidation,
    parse_shadow_selection,
)
from repodelta.llm.replay import (
    ReplayShadowProvider,
    load_shadow_replay,
    load_shadow_replay_provider,
    serialize_shadow_replay,
)
from repodelta.llm.execution import (
    ShadowExecutionBundle,
    ShadowExecutionObservation,
    ShadowExecutionPolicy,
    execute_shadow_admissions,
    execute_shadow_review,
    load_shadow_execution,
    unavailable_shadow_execution,
    write_shadow_execution,
)
from repodelta.llm.labeling import (
    SHADOW_LABELING_PACKET_SCHEMA_VERSION,
    ShadowLabelingPacket,
    load_shadow_labeling_packet,
    prepare_shadow_labeling_packet,
    write_shadow_labeling_packet,
)
from repodelta.llm.openai import OpenAIShadowConfig, OpenAIShadowProvider
from repodelta.llm.provider import (
    ShadowEvidenceProvider,
    ShadowProviderExecutionPolicy,
    ShadowProviderFailure,
    ShadowProviderFailureKind,
    ShadowProviderResponse,
)
from repodelta.llm.runner import (
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
