from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Literal

from repodelta.evaluation.structural_correctness import (
    StructuralCorrectnessLabels,
    StructuralCorrectnessObservation,
    StructuralCorrectnessPacket,
)
from repodelta.model.contracts import (
    EvidenceItem,
    ProjectionRelation,
    ReviewBrief,
    StructuralFocusOverlay,
    TransformationStructuralClosureGroup,
)
from repodelta.model.structural_refs import path_review_ids, review_symbol_id


ATTRIBUTION_SCHEMA = "structural_focus_attribution.v1"

MembershipKind = Literal["node", "exact_relation"]
MembershipRole = Literal["direct", "context", "relation"]


@dataclass(frozen=True)
class AttributionStep:
    producer_class: str
    source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.producer_class or not self.source_ids:
            raise ValueError("attribution steps require a producer and source")


@dataclass(frozen=True)
class AttributionPath:
    steps: tuple[AttributionStep, ...]

    def __post_init__(self) -> None:
        if not self.steps:
            raise ValueError("attribution paths cannot be empty")


@dataclass(frozen=True)
class MembershipAttribution:
    member_kind: MembershipKind
    member_id: str
    role: MembershipRole
    paths: tuple[AttributionPath, ...] = ()
    unsupported_reason: str = ""

    def __post_init__(self) -> None:
        if not self.member_id:
            raise ValueError("attribution membership requires an identity")
        if bool(self.paths) == bool(self.unsupported_reason):
            raise ValueError(
                "attribution membership must be supported or explicitly unsupported"
            )


@dataclass(frozen=True)
class FocusAttribution:
    subject_id: str
    memberships: tuple[MembershipAttribution, ...]

    def __post_init__(self) -> None:
        identities = tuple(
            (item.member_kind, item.member_id) for item in self.memberships
        )
        if len(set(identities)) != len(identities):
            raise ValueError("focus attribution contains duplicate memberships")


@dataclass(frozen=True)
class StructuralFocusAttribution:
    packet_digest: str
    focuses: tuple[FocusAttribution, ...]
    schema_version: str = ATTRIBUTION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != ATTRIBUTION_SCHEMA or not self.packet_digest:
            raise ValueError("invalid structural focus attribution identity")
        if len({item.subject_id for item in self.focuses}) != len(self.focuses):
            raise ValueError("structural focus attribution contains duplicate subjects")


@dataclass(frozen=True)
class CounterfactualOutcome:
    subject_kind: str
    focus_count: int
    unresolved_count: int
    unsupported_membership_count: int
    node_false_inclusions: int
    node_false_exclusions: int
    node_role_disagreements: int
    relation_false_inclusions: int
    relation_false_exclusions: int


@dataclass(frozen=True)
class CounterfactualReport:
    packet_digest: str
    disabled_producer_classes: tuple[str, ...]
    outcomes: tuple[CounterfactualOutcome, ...]
    schema_version: str = "structural_focus_counterfactual.v1"


@dataclass(frozen=True)
class ProducerCounterfactual:
    producer_class: str
    outcomes: tuple[CounterfactualOutcome, ...]


@dataclass(frozen=True)
class AttributionCampaignSummary:
    packet_digests: tuple[str, ...]
    baseline: tuple[CounterfactualOutcome, ...]
    counterfactuals: tuple[ProducerCounterfactual, ...]
    schema_version: str = "structural_focus_attribution_campaign.v1"


