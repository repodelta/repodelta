from __future__ import annotations

from dataclasses import dataclass

from repodelta.model.contracts import (
    Diagnostic,
    ProviderContribution,
    ProviderCoverage,
    ProviderFact,
    ProviderFileCoverage,
    ProviderPlan,
    ProviderPlanEntry,
    aggregate_provider_state,
)


@dataclass(frozen=True)
class FederatedEvidence:
    facts: tuple[ProviderFact, ...]
    coverage: tuple[ProviderCoverage, ...]
    diagnostics: tuple[Diagnostic, ...]


def ingest_contributions(
    plan: ProviderPlan,
    contributions: tuple[ProviderContribution, ...],
) -> FederatedEvidence:
    """Hold every contribution to its declaration and dispatch, then tabulate.

    Ingestion trusts nothing a provider returned: attribution, declared
    capability and dispatched paths are re-validated here, and a dispatched
    file the provider silently omitted becomes explicit unavailable coverage.
    """

    plan.validate_consistency()
    identities = tuple(item.descriptor.provider for item in contributions)
    if len(set(identities)) != len(identities):
        raise ValueError("provider contributions must have unique identities")
    entries = {entry.provider: entry for entry in plan.entries}
    unknown = set(entries) - set(identities)
    if unknown:
        raise ValueError(f"dispatched providers returned nothing: {sorted(unknown)}")
    facts: list[ProviderFact] = []
    rows: list[ProviderCoverage] = []
    diagnostics: list[Diagnostic] = []
    for contribution in sorted(contributions, key=lambda item: item.descriptor.provider):
        descriptor = contribution.descriptor
        observation = contribution.observation
        entry = entries.get(descriptor.provider, ProviderPlanEntry(descriptor.provider))
        observation.validate_consistency(
            descriptor,
            head_paths=entry.head_paths,
            base_paths=entry.base_paths,
        )
        covered = {(item.revision_side, item.path) for item in observation.coverage}
        omitted = tuple(
            ProviderFileCoverage(revision_side=side, path=path, state="unavailable")
            for side, paths in (("head", entry.head_paths), ("base", entry.base_paths))
            for path in paths
            if (side, path) not in covered
        )
        if omitted:
            diagnostics.append(
                Diagnostic(
                    code="evidence_provider_omitted_dispatch",
                    message=(
                        f"{descriptor.provider} returned no coverage for "
                        f"{', '.join(sorted(item.path for item in omitted))}; "
                        "recorded as unavailable."
                    ),
                )
            )
        files = tuple(
            sorted(
                (*observation.coverage, *omitted),
                key=lambda item: (item.path, item.revision_side),
            )
        )
        rows.append(
            ProviderCoverage(
                provider=descriptor.provider,
                capabilities=descriptor.capabilities,
                state=aggregate_provider_state(files),
                files=files,
                fact_count=len(observation.facts),
            )
        )
        facts.extend(observation.facts)
        diagnostics.extend(observation.diagnostics)
    return FederatedEvidence(tuple(facts), tuple(rows), tuple(diagnostics))
