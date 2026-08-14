from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from html import escape
from pathlib import Path
from typing import Any, Literal, Mapping

from repodelta.model.contracts import (
    ReviewBrief,
    StructuralOverviewFocus,
    VerificationEvidenceInspection,
)


PACKET_SCHEMA = "structural_correctness_packet.v3"
LEGACY_PACKET_SCHEMA = "structural_correctness_packet.v2"
OBSERVATION_SCHEMA = "structural_correctness_observation.v2"
LABELS_SCHEMA = "structural_correctness_labels.v3"
LEGACY_LABELS_SCHEMA = "structural_correctness_labels.v2"


@dataclass(frozen=True)
class StructuralCandidate:
    file_node_id: str
    path: str
    operation: str
    member_node_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class StructuralSymbolCandidate:
    node_id: str
    file_node_id: str
    path: str
    qualified_name: str
    symbol_kind: str
    operation: str


@dataclass(frozen=True)
class StructuralRelationCandidate:
    relation_id: str
    source_node_id: str
    target_node_id: str
    relation: str
    operation: str


@dataclass(frozen=True)
class ChangedSurface:
    base_path: str | None
    head_path: str | None
    status: str
    additions: int | None
    deletions: int | None
    hunk_headers: tuple[str, ...] = ()


@dataclass(frozen=True)
class StructuralSeedCoverage:
    provider_symbol_id: str
    node_id: str | None
    state: Literal["complete", "truncated", "unknown"]


@dataclass(frozen=True)
class StructuralCoverageSnapshot:
    state: str
    provider: str
    hunk_count: int
    mapped_hunk_count: int
    symbol_count: int
    path_count: int
    seed_count: int
    complete_seed_count: int
    truncated_seed_count: int
    requested_files: int
    indexed_files: int
    missing_reason: str
    base_state: str
    base_mapped_hunk_count: int
    base_hunk_count: int
    base_symbol_count: int
    seed_mapping_state: Literal["complete", "incomplete", "legacy_unavailable"]
    seeds: tuple[StructuralSeedCoverage, ...] = ()

    def __post_init__(self) -> None:
        counts = (
            self.hunk_count,
            self.mapped_hunk_count,
            self.symbol_count,
            self.path_count,
            self.seed_count,
            self.complete_seed_count,
            self.truncated_seed_count,
            self.requested_files,
            self.indexed_files,
            self.base_mapped_hunk_count,
            self.base_hunk_count,
            self.base_symbol_count,
        )
        if any(isinstance(item, bool) or item < 0 for item in counts):
            raise ValueError("coverage counts must be non-negative integers")
        if self.mapped_hunk_count > self.hunk_count:
            raise ValueError("mapped hunk coverage cannot exceed hunk count")
        if self.complete_seed_count + self.truncated_seed_count > self.seed_count:
            raise ValueError("disposed seed coverage cannot exceed seed count")
        if len({item.provider_symbol_id for item in self.seeds}) != len(self.seeds):
            raise ValueError("coverage contains duplicate seed identities")
        if self.seed_mapping_state == "complete" and (
            len(self.seeds) != self.seed_count
            or sum(item.state == "complete" for item in self.seeds)
            != self.complete_seed_count
            or sum(item.state == "truncated" for item in self.seeds)
            != self.truncated_seed_count
            or any(item.node_id is None for item in self.seeds)
        ):
            raise ValueError("complete seed mapping must dispose every exact seed")


@dataclass(frozen=True)
class StructuralSubject:
    subject_id: str
    subject_kind: str
    authored_statement: str