def attribute_structural_focus(
    brief: ReviewBrief,
    packet: StructuralCorrectnessPacket,
    observation: StructuralCorrectnessObservation,
) -> StructuralFocusAttribution:
    """Explain observed focus membership without changing production selection."""

    if observation.packet_digest != packet.digest:
        raise ValueError("structural observation does not match frozen packet")
    graph = brief.projection.review_graph
    evidence = brief.evidence_catalog.by_id()
    node_by_review_id = {item.review_symbol_id: item.id for item in graph.nodes}
    candidate_relations = brief.projection_candidates.by_id()
    convergence_by_focus = {
        item.focus_statement_id: item for item in brief.candidate_convergence.groups
    }
    inspections = {
        item.subject_id: item
        for item in brief.projection.verification_workspace.inspections
    }
    transformation_groups = brief.transformation_structural_closure.by_claim_id()
    observations = {item.subject_id: item for item in observation.focuses}
    relation_group_members = {
        item.id: set(item.member_edge_ids) for item in graph.relation_groups
    }
    graph_edges = {item.id: item for item in graph.edges}
    graph_placements = {item.id: item for item in graph.placements}
    graph_ownership = {item.id: item for item in graph.ownership_edges}

    focuses = []
    for subject in packet.subjects:
        inspection = inspections.get(subject.subject_id)
        observed = observations.get(subject.subject_id)
        if inspection is None or observed is None:
            raise ValueError(
                f"{subject.subject_id}: missing canonical inspection or observation"
            )
        overlay = inspection.structural_overlay
        if subject.subject_id in convergence_by_focus:
            paths = _requirement_paths(
                overlay,
                convergence_by_focus[subject.subject_id].selected_relation_ids,
                candidate_relations,
                evidence,
                node_by_review_id,
                graph_edges,
                graph_placements,
                graph_ownership,
            )
        else:
            paths = _transformation_paths(
                overlay,
                transformation_groups.get(subject.subject_id),
                evidence,
                node_by_review_id,
                graph_edges,
                graph_placements,
                graph_ownership,
            )
        memberships = []
        direct_ids = set(observed.direct_node_ids)
        context_ids = set(observed.context_node_ids)
        for node_id in sorted(direct_ids | context_ids):
            node_paths = _canonical_paths(paths.get(node_id, ()))
            memberships.append(
                MembershipAttribution(
                    member_kind="node",
                    member_id=node_id,
                    role="direct" if node_id in direct_ids else "context",
                    paths=node_paths,
                    unsupported_reason=(
                        "No supported production path reaches this projected node."
                        if not node_paths
                        else ""
                    ),
                )
            )
        for relation_id in observed.exact_relation_ids:
            member_edges = relation_group_members.get(relation_id, set())
            selected_edges = member_edges & set(overlay.edge_ids)
            relation_paths = _canonical_paths(
                path
                for edge_id in selected_edges
                for path in _edge_paths(
                    edge_id,
                    paths,
                    graph_edges,
                    producer="exact_relation",
                )
            )
            memberships.append(
                MembershipAttribution(
                    member_kind="exact_relation",
                    member_id=relation_id,
                    role="relation",
                    paths=relation_paths,
                    unsupported_reason=(
                        "No supported selected edge explains this relation group."
                        if not relation_paths
                        else ""
                    ),
                )
            )
        focuses.append(FocusAttribution(subject.subject_id, tuple(memberships)))

    result = StructuralFocusAttribution(packet.digest, tuple(focuses))
    _validate_attribution(result, packet, observation)
    return result


