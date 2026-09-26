from __future__ import annotations

from typing import Iterable, Protocol

from repodelta.model.contracts import (
    ChangedFile,
    Diagnostic,
    ProviderContribution,
    ProviderDescriptor,
    ProviderFileCoverage,
    ProviderObservation,
    ProviderPlan,
    ProviderPlanEntry,
)


class EvidenceProvider(Protocol):
    """A provider declares itself, then observes only what it was dispatched.

    It returns facts, coverage and diagnostics; never a review conclusion.
    Dispatch is a routing decision, not a coverage claim: the provider keeps
    final authority over what it actually examined.
    """

    def descriptor(self) -> ProviderDescriptor: ...

    def observe(
        self,
        *,
        head_paths: tuple[str, ...] = (),
        base_paths: tuple[str, ...] = (),
    ) -> ProviderObservation: ...


def plan_providers(
    changed_files: Iterable[ChangedFile],
    descriptors: Iterable[ProviderDescriptor],
) -> ProviderPlan:
    """Dispatch changed files to every provider whose selectors claim them.

    Routing is non-exclusive and deterministic: a path claimed by several
    providers goes to each, and a file no provider claims on either side is
    recorded as unclaimed rather than dropped.
    """

    ordered = tuple(sorted(descriptors, key=lambda item: item.provider))
    if len({item.provider for item in ordered}) != len(ordered):
        raise ValueError("provider descriptors must have unique identities")
    files = tuple(changed_files)
    head: dict[str, set[str]] = {item.provider: set() for item in ordered}
    base: dict[str, set[str]] = {item.provider: set() for item in ordered}
    unclaimed: set[str] = set()
    for changed in files:
        claimed = False
        for descriptor in ordered:
            if changed.head_path and descriptor.claims(changed.head_path):
                head[descriptor.provider].add(changed.head_path)
                claimed = True
            if changed.base_path and descriptor.claims(changed.base_path):
                base[descriptor.provider].add(changed.base_path)
                claimed = True
        if not claimed:
            unclaimed.add(display_path(changed))
    plan = ProviderPlan(
        changed_files=tuple(sorted({display_path(item) for item in files})),
        entries=tuple(
            ProviderPlanEntry(
                provider=descriptor.provider,
                head_paths=tuple(sorted(head[descriptor.provider])),
                base_paths=tuple(sorted(base[descriptor.provider])),
            )
            for descriptor in ordered
            if head[descriptor.provider] or base[descriptor.provider]
        ),
        unclaimed_files=tuple(sorted(unclaimed)),
    )
    plan.validate_consistency()
    return plan


def display_path(changed: ChangedFile) -> str:
    return changed.head_path or changed.base_path or ""


def run_providers(
    providers: Iterable[EvidenceProvider], plan: ProviderPlan
) -> tuple[ProviderContribution, ...]:
    """Observe each provider over exactly its dispatch, failing closed.

    A provider that raises contributes explicit unavailable coverage for its
    dispatched files and a diagnostic; it never contributes silence. A provider
    with nothing dispatched is still recorded so its declared capabilities stay
    review-visible.
    """

    entries = {entry.provider: entry for entry in plan.entries}
    contributions: list[ProviderContribution] = []
    for provider in providers:
        descriptor = provider.descriptor()
        entry = entries.get(descriptor.provider, ProviderPlanEntry(descriptor.provider))
        if not entry.head_paths and not entry.base_paths:
            observation = ProviderObservation(provider=descriptor.provider)
        else:
            try:
                observation = provider.observe(
                    head_paths=entry.head_paths, base_paths=entry.base_paths
                )
            except Exception as error:  # noqa: BLE001 - provider boundary
                observation = ProviderObservation(
                    provider=descriptor.provider,
                    coverage=tuple(
                        ProviderFileCoverage(
                            revision_side=side, path=path, state="unavailable"
                        )
                        for side, paths in (
                            ("head", entry.head_paths),
                            ("base", entry.base_paths),
                        )
                        for path in paths
                    ),
                    diagnostics=(
                        Diagnostic(
                            code="evidence_provider_failed",
                            message=(
                                f"{descriptor.provider} failed with "
                                f"{type(error).__name__}; its dispatched files "
                                "were not examined."
                            ),
                        ),
                    ),
                )
        contributions.append(ProviderContribution(descriptor, observation))
    return tuple(contributions)