@dataclass(frozen=True)
class StructuralCorrectnessPacket:
    repository: str
    pull_request: int | None
    base_sha: str | None
    head_sha: str | None
    candidates: tuple[StructuralCandidate, ...]
    symbols: tuple[StructuralSymbolCandidate, ...]
    relations: tuple[StructuralRelationCandidate, ...]
    changed_surfaces: tuple[ChangedSurface, ...]
    subjects: tuple[StructuralSubject, ...]
    relation_ids: tuple[str, ...]
    coverage: StructuralCoverageSnapshot
    schema_version: str = PACKET_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version not in {PACKET_SCHEMA, LEGACY_PACKET_SCHEMA} or not self.repository:
            raise ValueError("invalid structural correctness packet identity")
        _unique((item.file_node_id for item in self.candidates), "candidate files")
        _unique((item.subject_id for item in self.subjects), "subjects")
        _unique((item.node_id for item in self.symbols), "symbol candidates")
        _unique((item.relation_id for item in self.relations), "relation candidates")
        _unique(self.relation_ids, "relations")
        file_ids = {item.file_node_id for item in self.candidates}
        node_ids = file_ids | {item.node_id for item in self.symbols}
        if not {item.file_node_id for item in self.symbols} <= file_ids:
            raise ValueError("symbol candidates contain unknown file identities")
        if any(
            item.source_node_id not in node_ids or item.target_node_id not in node_ids
            for item in self.relations
        ):
            raise ValueError("relation candidates contain unknown node identities")
        if any(
            item.node_id is not None and item.node_id not in node_ids
            for item in self.coverage.seeds
        ):
            raise ValueError("coverage contains unknown seed node identities")

    @property
    def digest(self) -> str:
        raw = asdict(self)
        if self.schema_version == LEGACY_PACKET_SCHEMA:
            raw["coverage_state"] = self.coverage.state
            raw.pop("coverage")
        payload = json.dumps(raw, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class ObservedFile:
    file_node_id: str
    role: str


@dataclass(frozen=True)
class ObservedFocus:
    subject_id: str
    direct_file_node_ids: tuple[str, ...]
    context_file_node_ids: tuple[str, ...]
    relation_ids: tuple[str, ...]
    disposition_state: str
    direct_node_ids: tuple[str, ...] = ()
    context_node_ids: tuple[str, ...] = ()
    exact_relation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class StructuralCorrectnessObservation:
    packet_digest: str
    files: tuple[ObservedFile, ...]
    focuses: tuple[ObservedFocus, ...]
    schema_version: str = OBSERVATION_SCHEMA


LabelDisposition = Literal["included", "excluded", "unresolved"]


@dataclass(frozen=True)
class HumanFileLabel:
    file_node_id: str
    disposition: LabelDisposition
    role: str | None = None


@dataclass(frozen=True)
class HumanFocusLabel:
    subject_id: str
    direct_file_node_ids: tuple[str, ...] = ()
    context_file_node_ids: tuple[str, ...] = ()
    unresolved: bool = False
    equivalent_to: tuple[str, ...] = ()
    direct_node_ids: tuple[str, ...] = ()
    context_node_ids: tuple[str, ...] = ()
    relation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReferenceAuthority:
    status: Literal["proposed", "adjudicated"]
    prepared_by: str
    accepted_by: str = ""
    proposal_digest: str = ""


@dataclass(frozen=True)
class StructuralCorrectnessLabels:
    packet_digest: str
    files: tuple[HumanFileLabel, ...]
    focuses: tuple[HumanFocusLabel, ...]
    authority: ReferenceAuthority = ReferenceAuthority(
        "proposed", "unassigned"
    )
    schema_version: str = LABELS_SCHEMA

    @property
    def proposal_digest(self) -> str:
        payload = json.dumps(
            {
                "packet_digest": self.packet_digest,
                "files": [asdict(item) for item in self.files],
                "focuses": [asdict(item) for item in self.focuses],
                "prepared_by": self.authority.prepared_by,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def __post_init__(self) -> None:
        if self.schema_version not in {LABELS_SCHEMA, LEGACY_LABELS_SCHEMA}:
            raise ValueError("invalid structural correctness labels identity")
        authority = self.authority
        if not authority.prepared_by:
            raise ValueError("reference authority requires a preparer")
        if authority.status == "proposed" and (
            authority.accepted_by or authority.proposal_digest
        ):
            raise ValueError("proposed reference cannot claim adjudication")
        if authority.status == "adjudicated" and (
            not authority.accepted_by
            or authority.proposal_digest != self.proposal_digest
        ):
            raise ValueError(
                "adjudication must bind the exact proposed decision identity"
            )


def prepare_structural_correctness_label_template(
    packet: StructuralCorrectnessPacket,
    *,
    prepared_by: str = "unassigned",
) -> StructuralCorrectnessLabels:
    return StructuralCorrectnessLabels(
        packet_digest=packet.digest,
        files=tuple(
            HumanFileLabel(item.file_node_id, "unresolved")
            for item in packet.candidates
        ),
        focuses=tuple(
            HumanFocusLabel(item.subject_id, unresolved=True)
            for item in packet.subjects
        ),
        authority=ReferenceAuthority("proposed", prepared_by),
    )


def adjudicate_structural_correctness_labels(
    labels: StructuralCorrectnessLabels,
    *,
    accepted_by: str,
) -> StructuralCorrectnessLabels:
    if labels.authority.status != "proposed":
        raise ValueError("only a proposed reference can be adjudicated")
    if not accepted_by.strip():
        raise ValueError("adjudication requires an acceptance owner")
    return replace(
        labels,
        authority=ReferenceAuthority(
            status="adjudicated",
            prepared_by=labels.authority.prepared_by,
            accepted_by=accepted_by.strip(),
            proposal_digest=labels.proposal_digest,
        ),
    )


def prepare_structural_correctness_packet(
    brief: ReviewBrief,
) -> StructuralCorrectnessPacket:
    graph = brief.projection.review_graph
    subjects = []
    for item in brief.projection.verification_workspace.matrix:
        subjects.append(
            StructuralSubject(
                subject_id=item.subject_id,
                subject_kind=item.subject_kind,
                authored_statement=item.text,
            )
        )
    evidence = brief.evidence_catalog.by_id()
    file_nodes = []
    node_path: dict[str, str] = {}
    node_fact = {}
    for item in graph.nodes:
        fact = evidence.get(item.display_evidence_id)
        if fact is None:
            continue
        node_fact[item.id] = fact
        path = str(fact.metadata.get("path", ""))
        if path:
            node_path[item.id] = path
        if fact.metadata.get("symbol_kind") == "file":
            file_nodes.append(item)
    candidates = tuple(
        StructuralCandidate(
            file_node_id=item.id,
            path=node_path[item.id],
            operation=item.delta,
            member_node_ids=tuple(
                node.id
                for node in graph.nodes
                if node.id != item.id and node_path.get(node.id) == node_path[item.id]
            ),
        )
        for item in file_nodes
    )
    file_id_by_path = {item.path: item.file_node_id for item in candidates}
    symbols = tuple(
        StructuralSymbolCandidate(
            node_id=item.id,
            file_node_id=file_id_by_path[node_path[item.id]],
            path=node_path[item.id],
            qualified_name=str(
                node_fact[item.id].metadata.get("qualified_name", "")
                or node_fact[item.id].summary
            ),
            symbol_kind=str(
                node_fact[item.id].metadata.get("symbol_kind", "unknown")
            ),
            operation=item.delta,
        )
        for item in graph.nodes
        if item.id not in {file.id for file in file_nodes}
        and node_path.get(item.id) in file_id_by_path
    )
    coverage = _coverage_snapshot(brief, graph.nodes)
    return StructuralCorrectnessPacket(
        repository=brief.packet.repository,
        pull_request=brief.packet.pull_request,
        base_sha=brief.packet.base_sha,
        head_sha=brief.packet.head_sha,
        candidates=candidates,
        symbols=symbols,
        relations=tuple(
            StructuralRelationCandidate(
                relation_id=item.id,
                source_node_id=item.source_node_id,
                target_node_id=item.target_node_id,
                relation=item.relation,
                operation=item.operation,
            )
            for item in graph.relation_groups
        ),
        changed_surfaces=tuple(
            ChangedSurface(
                base_path=item.base_path,
                head_path=item.head_path,
                status=item.status,
                additions=item.additions,
                deletions=item.deletions,
                hunk_headers=tuple(
                    line.strip()
                    for line in (item.patch or "").splitlines()
                    if line.startswith("@@")
                )[:32],
            )
            for item in brief.packet.changed_files
        ),
        subjects=tuple(subjects),
        relation_ids=tuple(
            dict.fromkeys((
                *(item.id for item in graph.relation_groups),
                *(item.id for item in brief.projection.structural_overview.relations),
            ))
        ),
        coverage=coverage,
    )


def _coverage_snapshot(brief: ReviewBrief, graph_nodes) -> StructuralCoverageSnapshot:
    coverage = brief.overview.structural_coverage
    node_id_by_review_symbol_id = {
        item.review_symbol_id: item.id for item in graph_nodes
    }
    truncated_provider_ids = {
        affected_id
        for diagnostic in brief.projection_candidates.diagnostics
        if diagnostic.scope == "review"
        and diagnostic.slot == "structural_path"
        and diagnostic.state == "budget_truncated"
        for affected_id in diagnostic.affected_ids
    }
    seed_facts = tuple(
        item
        for item in brief.evidence_catalog.items
        if item.kind == "symbol"
        and item.changed
        and item.revision_side == "head"
        and item.metadata.get("symbol_id")
        and item.metadata.get("review_symbol_id")
    )
    seeds = tuple(
        StructuralSeedCoverage(
            provider_symbol_id=str(item.metadata["symbol_id"]),
            node_id=node_id_by_review_symbol_id.get(
                str(item.metadata["review_symbol_id"])
            ),
            state=(
                "truncated"
                if item.metadata["symbol_id"] in truncated_provider_ids
                else "complete"
            ),
        )
        for item in seed_facts
    )
    mapping_complete = (
        len(seeds) == coverage.seed_count
        and sum(item.state == "complete" for item in seeds)
        == coverage.complete_seed_count
        and sum(item.state == "truncated" for item in seeds)
        == coverage.truncated_seed_count
        and all(item.node_id is not None for item in seeds)
    )
    return StructuralCoverageSnapshot(
        state=coverage.state,
        provider=coverage.provider,
        hunk_count=coverage.hunk_count,
        mapped_hunk_count=coverage.mapped_hunk_count,
        symbol_count=coverage.symbol_count,
        path_count=coverage.path_count,
        seed_count=coverage.seed_count,
        complete_seed_count=coverage.complete_seed_count,
        truncated_seed_count=coverage.truncated_seed_count,
        requested_files=coverage.requested_files,
        indexed_files=coverage.indexed_files,
        missing_reason=coverage.missing_reason,
        base_state=coverage.base_state,
        base_mapped_hunk_count=coverage.base_mapped_hunk_count,
        base_hunk_count=coverage.base_hunk_count,
        base_symbol_count=coverage.base_symbol_count,
        seed_mapping_state="complete" if mapping_complete else "incomplete",
        seeds=seeds,
    )


def observe_structural_correctness(
    brief: ReviewBrief,
    packet: StructuralCorrectnessPacket,
) -> StructuralCorrectnessObservation:
    current = prepare_structural_correctness_packet(brief)
    if current != packet:
        raise ValueError("structural correctness packet does not match current review")
    overview = brief.projection.structural_overview
    inspections = {
        item.subject_id: item
        for item in brief.projection.verification_workspace.inspections
    }
    relation_group_by_edge_id = {
        edge_id: group.id
        for group in brief.projection.review_graph.relation_groups
        for edge_id in group.member_edge_ids
    }
    return StructuralCorrectnessObservation(
        packet_digest=packet.digest,
        files=tuple(ObservedFile(item.file_node_id, item.role) for item in overview.files),
        focuses=tuple(
            _observe_focus(
                item,
                inspections.get(item.subject_id),
                relation_group_by_edge_id,
            )
            for item in overview.focuses
        ),
    )


def _observe_focus(
    overview_focus: StructuralOverviewFocus,
    inspection: VerificationEvidenceInspection | None,
    relation_group_by_edge_id: Mapping[str, str],
) -> ObservedFocus:
    overlay = inspection.structural_overlay if inspection is not None else None
    direct_node_ids = ()
    context_node_ids = ()
    exact_relation_ids = ()
    if overlay is not None:
        direct_node_ids = tuple(
            sorted(
                item.node_id
                for item in overlay.nodes
                if item.role != "intermediate"
            )
        )
        context_node_ids = tuple(
            sorted(
                item.node_id
                for item in overlay.nodes
                if item.role == "intermediate"
            )
        )
        exact_relation_ids = tuple(
            sorted(
                {
                    *overlay.relation_group_ids,
                    *(
                        relation_group_by_edge_id[edge_id]
                        for edge_id in overlay.edge_ids
                        if edge_id in relation_group_by_edge_id
                    ),
                }
            )
        )
    return ObservedFocus(
        overview_focus.subject_id,
        overview_focus.direct_file_node_ids,
        overview_focus.context_file_node_ids,
        overview_focus.relation_ids,
        overview_focus.structural_disposition.state,
        direct_node_ids,
        context_node_ids,
        exact_relation_ids,
    )


def write_json_artifact(value: object, output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(value), indent=2, sort_keys=True) + "\n")
    return path


def load_packet(path: str | Path) -> StructuralCorrectnessPacket:
    raw = _mapping_one_of(path, {PACKET_SCHEMA, LEGACY_PACKET_SCHEMA})
    schema_version = _string(raw, "schema_version")
    return StructuralCorrectnessPacket(
        repository=_string(raw, "repository"),
        pull_request=_optional_int(raw.get("pull_request")),
        base_sha=_optional_string(raw.get("base_sha")),
        head_sha=_optional_string(raw.get("head_sha")),
        candidates=tuple(
            StructuralCandidate(
                file_node_id=_string(item, "file_node_id"),
                path=_string(item, "path"),
                operation=_string(item, "operation"),
                member_node_ids=_strings(item.get("member_node_ids", [])),
            )
            for item in _objects(raw, "candidates")
        ),
        symbols=tuple(
            StructuralSymbolCandidate(
                node_id=_string(item, "node_id"),
                file_node_id=_string(item, "file_node_id"),
                path=_string(item, "path"),
                qualified_name=_string(item, "qualified_name"),
                symbol_kind=_string(item, "symbol_kind"),
                operation=_string(item, "operation"),
            )
            for item in _objects(raw, "symbols")
        ),
        relations=tuple(
            StructuralRelationCandidate(
                relation_id=_string(item, "relation_id"),
                source_node_id=_string(item, "source_node_id"),
                target_node_id=_string(item, "target_node_id"),
                relation=_string(item, "relation"),
                operation=_string(item, "operation"),
            )
            for item in _objects(raw, "relations")
        ),
        changed_surfaces=tuple(
            ChangedSurface(
                base_path=_optional_string(item.get("base_path")),
                head_path=_optional_string(item.get("head_path")),
                status=_string(item, "status"),
                additions=_optional_non_negative_int(item.get("additions")),
                deletions=_optional_non_negative_int(item.get("deletions")),
                hunk_headers=_strings(item.get("hunk_headers", [])),
            )
            for item in _objects(raw, "changed_surfaces")
        ),
        subjects=tuple(
            StructuralSubject(
                subject_id=_string(item, "subject_id"),
                subject_kind=_string(item, "subject_kind"),
                authored_statement=_string(item, "authored_statement"),
            )
            for item in _objects(raw, "subjects")
        ),
        relation_ids=_strings(raw.get("relation_ids", [])),
        coverage=(
            _load_coverage(raw.get("coverage"))
            if schema_version == PACKET_SCHEMA
            else _legacy_coverage(_string(raw, "coverage_state"))
        ),
        schema_version=schema_version,
    )


def load_observation(path: str | Path) -> StructuralCorrectnessObservation:
    raw = _mapping(path, OBSERVATION_SCHEMA)
    return StructuralCorrectnessObservation(
        packet_digest=_string(raw, "packet_digest"),
        files=tuple(
            ObservedFile(_string(item, "file_node_id"), _string(item, "role"))
            for item in _objects(raw, "files")
        ),
        focuses=tuple(
            ObservedFocus(
                _string(item, "subject_id"),
                _strings(item.get("direct_file_node_ids", [])),
                _strings(item.get("context_file_node_ids", [])),
                _strings(item.get("relation_ids", [])),
                _string(item, "disposition_state"),
                _strings(item.get("direct_node_ids", [])),
                _strings(item.get("context_node_ids", [])),
                _strings(item.get("exact_relation_ids", [])),
            )
            for item in _objects(raw, "focuses")
        ),
        schema_version=_string(raw, "schema_version"),
    )


def load_labels(
    path: str | Path, packet: StructuralCorrectnessPacket
) -> StructuralCorrectnessLabels:
    raw = _mapping_one_of(path, {LABELS_SCHEMA, LEGACY_LABELS_SCHEMA})
    schema_version = _string(raw, "schema_version")
    labels = StructuralCorrectnessLabels(
        packet_digest=_string(raw, "packet_digest"),
        files=tuple(
            HumanFileLabel(
                _string(item, "file_node_id"),
                _string(item, "disposition"),  # type: ignore[arg-type]
                _optional_string(item.get("role")),
            )
            for item in _objects(raw, "files")
        ),
        focuses=tuple(
            HumanFocusLabel(
                _string(item, "subject_id"),
                _strings(item.get("direct_file_node_ids", [])),
                _strings(item.get("context_file_node_ids", [])),
                bool(item.get("unresolved", False)),
                _strings(item.get("equivalent_to", [])),
                _strings(item.get("direct_node_ids", [])),
                _strings(item.get("context_node_ids", [])),
                _strings(item.get("relation_ids", [])),
            )
            for item in _objects(raw, "focuses")
        ),
        authority=(
            _load_reference_authority(raw.get("authority"))
            if schema_version == LABELS_SCHEMA
            else ReferenceAuthority("proposed", "legacy-unverified")
        ),
        schema_version=schema_version,
    )
    _validate_labels(labels, packet)
    return labels


def write_comparison_html(
    packet_path: str | Path,
    observation_path: str | Path,
    labels_path: str | Path,
    output: str | Path,
) -> Path:
    packet = load_packet(packet_path)
    observation = load_observation(observation_path)
    labels = load_labels(labels_path, packet)
    if observation.packet_digest != packet.digest:
        raise ValueError("structural observation does not match frozen packet")
    _validate_observation(observation, packet)
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render(packet, observation, labels), encoding="utf-8")
    return path


def _validate_labels(
    labels: StructuralCorrectnessLabels, packet: StructuralCorrectnessPacket
) -> None:
    if labels.packet_digest != packet.digest:
        raise ValueError("structural labels do not match frozen packet")
    candidate_ids = {item.file_node_id for item in packet.candidates}
    node_ids = candidate_ids | {item.node_id for item in packet.symbols}
    relation_ids = {item.relation_id for item in packet.relations}
    subject_ids = {item.subject_id for item in packet.subjects}
    _unique((item.file_node_id for item in labels.files), "file labels")
    _unique((item.subject_id for item in labels.focuses), "focus labels")
    if {item.file_node_id for item in labels.files} != candidate_ids:
        raise ValueError("structural labels must dispose every candidate file")
    if {item.subject_id for item in labels.focuses} != subject_ids:
        raise ValueError("structural labels must dispose every subject")
    by_subject = {item.subject_id: item for item in labels.focuses}
    for item in labels.files:
        if item.disposition not in {"included", "excluded", "unresolved"}:
            raise ValueError("unsupported structural file disposition")
        if item.disposition == "included" and item.role not in {
            "changed", "retained_bridge", "retained_context"
        }:
            raise ValueError("included structural file requires a valid role")
        if item.disposition != "included" and item.role is not None:
            raise ValueError("excluded or unresolved file cannot carry a role")
    for item in labels.focuses:
        file_memberships = {
            *item.direct_file_node_ids,
            *item.context_file_node_ids,
        }
        node_memberships = {*item.direct_node_ids, *item.context_node_ids}
        if not file_memberships <= candidate_ids:
            raise ValueError("focus labels contain unknown candidate files")
        if not node_memberships <= node_ids:
            raise ValueError("focus labels contain unknown candidate nodes")
        if not set(item.relation_ids) <= relation_ids:
            raise ValueError("focus labels contain unknown candidate relations")
        if set(item.direct_file_node_ids) & set(item.context_file_node_ids):
            raise ValueError("focus direct and context memberships must be distinct")
        if set(item.direct_node_ids) & set(item.context_node_ids):
            raise ValueError(
                "focus direct and context node memberships must be distinct"
            )
        if not set(item.equivalent_to) <= subject_ids - {item.subject_id}:
            raise ValueError("focus equivalence contains unknown subjects")
        for peer_id in item.equivalent_to:
            peer = by_subject[peer_id]
            if (
                set(item.direct_file_node_ids),
                set(item.context_file_node_ids),
                item.unresolved,
                set(item.direct_node_ids),
                set(item.context_node_ids),
                set(item.relation_ids),
            ) != (
                set(peer.direct_file_node_ids),
                set(peer.context_file_node_ids),
                peer.unresolved,
                set(peer.direct_node_ids),
                set(peer.context_node_ids),
                set(peer.relation_ids),
            ):
                raise ValueError("equivalent focuses must have equal human memberships")


def _validate_observation(
    observation: StructuralCorrectnessObservation,
    packet: StructuralCorrectnessPacket,
) -> None:
    candidate_ids = {item.file_node_id for item in packet.candidates}
    node_ids = candidate_ids | {item.node_id for item in packet.symbols}
    exact_relation_ids = {item.relation_id for item in packet.relations}
    subject_ids = {item.subject_id for item in packet.subjects}
    _unique((item.file_node_id for item in observation.files), "observed files")
    _unique((item.subject_id for item in observation.focuses), "observed focuses")
    if not {item.file_node_id for item in observation.files} <= candidate_ids:
        raise ValueError("structural observation contains unknown candidate files")
    if {item.subject_id for item in observation.focuses} != subject_ids:
        raise ValueError("structural observation must dispose every subject")
    for item in observation.files:
        if item.role not in {"changed", "retained_bridge", "retained_context"}:
            raise ValueError("structural observation contains an invalid file role")
    for item in observation.focuses:
        if not set((*item.direct_file_node_ids, *item.context_file_node_ids)) <= candidate_ids:
            raise ValueError("structural observation focus contains unknown files")
        if set(item.direct_file_node_ids) & set(item.context_file_node_ids):
            raise ValueError("observed direct and context memberships must be distinct")
        if not set(item.relation_ids) <= set(packet.relation_ids):
            raise ValueError("structural observation focus contains unknown relations")
        if not set((*item.direct_node_ids, *item.context_node_ids)) <= node_ids:
            raise ValueError("structural observation focus contains unknown nodes")
        if set(item.direct_node_ids) & set(item.context_node_ids):
            raise ValueError(
                "observed direct and context node memberships must be distinct"
            )
        if not set(item.exact_relation_ids) <= exact_relation_ids:
            raise ValueError(
                "structural observation focus contains unknown exact relations"
            )


def _render(packet, observation, labels) -> str:
    observed_files = {item.file_node_id: item for item in observation.files}
    rows = []
    counts = {"match": 0, "false inclusion": 0, "false exclusion": 0, "role disagreement": 0, "unresolved": 0}
    for label in labels.files:
        observed = observed_files.get(label.file_node_id)
        if label.disposition == "unresolved": state = "unresolved"
        elif observed is None and label.disposition == "included": state = "false exclusion"
        elif observed is not None and label.disposition == "excluded": state = "false inclusion"
        elif observed is not None and observed.role != label.role: state = "role disagreement"
        else: state = "match"
        counts[state] += 1
        candidate = next(item for item in packet.candidates if item.file_node_id == label.file_node_id)
        rows.append(f"<tr class='{state.replace(' ', '-')}'><td>{escape(candidate.path)}</td><td>{escape(observed.role if observed else 'not projected')}</td><td>{escape(label.disposition + ((' · ' + label.role) if label.role else ''))}</td><td>{escape(state)}</td></tr>")
    focus_rows = []
    observed_focus = {item.subject_id: item for item in observation.focuses}
    for label in labels.focuses:
        observed = observed_focus.get(label.subject_id)
        file_result = _role_comparison(
            observed.direct_file_node_ids if observed else (),
            observed.context_file_node_ids if observed else (),
            label.direct_file_node_ids,
            label.context_file_node_ids,
        )
        node_result = _role_comparison(
            observed.direct_node_ids if observed else (),
            observed.context_node_ids if observed else (),
            label.direct_node_ids,
            label.context_node_ids,
        )
        projected_relations = set(observed.exact_relation_ids if observed else ())
        expected_relations = set(label.relation_ids)
        relation_result = _set_comparison(
            projected_relations,
            expected_relations,
        )
        focus_coverage = _focus_coverage(packet, label)
        focus_rows.append(
            "<tr>"
            f"<td>{escape(label.subject_id)}</td>"
            f"<td>{_comparison_html(file_result)}</td>"
            f"<td>{_comparison_html(node_result)}</td>"
            f"<td>{_comparison_html(relation_result)}</td>"
            f"<td>{'yes' if label.unresolved else 'no'}</td>"
            f"<td>{escape(focus_coverage)}</td>"
            "</tr>"
        )
    cards = ''.join(f"<div><span>{escape(key)}</span><strong>{value}</strong></div>" for key, value in counts.items())
    title = f"{packet.repository} · PR #{packet.pull_request} · structural correctness"
    coverage = packet.coverage
    coverage_summary = (
        f"{coverage.state} · {coverage.mapped_hunk_count}/{coverage.hunk_count} "
        f"hunks mapped · {coverage.complete_seed_count}/{coverage.seed_count} "
        f"seeds complete · mapping {coverage.seed_mapping_state}"
    )
    authority = labels.authority
    authority_summary = (
        f"{authority.status} reference prepared by {authority.prepared_by}"
        + (
            f" · adjudicated by {authority.accepted_by}"
            if authority.status == "adjudicated"
            else " · not human-adjudicated"
        )
    )
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{escape(title)}</title><style>{_CSS}</style></head><body><main><header><p>Non-authoritative evaluation</p><h1>{escape(title)}</h1><p>{escape(authority_summary)}. File, node-role, exact-relation, and coverage truth remain distinct. This report does not change assessment or mergeability.</p><code>{escape(packet.digest)}</code></header><section><h2>File overview</h2><div class='cards'>{cards}</div><table><thead><tr><th>Candidate</th><th>RepoDelta</th><th>Reference</th><th>Result</th></tr></thead><tbody>{''.join(rows)}</tbody></table></section><section><h2>Focus membership</h2><table><thead><tr><th>Subject</th><th>Files</th><th>Nodes and roles</th><th>Exact relations</th><th>Reference unresolved</th><th>Reference coverage</th></tr></thead><tbody>{''.join(focus_rows)}</tbody></table></section><footer>Coverage: {escape(coverage_summary)}</footer></main></body></html>"""


def _focus_coverage(
    packet: StructuralCorrectnessPacket,
    label: HumanFocusLabel,
) -> str:
    if label.unresolved:
        return "reference unresolved"
    memberships = {
        *label.direct_file_node_ids,
        *label.context_file_node_ids,
        *label.direct_node_ids,
        *label.context_node_ids,
        *label.relation_ids,
    }
    if not memberships:
        return "not required for empty reference"
    if packet.coverage.seed_mapping_state != "complete":
        return "unknown · exact seed mapping unavailable"
    direct_nodes = set(label.direct_node_ids)
    relevant = tuple(
        item
        for item in packet.coverage.seeds
        if item.node_id in direct_nodes
    )
    if not relevant:
        return "unknown · no admitted direct seed"
    if any(item.state == "truncated" for item in relevant):
        return "limited · admitted seed truncated"
    if any(item.state == "unknown" for item in relevant):
        return "unknown · admitted seed state unavailable"
    return "complete for admitted direct seeds"


def _role_comparison(
    observed_direct,
    observed_context,
    expected_direct,
    expected_context,
):
    observed = {
        **{item: "direct" for item in observed_direct},
        **{item: "context" for item in observed_context},
    }
    expected = {
        **{item: "direct" for item in expected_direct},
        **{item: "context" for item in expected_context},
    }
    shared = {
        item for item in observed.keys() & expected.keys()
        if observed[item] == expected[item]
    }
    role_disagreements = {
        f"{item} ({observed[item]}→{expected[item]})"
        for item in observed.keys() & expected.keys()
        if observed[item] != expected[item]
    }
    return {
        "shared": shared,
        "false inclusion": observed.keys() - expected.keys(),
        "false exclusion": expected.keys() - observed.keys(),
        "role disagreement": role_disagreements,
    }


def _set_comparison(observed, expected):
    return {
        "shared": observed & expected,
        "false inclusion": observed - expected,
        "false exclusion": expected - observed,
        "role disagreement": set(),
    }


def _comparison_html(result):
    parts = [f"shared {len(result['shared'])}"]
    for key in ("false inclusion", "false exclusion", "role disagreement"):
        values = sorted(result[key])
        if values:
            parts.append(f"{key}: {' · '.join(values)}")
    return "<br>".join(escape(item) for item in parts)


def _mapping(path: str | Path, schema: str) -> Mapping[str, Any]:
    raw = json.loads(Path(path).read_text())
    if not isinstance(raw, Mapping) or raw.get("schema_version") != schema:
        raise ValueError(f"artifact must use schema_version {schema}")
    return raw


def _mapping_one_of(
    path: str | Path,
    schemas: set[str],
) -> Mapping[str, Any]:
    raw = json.loads(Path(path).read_text())
    if not isinstance(raw, Mapping) or raw.get("schema_version") not in schemas:
        raise ValueError(
            "artifact must use one of schema versions " + ", ".join(sorted(schemas))
        )
    return raw


def _legacy_coverage(state: str) -> StructuralCoverageSnapshot:
    return StructuralCoverageSnapshot(
        state=state,
        provider="",
        hunk_count=0,
        mapped_hunk_count=0,
        symbol_count=0,
        path_count=0,
        seed_count=0,
        complete_seed_count=0,
        truncated_seed_count=0,
        requested_files=0,
        indexed_files=0,
        missing_reason="",
        base_state="unavailable",
        base_mapped_hunk_count=0,
        base_hunk_count=0,
        base_symbol_count=0,
        seed_mapping_state="legacy_unavailable",
    )


def _load_coverage(value: Any) -> StructuralCoverageSnapshot:
    if not isinstance(value, Mapping):
        raise ValueError("coverage must be an object")
    seeds = tuple(
        StructuralSeedCoverage(
            provider_symbol_id=_string(item, "provider_symbol_id"),
            node_id=_optional_string(item.get("node_id")),
            state=_coverage_seed_state(item.get("state")),
        )
        for item in _objects(value, "seeds")
    )
    return StructuralCoverageSnapshot(
        state=_string(value, "state"),
        provider=str(value.get("provider", "")),
        hunk_count=_non_negative_int(value.get("hunk_count")),
        mapped_hunk_count=_non_negative_int(value.get("mapped_hunk_count")),
        symbol_count=_non_negative_int(value.get("symbol_count")),
        path_count=_non_negative_int(value.get("path_count")),
        seed_count=_non_negative_int(value.get("seed_count")),
        complete_seed_count=_non_negative_int(value.get("complete_seed_count")),
        truncated_seed_count=_non_negative_int(value.get("truncated_seed_count")),
        requested_files=_non_negative_int(value.get("requested_files")),
        indexed_files=_non_negative_int(value.get("indexed_files")),
        missing_reason=str(value.get("missing_reason", "")),
        base_state=_string(value, "base_state"),
        base_mapped_hunk_count=_non_negative_int(
            value.get("base_mapped_hunk_count")
        ),
        base_hunk_count=_non_negative_int(value.get("base_hunk_count")),
        base_symbol_count=_non_negative_int(value.get("base_symbol_count")),
        seed_mapping_state=_seed_mapping_state(value.get("seed_mapping_state")),
        seeds=seeds,
    )


def _load_reference_authority(value: Any) -> ReferenceAuthority:
    if not isinstance(value, Mapping):
        raise ValueError("reference authority must be an object")
    status = value.get("status")
    if status not in {"proposed", "adjudicated"}:
        raise ValueError("reference authority has an invalid status")
    return ReferenceAuthority(
        status=status,
        prepared_by=_string(value, "prepared_by"),
        accepted_by=str(value.get("accepted_by", "")),
        proposal_digest=str(value.get("proposal_digest", "")),
    )


def _coverage_seed_state(value: Any) -> Literal["complete", "truncated", "unknown"]:
    if value not in {"complete", "truncated", "unknown"}:
        raise ValueError("coverage seed has an invalid state")
    return value


def _seed_mapping_state(
    value: Any,
) -> Literal["complete", "incomplete", "legacy_unavailable"]:
    if value not in {"complete", "incomplete", "legacy_unavailable"}:
        raise ValueError("coverage has an invalid seed mapping state")
    return value


def _objects(raw: Mapping[str, Any], name: str) -> list[Mapping[str, Any]]:
    value = raw.get(name)
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"{name} must be an object list")
    return value


def _string(raw: Mapping[str, Any], name: str) -> str:
    value = raw.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError("expected a non-empty string list")
    return tuple(value)


def _optional_string(value: Any) -> str | None:
    if value is None: return None
    if not isinstance(value, str) or not value: raise ValueError("expected string or null")
    return value


def _optional_int(value: Any) -> int | None:
    if value is None: return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0: raise ValueError("expected positive integer or null")
    return value


def _optional_non_negative_int(value: Any) -> int | None:
    if value is None: return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("expected non-negative integer or null")
    return value


def _non_negative_int(value: Any) -> int:
    result = _optional_non_negative_int(value)
    if result is None:
        raise ValueError("expected non-negative integer")
    return result


def _unique(values, name: str) -> None:
    values = tuple(values)
    if len(values) != len(set(values)): raise ValueError(f"duplicate {name}")


_CSS = """
:root{color-scheme:dark;--bg:#091015;--panel:#111b21;--line:#2b3b43;--text:#e9eff1;--muted:#91a0a7;--good:#70d49b;--bad:#ef8f91;--warn:#e6bd6a}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,sans-serif}main{width:min(1200px,calc(100% - 32px));margin:32px auto}header,section{padding:24px;margin-bottom:18px;background:var(--panel);border:1px solid var(--line);border-radius:14px}code{overflow-wrap:anywhere;color:var(--muted)}.cards{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:20px}.cards div{padding:12px;border:1px solid var(--line);border-radius:9px}.cards span{display:block;color:var(--muted);font-size:11px}.cards strong{font-size:20px}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid var(--line)}th{color:var(--muted)}tr.match td:last-child{color:var(--good)}tr.false-inclusion td:last-child,tr.false-exclusion td:last-child{color:var(--bad)}tr.role-disagreement td:last-child,tr.unresolved td:last-child{color:var(--warn)}footer{color:var(--muted)}@media(max-width:700px){.cards{grid-template-columns:1fr 1fr}header,section{padding:14px}table{display:block;overflow:auto}}
"""