def replay_focus_counterfactual(
    packet: StructuralCorrectnessPacket,
    observation: StructuralCorrectnessObservation,
    attribution: StructuralFocusAttribution,
    labels: StructuralCorrectnessLabels,
    *,
    disabled_producer_classes: Iterable[str] = (),
) -> CounterfactualReport:
    """Replay membership removal over frozen attribution; never rerun selection."""

    disabled = frozenset(item for item in disabled_producer_classes if item)
    _validate_attribution(attribution, packet, observation)
    if labels.packet_digest != packet.digest:
        raise ValueError("structural reference does not match frozen packet")
    subject_kind = {item.subject_id: item.subject_kind for item in packet.subjects}
    observed_by_subject = {item.subject_id: item for item in observation.focuses}
    attribution_by_subject = {item.subject_id: item for item in attribution.focuses}
    outcomes: dict[str, dict[str, int]] = {}

    for expected in labels.focuses:
        kind = subject_kind[expected.subject_id]
        counts = outcomes.setdefault(
            kind,
            {
                "focus_count": 0,
                "unresolved_count": 0,
                "unsupported_membership_count": 0,
                "node_false_inclusions": 0,
                "node_false_exclusions": 0,
                "node_role_disagreements": 0,
                "relation_false_inclusions": 0,
                "relation_false_exclusions": 0,
            },
        )
        counts["focus_count"] += 1
        if expected.unresolved:
            counts["unresolved_count"] += 1
            continue
        observed = observed_by_subject[expected.subject_id]
        focus_attribution = attribution_by_subject[expected.subject_id]
        attribution_by_member = {
            (item.member_kind, item.member_id): item
            for item in focus_attribution.memberships
        }
        kept_nodes = {
            node_id
            for node_id in (*observed.direct_node_ids, *observed.context_node_ids)
            if _membership_survives(
                attribution_by_member[("node", node_id)], disabled
            )
        }
        kept_relations = {
            relation_id
            for relation_id in observed.exact_relation_ids
            if _membership_survives(
                attribution_by_member[("exact_relation", relation_id)], disabled
            )
        }
        counts["unsupported_membership_count"] += sum(
            not item.paths for item in focus_attribution.memberships
        )
        observed_roles = {
            **{
                item: "direct"
                for item in observed.direct_node_ids
                if item in kept_nodes
            },
            **{
                item: "context"
                for item in observed.context_node_ids
                if item in kept_nodes
            },
        }
        expected_roles = {
            **{item: "direct" for item in expected.direct_node_ids},
            **{item: "context" for item in expected.context_node_ids},
        }
        counts["node_false_inclusions"] += len(
            observed_roles.keys() - expected_roles.keys()
        )
        counts["node_false_exclusions"] += len(
            expected_roles.keys() - observed_roles.keys()
        )
        counts["node_role_disagreements"] += sum(
            observed_roles[item] != expected_roles[item]
            for item in observed_roles.keys() & expected_roles.keys()
        )
        expected_relations = set(expected.relation_ids)
        counts["relation_false_inclusions"] += len(
            kept_relations - expected_relations
        )
        counts["relation_false_exclusions"] += len(
            expected_relations - kept_relations
        )

    return CounterfactualReport(
        packet_digest=packet.digest,
        disabled_producer_classes=tuple(sorted(disabled)),
        outcomes=tuple(
            CounterfactualOutcome(subject_kind=kind, **counts)
            for kind, counts in sorted(outcomes.items())
        ),
    )


def summarize_attribution_campaign(
    cases: Iterable[
        tuple[
            StructuralCorrectnessPacket,
            StructuralCorrectnessObservation,
            StructuralFocusAttribution,
            StructuralCorrectnessLabels,
        ]
    ],
) -> AttributionCampaignSummary:
    """Aggregate baseline and one-producer counterfactuals over frozen cases."""

    frozen = tuple(cases)
    producer_classes = tuple(
        sorted(
            {
                step.producer_class
                for _, _, attribution, _ in frozen
                for focus in attribution.focuses
                for membership in focus.memberships
                for path in membership.paths
                for step in path.steps
            }
        )
    )
    baseline_reports = tuple(
        replay_focus_counterfactual(packet, observation, attribution, labels)
        for packet, observation, attribution, labels in frozen
    )
    return AttributionCampaignSummary(
        packet_digests=tuple(packet.digest for packet, _, _, _ in frozen),
        baseline=_aggregate_outcomes(baseline_reports),
        counterfactuals=tuple(
            ProducerCounterfactual(
                producer,
                _aggregate_outcomes(
                    tuple(
                        replay_focus_counterfactual(
                            packet,
                            observation,
                            attribution,
                            labels,
                            disabled_producer_classes=(producer,),
                        )
                        for packet, observation, attribution, labels in frozen
                    )
                ),
            )
            for producer in producer_classes
        ),
    )


