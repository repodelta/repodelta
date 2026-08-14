from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from html import escape
from pathlib import Path
from typing import Any, Literal, Mapping

from repodelta.model.contracts import (
    ReviewBrief,
    StructuralOverviewFocus,
    VerificationEvidenceInspection,
)


PACKET_SCHEMA = "structural_correctness_packet.v2"
OBSERVATION_SCHEMA = "structural_correctness_observation.v2"
LABELS_SCHEMA = "structural_correctness_labels.v2"


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
    coverage_state: str
    schema_version: str = PACKET_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != PACKET_SCHEMA or not self.repository:
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

    @property
    def digest(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
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
class StructuralCorrectnessLabels:
    packet_digest: str
    files: tuple[HumanFileLabel, ...]
    focuses: tuple[HumanFocusLabel, ...]
    schema_version: str = LABELS_SCHEMA


def prepare_structural_correctness_label_template(
    packet: StructuralCorrectnessPacket,
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
        coverage_state=brief.overview.structural_coverage.state,
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
    raw = _mapping(path, PACKET_SCHEMA)
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
        coverage_state=_string(raw, "coverage_state"),
        schema_version=_string(raw, "schema_version"),
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
    raw = _mapping(path, LABELS_SCHEMA)
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
        schema_version=_string(raw, "schema_version"),
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
        focus_rows.append(
            "<tr>"
            f"<td>{escape(label.subject_id)}</td>"
            f"<td>{_comparison_html(file_result)}</td>"
            f"<td>{_comparison_html(node_result)}</td>"
            f"<td>{_comparison_html(relation_result)}</td>"
            f"<td>{'yes' if label.unresolved else 'no'}</td>"
            "</tr>"
        )
    cards = ''.join(f"<div><span>{escape(key)}</span><strong>{value}</strong></div>" for key, value in counts.items())
    title = f"{packet.repository} · PR #{packet.pull_request} · structural correctness"
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{escape(title)}</title><style>{_CSS}</style></head><body><main><header><p>Non-authoritative evaluation</p><h1>{escape(title)}</h1><p>Frozen human labels are compared with the canonical structural projection. File, node-role, and exact-relation truth remain distinct. This report does not change assessment or mergeability.</p><code>{escape(packet.digest)}</code></header><section><h2>File overview</h2><div class='cards'>{cards}</div><table><thead><tr><th>Candidate</th><th>RepoDelta</th><th>Human</th><th>Result</th></tr></thead><tbody>{''.join(rows)}</tbody></table></section><section><h2>Focus membership</h2><table><thead><tr><th>Subject</th><th>Files</th><th>Nodes and roles</th><th>Exact relations</th><th>Human unresolved</th></tr></thead><tbody>{''.join(focus_rows)}</tbody></table></section><footer>Coverage: {escape(packet.coverage_state)}</footer></main></body></html>"""


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


def _unique(values, name: str) -> None:
    values = tuple(values)
    if len(values) != len(set(values)): raise ValueError(f"duplicate {name}")


_CSS = """
:root{color-scheme:dark;--bg:#091015;--panel:#111b21;--line:#2b3b43;--text:#e9eff1;--muted:#91a0a7;--good:#70d49b;--bad:#ef8f91;--warn:#e6bd6a}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,sans-serif}main{width:min(1200px,calc(100% - 32px));margin:32px auto}header,section{padding:24px;margin-bottom:18px;background:var(--panel);border:1px solid var(--line);border-radius:14px}code{overflow-wrap:anywhere;color:var(--muted)}.cards{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:20px}.cards div{padding:12px;border:1px solid var(--line);border-radius:9px}.cards span{display:block;color:var(--muted);font-size:11px}.cards strong{font-size:20px}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid var(--line)}th{color:var(--muted)}tr.match td:last-child{color:var(--good)}tr.false-inclusion td:last-child,tr.false-exclusion td:last-child{color:var(--bad)}tr.role-disagreement td:last-child,tr.unresolved td:last-child{color:var(--warn)}footer{color:var(--muted)}@media(max-width:700px){.cards{grid-template-columns:1fr 1fr}header,section{padding:14px}table{display:block;overflow:auto}}
"""
