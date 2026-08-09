from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Literal

from prismcode.llm.contracts import (
    ShadowEvidenceRequest,
    ShadowEvidenceSelection,
    ShadowSelectionDiagnostic,
    parse_shadow_selection,
)
from prismcode.llm.provider import (
    ShadowEvidenceProvider,
    ShadowProviderExecutionPolicy,
    ShadowProviderFailure,
)


ShadowRunState = Literal["accepted", "invalid_output", "provider_error"]


@dataclass(frozen=True)
class ShadowSelectionComparison:
    deterministic_ids: tuple[str, ...]
    shadow_ids: tuple[str, ...]
    shared_ids: tuple[str, ...]
    deterministic_only_ids: tuple[str, ...]
    shadow_only_ids: tuple[str, ...]


@dataclass(frozen=True)
class ShadowRunRecord:
    """Measured shadow observation with no production or assessment authority."""

    request_id: str
    subject_id: str
    state: ShadowRunState
    candidate_count: int
    duration_ms: float
    execution_policy: ShadowProviderExecutionPolicy
    provider_id: str | None = None
    model_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    selection: ShadowEvidenceSelection | None = None
    comparison: ShadowSelectionComparison | None = None
    diagnostics: tuple[ShadowSelectionDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        accepted = self.state == "accepted"
        if (self.selection is not None) != accepted or (
            (self.comparison is not None) != accepted
        ):
            raise ValueError("only accepted shadow runs carry selection semantics")
        if self.selection is not None and (
            self.selection.request_id != self.request_id
            or self.selection.subject_id != self.subject_id
        ):
            raise ValueError("shadow run selection must match its run identity")
        if self.candidate_count < 0:
            raise ValueError("shadow run candidate_count cannot be negative")
        if self.duration_ms < 0:
            raise ValueError("shadow run duration_ms cannot be negative")


class ShadowRunner:
    """Invoke one provider and isolate every failure from deterministic output."""

    def __init__(
        self,
        provider: ShadowEvidenceProvider,
        *,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._provider = provider
        self._clock = clock

    def measure_selection(
        self,
        request: ShadowEvidenceRequest,
        *,
        deterministic_evidence_ids: tuple[str, ...],
    ) -> ShadowRunRecord:
        deterministic_ids = canonical_shadow_evidence_ids(
            request, deterministic_evidence_ids
        )
        started = self._clock()
        try:
            response = self._provider.select(request)
        except ShadowProviderFailure as exc:
            return ShadowRunRecord(
                request_id=request.request_id,
                subject_id=request.subject_id,
                state="provider_error",
                candidate_count=len(request.candidates),
                duration_ms=_elapsed_ms(started, self._clock()),
                execution_policy=self._provider.execution_policy,
                diagnostics=(
                    ShadowSelectionDiagnostic(
                        code=f"shadow_provider_{exc.kind}",
                        message=_PROVIDER_FAILURE_MESSAGES[exc.kind],
                    ),
                ),
            )
        except Exception:
            return ShadowRunRecord(
                request_id=request.request_id,
                subject_id=request.subject_id,
                state="provider_error",
                candidate_count=len(request.candidates),
                duration_ms=_elapsed_ms(started, self._clock()),
                execution_policy=self._provider.execution_policy,
                diagnostics=(
                    ShadowSelectionDiagnostic(
                        code="shadow_provider_error",
                        message="Shadow provider failed before validated output.",
                    ),
                ),
            )

        validation = parse_shadow_selection(response.output, request)
        common = dict(
            request_id=request.request_id,
            subject_id=request.subject_id,
            candidate_count=len(request.candidates),
            duration_ms=_elapsed_ms(started, self._clock()),
            provider_id=response.provider_id,
            model_id=response.model_id,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            execution_policy=self._provider.execution_policy,
        )
        if not validation.accepted or validation.selection is None:
            return ShadowRunRecord(
                state="invalid_output",
                diagnostics=validation.diagnostics,
                **common,
            )

        return ShadowRunRecord(
            state="accepted",
            selection=validation.selection,
            comparison=build_shadow_selection_comparison(
                request,
                deterministic_ids,
                validation.selection,
            ),
            **common,
        )


def canonical_shadow_evidence_ids(
    request: ShadowEvidenceRequest, evidence_ids: tuple[str, ...]
) -> tuple[str, ...]:
    admitted_order = {
        candidate.evidence_id: index for index, candidate in enumerate(request.candidates)
    }
    unknown = set(evidence_ids) - set(admitted_order)
    if unknown:
        raise ValueError("deterministic evidence IDs must be admitted candidates")
    return tuple(sorted(set(evidence_ids), key=admitted_order.__getitem__))


def build_shadow_selection_comparison(
    request: ShadowEvidenceRequest,
    deterministic_evidence_ids: tuple[str, ...],
    selection: ShadowEvidenceSelection,
) -> ShadowSelectionComparison:
    """Derive the only comparison truth from one request and validated output."""

    deterministic_ids = canonical_shadow_evidence_ids(
        request, deterministic_evidence_ids
    )
    shadow_ids = tuple(item.evidence_id for item in selection.selections)
    canonical_shadow_evidence_ids(
        request,
        shadow_ids,
    )
    deterministic = set(deterministic_ids)
    shadow = set(shadow_ids)
    return ShadowSelectionComparison(
        deterministic_ids=deterministic_ids,
        shadow_ids=shadow_ids,
        shared_ids=tuple(value for value in deterministic_ids if value in shadow),
        deterministic_only_ids=tuple(
            value for value in deterministic_ids if value not in shadow
        ),
        shadow_only_ids=tuple(value for value in shadow_ids if value not in deterministic),
    )


def _elapsed_ms(started: float, finished: float) -> float:
    return max(0.0, (finished - started) * 1_000)


_PROVIDER_FAILURE_MESSAGES = {
    "timeout": "Shadow provider timed out without validated output.",
    "network_failure": "Shadow provider transport failed without validated output.",
    "rate_limited": "Shadow provider returned an HTTP rate-limit response.",
    "request_rejected": "Shadow provider returned an HTTP 4xx request response.",
    "server_failure": "Shadow provider returned an HTTP 5xx server response.",
    "transport_response_decode_failure": (
        "Shadow provider HTTP response could not be decoded as the transport contract."
    ),
    "structured_output_decode_failure": (
        "Shadow provider message content could not be decoded as structured output."
    ),
    "structured_output_missing": (
        "Shadow provider response contained no usable structured output."
    ),
}
