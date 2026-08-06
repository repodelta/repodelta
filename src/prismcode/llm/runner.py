from __future__ import annotations

import time
from dataclasses import dataclass
from collections.abc import Iterable
from typing import Callable, Literal

from prismcode.llm.contracts import (
    ShadowEvidenceRequest,
    ShadowEvidenceSelection,
    ShadowSelectionDiagnostic,
    parse_shadow_selection,
)
from prismcode.llm.provider import ShadowEvidenceProvider


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
    provider_id: str | None = None
    model_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    selection: ShadowEvidenceSelection | None = None
    comparison: ShadowSelectionComparison | None = None
    diagnostics: tuple[ShadowSelectionDiagnostic, ...] = ()


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
        deterministic_ids = _canonical_ids(request, deterministic_evidence_ids)
        started = self._clock()
        try:
            response = self._provider.select(request)
        except Exception:
            return ShadowRunRecord(
                request_id=request.request_id,
                subject_id=request.subject_id,
                state="provider_error",
                candidate_count=len(request.candidates),
                duration_ms=_elapsed_ms(started, self._clock()),
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
        )
        if not validation.accepted or validation.selection is None:
            return ShadowRunRecord(
                state="invalid_output",
                diagnostics=validation.diagnostics,
                **common,
            )

        shadow_ids = _ordered_unique(
            item.evidence_id for item in validation.selection.selections
        )
        return ShadowRunRecord(
            state="accepted",
            selection=validation.selection,
            comparison=_compare(deterministic_ids, shadow_ids),
            **common,
        )


def _canonical_ids(
    request: ShadowEvidenceRequest, evidence_ids: tuple[str, ...]
) -> tuple[str, ...]:
    admitted_order = {
        candidate.evidence_id: index for index, candidate in enumerate(request.candidates)
    }
    unknown = set(evidence_ids) - set(admitted_order)
    if unknown:
        raise ValueError("deterministic evidence IDs must be admitted candidates")
    return tuple(sorted(set(evidence_ids), key=admitted_order.__getitem__))


def _ordered_unique(evidence_ids: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(evidence_ids))


def _compare(
    deterministic_ids: tuple[str, ...], shadow_ids: tuple[str, ...]
) -> ShadowSelectionComparison:
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