def write_attribution_json(
    value: StructuralFocusAttribution | CounterfactualReport,
    output: str | Path,
) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(value), indent=2, sort_keys=True) + "\n")
    return path


def load_structural_focus_attribution(
    path: str | Path,
) -> StructuralFocusAttribution:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("schema_version") != ATTRIBUTION_SCHEMA:
        raise ValueError("unsupported structural focus attribution schema")
    return StructuralFocusAttribution(
        packet_digest=str(raw["packet_digest"]),
        focuses=tuple(
            FocusAttribution(
                subject_id=str(focus["subject_id"]),
                memberships=tuple(
                    MembershipAttribution(
                        member_kind=item["member_kind"],
                        member_id=str(item["member_id"]),
                        role=item["role"],
                        paths=tuple(
                            AttributionPath(
                                tuple(
                                    AttributionStep(
                                        str(step["producer_class"]),
                                        tuple(str(value) for value in step["source_ids"]),
                                    )
                                    for step in candidate_path["steps"]
                                )
                            )
                            for candidate_path in item.get("paths", [])
                        ),
                        unsupported_reason=str(item.get("unsupported_reason", "")),
                    )
                    for item in focus["memberships"]
                ),
            )
            for focus in raw["focuses"]
        ),
    )


def _requirement_paths(
    overlay: StructuralFocusOverlay,
    selected_relation_ids: tuple[str, ...],
    relations: dict[str, ProjectionRelation],
    evidence: dict[str, EvidenceItem],
    node_by_review_id: dict[str, str],
    graph_edges,
    graph_placements,
    graph_ownership,
) -> dict[str, list[AttributionPath]]:
    selected = tuple(relations[item] for item in selected_relation_ids)
    chains_by_evidence_id: dict[str, list[AttributionPath]] = {}
    paths_by_evidence_id: dict[str, list[AttributionPath]] = {}
    result: dict[str, list[AttributionPath]] = {}

    for relation in selected:
        if relation.slot != "changed_anchor":
            continue
        fact = evidence.get(relation.target_id)
        node_id = _node_id(fact, node_by_review_id)
        if node_id is None:
            continue
        chain = AttributionPath(
            (AttributionStep(relation.association, (relation.id,)),)
        )
        result.setdefault(node_id, []).append(chain)
        chains_by_evidence_id.setdefault(relation.target_id, []).append(chain)

    for relation in selected:
        if relation.slot != "structural_path":
            continue
        chains = [
            _append(path, "structural_path", (relation.id, relation.target_id))
            for anchor_id in relation.bridge_ids
            for path in chains_by_evidence_id.get(anchor_id, ())
        ]
        paths_by_evidence_id.setdefault(relation.target_id, []).extend(chains)
        path_fact = evidence.get(relation.target_id)
        for review_id in path_review_ids(path_fact, evidence):
            node_id = node_by_review_id.get(review_id)
            if node_id is not None:
                result.setdefault(node_id, []).extend(chains)

    for relation in selected:
        if relation.slot not in {"runtime_context", "test_context"}:
            continue
        fact = evidence.get(relation.target_id)
        node_id = _node_id(fact, node_by_review_id)
        if node_id is None:
            continue
        if relation.bridge_ids:
            chains = [
                _append(path, relation.slot, (relation.id,))
                for path_id in relation.bridge_ids
                for path in paths_by_evidence_id.get(path_id, ())
            ]
        else:
            chains = [
                AttributionPath(
                    (AttributionStep(relation.association, (relation.id,)),)
                )
            ]
        result.setdefault(node_id, []).extend(chains)

    _add_relation_endpoints(
        result,
        overlay.edge_ids,
        graph_edges,
        evidence,
        paths_by_evidence_id,
        producer="relation_endpoint",
    )
    _add_projection_ancestors(
        result,
        overlay,
        graph_placements,
        graph_ownership,
    )
    return result


def _transformation_paths(
    overlay: StructuralFocusOverlay,
    group: TransformationStructuralClosureGroup | None,
    evidence: dict[str, EvidenceItem],
    node_by_review_id: dict[str, str],
    graph_edges,
    graph_placements,
    graph_ownership,
) -> dict[str, list[AttributionPath]]:
    if group is None:
        return {}
    result: dict[str, list[AttributionPath]] = {}
    seed_chains: dict[str, list[AttributionPath]] = {}
    path_chains: dict[str, list[AttributionPath]] = {}
    for seed_id in group.seed_evidence_ids:
        fact = evidence.get(seed_id)
        node_id = _node_id(fact, node_by_review_id)
        if node_id is None:
            continue
        chain = AttributionPath(
            (AttributionStep("transformation_selector", (seed_id,)),)
        )
        result.setdefault(node_id, []).append(chain)
        seed_chains.setdefault(seed_id, []).append(chain)
    for path_id in group.path_evidence_ids:
        sponsors = tuple(
            seed_id
            for seed_id in group.seed_evidence_ids
            if path_id in evidence[seed_id].structural_path_ids
        )
        chains = [
            _append(path, "structural_path", (path_id,))
            for seed_id in sponsors
            for path in seed_chains.get(seed_id, ())
        ]
        path_chains[path_id] = chains
        for review_id in path_review_ids(evidence.get(path_id), evidence):
            node_id = node_by_review_id.get(review_id)
            if node_id is not None:
                result.setdefault(node_id, []).extend(chains)
    _add_relation_endpoints(
        result,
        overlay.edge_ids,
        graph_edges,
        evidence,
        path_chains,
        producer="relation_endpoint",
    )
    _add_projection_ancestors(
        result,
        overlay,
        graph_placements,
        graph_ownership,
    )
    return result


def _add_relation_endpoints(
    result: dict[str, list[AttributionPath]],
    edge_ids: tuple[str, ...],
    graph_edges,
    evidence: dict[str, EvidenceItem],
    path_chains: dict[str, list[AttributionPath]],
    *,
    producer: str,
) -> None:
    for edge_id in edge_ids:
        edge = graph_edges[edge_id]
        fact = evidence.get(edge.relation_change_evidence_id)
        supporting_paths = (
            fact.structural_path_ids if fact is not None else ()
        )
        chains = [
            _append(path, producer, (edge_id,))
            for path_id in supporting_paths
            for path in path_chains.get(path_id, ())
        ]
        if not chains:
            endpoint_paths = (
                *result.get(edge.source_node_id, ()),
                *result.get(edge.target_node_id, ()),
            )
            chains = [
                _append(path, producer, (edge_id,)) for path in endpoint_paths
            ]
        for node_id in (edge.source_node_id, edge.target_node_id):
            result.setdefault(node_id, []).extend(chains)


def _add_projection_ancestors(
    result: dict[str, list[AttributionPath]],
    overlay: StructuralFocusOverlay,
    graph_placements,
    graph_ownership,
) -> None:
    for placement_id in overlay.placement_ids:
        placement = graph_placements[placement_id]
        child_paths = tuple(result.get(placement.child_node_id, ()))
        result.setdefault(placement.parent_node_id, []).extend(
            _append(path, "placement_ancestor", (placement_id,))
            for path in child_paths
        )
    changed = True
    selected_ownership = tuple(
        graph_ownership[item] for item in overlay.ownership_edge_ids
    )
    while changed:
        changed = False
        for edge in selected_ownership:
            child_paths = tuple(result.get(edge.child_node_id, ()))
            before = len(result.get(edge.parent_node_id, ()))
            result.setdefault(edge.parent_node_id, []).extend(
                _append(path, "ownership_ancestor", (edge.id,))
                for path in child_paths
            )
            result[edge.parent_node_id] = list(
                _canonical_paths(result[edge.parent_node_id])
            )
            changed = changed or len(result[edge.parent_node_id]) > before


def _edge_paths(edge_id, paths, graph_edges, *, producer):
    edge = graph_edges[edge_id]
    return tuple(
        _append(path, producer, (edge_id,))
        for node_id in (edge.source_node_id, edge.target_node_id)
        for path in paths.get(node_id, ())
    )


def _node_id(
    fact: EvidenceItem | None,
    node_by_review_id: dict[str, str],
) -> str | None:
    review_id = review_symbol_id(fact)
    return node_by_review_id.get(review_id) if review_id is not None else None


def _append(
    path: AttributionPath,
    producer_class: str,
    source_ids: tuple[str, ...],
) -> AttributionPath:
    if any(
        step.producer_class == producer_class
        and set(step.source_ids) & set(source_ids)
        for step in path.steps
    ):
        return path
    return AttributionPath((*path.steps, AttributionStep(producer_class, source_ids)))


def _canonical_paths(paths: Iterable[AttributionPath]) -> tuple[AttributionPath, ...]:
    grouped: dict[tuple[str, ...], list[set[str]]] = {}
    for path in paths:
        key = tuple(step.producer_class for step in path.steps)
        sources = grouped.setdefault(key, [set() for _ in path.steps])
        for index, step in enumerate(path.steps):
            sources[index].update(step.source_ids)
    canonical = tuple(
        AttributionPath(
            tuple(
                AttributionStep(producer, tuple(sorted(sources[index])))
                for index, producer in enumerate(key)
            )
        )
        for key, sources in sorted(grouped.items())
    )
    producer_sets = tuple(
        frozenset(step.producer_class for step in path.steps)
        for path in canonical
    )
    return tuple(
        path
        for index, path in enumerate(canonical)
        if not any(
            other < producer_sets[index]
            for other_index, other in enumerate(producer_sets)
            if other_index != index
        )
    )


def _membership_survives(
    membership: MembershipAttribution,
    disabled: frozenset[str],
) -> bool:
    if not membership.paths:
        return True
    return any(
        not disabled & {step.producer_class for step in path.steps}
        for path in membership.paths
    )


def _aggregate_outcomes(
    reports: tuple[CounterfactualReport, ...],
) -> tuple[CounterfactualOutcome, ...]:
    fields = (
        "focus_count",
        "unresolved_count",
        "unsupported_membership_count",
        "node_false_inclusions",
        "node_false_exclusions",
        "node_role_disagreements",
        "relation_false_inclusions",
        "relation_false_exclusions",
    )
    aggregate: dict[str, dict[str, int]] = {}
    for report in reports:
        for outcome in report.outcomes:
            counts = aggregate.setdefault(
                outcome.subject_kind,
                {field: 0 for field in fields},
            )
            for field in fields:
                counts[field] += getattr(outcome, field)
    return tuple(
        CounterfactualOutcome(subject_kind=kind, **counts)
        for kind, counts in sorted(aggregate.items())
    )


def _validate_attribution(
    attribution: StructuralFocusAttribution,
    packet: StructuralCorrectnessPacket,
    observation: StructuralCorrectnessObservation,
) -> None:
    if attribution.packet_digest != packet.digest:
        raise ValueError("structural attribution does not match frozen packet")
    observed = {item.subject_id: item for item in observation.focuses}
    if {item.subject_id for item in attribution.focuses} != set(observed):
        raise ValueError("structural attribution must dispose every observed focus")
    for focus in attribution.focuses:
        expected = observed[focus.subject_id]
        expected_ids = {
            *(('node', item) for item in expected.direct_node_ids),
            *(('node', item) for item in expected.context_node_ids),
            *(('exact_relation', item) for item in expected.exact_relation_ids),
        }
        actual_ids = {
            (item.member_kind, item.member_id) for item in focus.memberships
        }
        if actual_ids != expected_ids:
            raise ValueError(
                f"{focus.subject_id}: attribution must dispose exact observation membership"
            )
