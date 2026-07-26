from __future__ import annotations

from html import escape
from pathlib import Path
import re
from urllib.parse import quote, urlparse, urlunparse

from prismcode.model.contracts import (
    ChangedFile,
    EvidenceItem,
    ProjectionDiagnostic,
    ProjectionRelation,
    ReviewBrief,
    ReviewProjection,
    ReviewSlice,
    ReviewStatement,
    ReviewStructuralGraph,
    SourceRef,
)


def _safe_href(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else None


def _source(source: SourceRef) -> str:
    parsed = urlparse(source.url or "")
    parts = tuple(part for part in parsed.path.split("/") if part)
    concrete_label = None
    if len(parts) >= 4 and parts[-2] == "issues" and parts[-1].isdigit():
        concrete_label = f"Issue #{parts[-1]}"
    elif len(parts) >= 4 and parts[-2] == "pull" and parts[-1].isdigit():
        concrete_label = f"PR #{parts[-1]}"
    label_parts = source.label.split(" · ", 1)
    section = label_parts[1] if len(label_parts) == 2 else None
    display_label = concrete_label or label_parts[0]
    if section:
        display_label += f" · {section}"
    label = escape(display_label)
    href = _safe_href(source.url)
    if href and section and not parsed.fragment:
        fragment = re.sub(r"[^a-z0-9]+", "-", section.casefold()).strip("-")
        href = urlunparse(parsed._replace(fragment=fragment))
    if href:
        return (
            f'<a class="source-link" href="{escape(href, quote=True)}" '
            f'target="_blank" rel="noopener">{label}</a>'
        )
    if source.path:
        return f"<code>{escape(source.path)}</code>"
    return label


def _sources(item: EvidenceItem, brief: ReviewBrief) -> str:
    unique: list[SourceRef] = []
    seen: set[tuple[object, ...]] = set()
    for source in item.sources:
        key = (source.url, source.path, source.line_start, source.line_end)
        if key in seen:
            continue
        seen.add(key)
        if not source.url and source.path and brief.packet.head_sha:
            line = f"#L{source.line_start}" if source.line_start else ""
            if source.line_end and source.line_end != source.line_start:
                line += f"-L{source.line_end}"
            source = SourceRef(
                label=source.label,
                url=(
                    f"https://github.com/{brief.packet.repository}/blob/"
                    f"{brief.packet.head_sha}/{quote(source.path, safe='/')}{line}"
                ),
                path=source.path,
                line_start=source.line_start,
                line_end=source.line_end,
            )
        unique.append(source)
    shown = " · ".join(_source(source) for source in unique[:3])
    return shown + (
        f' <span class="more">+{len(unique) - 3} sources</span>'
        if len(unique) > 3
        else ""
    )


def _changed_file(item: ChangedFile) -> str:
    href = _safe_href(item.source_url)
    source = (
        f'<a class="file-link" href="{escape(href, quote=True)}" '
        f'target="_blank" rel="noopener">{escape(Path(item.path).name)}</a>'
    if href
        else escape(Path(item.path).name)
    )
    counts = []
    if item.additions is not None:
        counts.append(f"+{item.additions}")
    if item.deletions is not None:
        counts.append(f"-{item.deletions}")
    return (
        '<div class="file-row"><div class="file-name">'
        f'{source}<span class="file-path">{escape(item.path)}</span></div>'
        f'<div class="file-state">{escape(item.status)}'
        + (f" · {' '.join(counts)}" if counts else "")
        + "</div></div>"
    )


def _statement_context(label: str, statements: tuple[ReviewStatement, ...]) -> str:
    if not statements:
        return ""
    rows = []
    for item in statements:
        sources = " · ".join(_source(source) for source in item.sources)
        rows.append(
            '<div class="context-row">'
            f'<span class="context-id">{escape(item.id)}</span>'
            f'<span class="context-copy">{escape(item.text)}</span>'
            f'<span class="context-authority">{escape(item.authority.replace("_", " "))}</span>'
            + (
                f'<span class="context-source">Source: {sources}</span>'
                if sources
                else ""
            )
            + "</div>"
        )
    return (
        f'<details class="context"><summary>{escape(label)} · {len(statements)} '
        f"statement{'s' if len(statements) != 1 else ''}</summary>"
        f'<div class="context-list">{"".join(rows)}</div></details>'
    )


def _relation_fact(
    relation: ProjectionRelation,
    brief: ReviewBrief,
    *,
    label: str,
) -> str:
    evidence = brief.evidence_catalog.by_id().get(relation.target_id)
    if evidence is None:
        raise ValueError(f"projection references missing evidence: {relation.target_id}")
    sources = _sources(evidence, brief)
    reason = relation.reasons[0] if relation.reasons else None
    reason_copy = reason.detail if reason else relation.association.replace("_", " ")
    return (
        '<div class="projection-item">'
        f'<span class="relation-label">{escape(label)}</span>'
        f'<span class="projection-copy">{escape(evidence.summary)}</span>'
        f'<span class="relation-reason">{escape(reason_copy)}</span>'
        + (
            f'<span class="projection-source">Source: {sources}</span>'
            if sources
            else ""
        )
        + "</div>"
    )


def _diagnostic_rows(
    diagnostics: tuple[ProjectionDiagnostic, ...],
    *,
    slots: set[str],
) -> str:
    rows = []
    for item in diagnostics:
        if item.slot not in slots or item.state == "not_applicable":
            continue
        rows.append(
            '<div class="slot-diagnostic">'
            f'<span>{escape(item.slot.replace("_", " "))} · '
            f'{escape(item.state.replace("_", " "))}</span>'
            f"<p>{escape(item.message)}</p></div>"
        )
    return "".join(rows)


def _review_graph(
    graph: ReviewStructuralGraph,
    projection: ReviewProjection,
    brief: ReviewBrief,
) -> str:
    if not graph.nodes:
        return ""
    evidence = brief.evidence_catalog.by_id()
    nodes = {item.evidence_id: item for item in graph.nodes}
    edges = {item.id: item for item in graph.edges}
    node_focus: dict[str, list[tuple[str, str]]] = {}
    edge_focus: dict[str, list[str]] = {}
    for review_slice in projection.slices:
        focus_id = review_slice.focus_statement_id
        for node in review_slice.structural_overlay.nodes:
            if node.evidence_id not in nodes:
                raise ValueError(
                    f"{focus_id}: structural overlay references missing node "
                    f"{node.evidence_id}"
                )
            node_focus.setdefault(node.evidence_id, []).append(
                (focus_id, node.role)
            )
        for edge_id in review_slice.structural_overlay.edge_ids:
            if edge_id not in edges:
                raise ValueError(
                    f"{focus_id}: structural overlay references missing edge "
                    f"{edge_id}"
                )
            edge_focus.setdefault(edge_id, []).append(focus_id)
    node_rows = []
    for node in graph.nodes:
        fact = evidence.get(node.evidence_id)
        if fact is None:
            raise ValueError(
                f"structural graph references missing node: {node.evidence_id}"
            )
        sources = _sources(fact, brief)
        focus_labels = ", ".join(
            focus_id
            for focus_id, _role in node_focus.get(node.evidence_id, ())
        )
        node_rows.append(
            '<div class="subgraph-node">'
            f'<span class="node-focuses">{escape(focus_labels)}</span>'
            f'<span class="subgraph-node-name">{escape(_structural_name(fact))}</span>'
            + (
                f'<span class="projection-source">Source: {sources}</span>'
                if sources
                else ""
            )
            + "</div>"
        )

    edge_rows = []
    for edge in graph.edges:
        source_node = nodes.get(edge.source_evidence_id)
        target_node = nodes.get(edge.target_evidence_id)
        source = evidence.get(edge.source_evidence_id)
        target = evidence.get(edge.target_evidence_id)
        if source_node is None or target_node is None or source is None or target is None:
            raise ValueError("structural graph edge references a missing node")
        source_name = _structural_name(source)
        target_name = _structural_name(target)
        arrow = "→" if edge.direction == "outgoing" else "←"
        edge_rows.append(
            '<div class="subgraph-edge">'
            f'<span>{escape(source_name)}</span>'
            f'<span class="subgraph-relation">{arrow} {escape(edge.relation)}</span>'
            f'<span>{escape(target_name)}</span>'
            '<span class="edge-path-count">'
            f'{escape(", ".join(edge_focus.get(edge.id, ())))} · '
            f'{len(edge.path_relation_ids)} '
            f'support ref{"s" if len(edge.path_relation_ids) != 1 else ""}</span>'
            "</div>"
        )

    return (
        '<div class="review-structural-graph">'
        '<h3>Structural evidence graph</h3>'
        f'<div class="subgraph-summary">{len(graph.nodes)} canonical nodes · '
        f'{len(graph.edges)} canonical edges · '
        f'{len(graph.path_relation_ids)} focus-relative support refs · '
        f'{sum(bool(item.structural_overlay.nodes) for item in projection.slices)} '
        "focus overlays</div>"
        f'<div class="subgraph-nodes">{"".join(node_rows)}</div>'
        f'<div class="subgraph-edges">{"".join(edge_rows)}</div>'
        "</div>"
    )


def _structural_name(item: EvidenceItem) -> str:
    qualified_name = str(item.metadata.get("qualified_name", item.summary))
    path = str(item.metadata.get("path", ""))
    if not path:
        return qualified_name
    parts = Path(path).parts
    short_path = "/".join(parts[-2:])
    return f"{short_path} · {qualified_name}"


def _projection_slice(
    review_slice: ReviewSlice,
    statement: ReviewStatement,
    brief: ReviewBrief,
    *,
    profile: str,
    diagnostics: tuple[ProjectionDiagnostic, ...],
) -> str:
    relations = brief.projection_candidates.by_id()
    claims = {item.id: item for item in brief.claims}

    claim_rows = []
    for relation_id in review_slice.claim_relation_ids:
        relation = relations.get(relation_id)
        claim = claims.get(relation.target_id) if relation else None
        if relation is None or claim is None:
            raise ValueError(f"projection references missing claim relation: {relation_id}")
        source = " · ".join(_source(item) for item in claim.sources)
        reason = relation.reasons[0] if relation.reasons else None
        claim_rows.append(
            '<div class="projection-item">'
            f'<span class="relation-label">{escape(relation.association.replace("_", " "))}</span>'
            f'<span class="projection-copy"><b>{escape(claim.id)}</b> {escape(claim.text)}</span>'
            + (
                f'<span class="relation-reason">{escape(reason.detail)}</span>'
                if reason
                else ""
            )
            + (
                f'<span class="projection-source">Source: {source}</span>'
                if source
                else ""
            )
            + "</div>"
        )

    groups = (
        (
            "Changed anchors",
            review_slice.standalone_changed_fact_relation_ids,
            "changed fact",
        ),
        (
            "Runtime context",
            review_slice.standalone_runtime_relation_ids,
            "context fact",
        ),
        (
            "Test context",
            review_slice.standalone_test_relation_ids,
            "context fact",
        ),
        (
            "Verification",
            review_slice.verification_relation_ids,
            "current-head observation",
        ),
    )
    fact_groups = []
    if review_slice.guardrail_scan_plan_id is not None:
        plan = brief.guardrail_scan_plans.by_id().get(
            review_slice.guardrail_scan_plan_id
        )
        if plan is None:
            raise ValueError(
                "projection references missing guardrail scan plan: "
                f"{review_slice.guardrail_scan_plan_id}"
            )
        sources = " · ".join(_source(source) for source in plan.sources)
        fact_groups.append(
            '<div class="projection-group">'
            '<span class="block-title">Guardrail scan plan</span>'
            f'<span class="projection-copy">{escape(plan.scope)} '
            f'{" / ".join(escape(item) for item in plan.surfaces)} · '
            f'{escape(plan.revision_side)} revision</span>'
            f'<span class="relation-reason">{escape(plan.query_text)}</span>'
            + (
                f'<span class="projection-source">Source: {sources}</span>'
                if sources
                else ""
            )
            + "</div>"
        )
    for heading, relation_ids, label in groups:
        rows = "".join(
            _relation_fact(relations[relation_id], brief, label=label)
            for relation_id in relation_ids
            if relation_id in relations
        )
        if rows:
            fact_groups.append(
                f'<div class="projection-group"><span class="block-title">'
                f"{escape(heading)}</span>{rows}</div>"
            )
    overlay = review_slice.structural_overlay
    if overlay.nodes:
        fact_groups.append(
            '<div class="projection-group structural-overlay-summary">'
            '<span class="block-title">Structural overlay</span>'
            f'<span class="projection-copy">{len(overlay.nodes)} nodes · '
            f'{len(overlay.edge_ids)} edges · '
            f'{len(overlay.path_relation_ids)} support paths</span></div>'
        )

    claim_diagnostics = _diagnostic_rows(
        diagnostics,
        slots={"claim"},
    )
    fact_diagnostics = _diagnostic_rows(
        diagnostics,
        slots={
            "changed_anchor",
            "runtime_context",
            "test_context",
            "verification",
            "structural_path",
            "boundary_fact",
        },
    )
    contract_label = statement.authority.replace("_", " ")
    statement_sources = " · ".join(_source(source) for source in statement.sources)
    authority_note = f"{statement.role.replace('_', ' ')} · {statement.purpose.replace('_', ' ')}"
    return (
        '<div class="projection">'
        '<div class="projection-column">'
        f'<span class="projection-heading">{escape(contract_label)}</span>'
        f'<span class="profile-chip">{escape(profile.replace("_", " "))}</span>'
        f'<p class="projection-copy">{escape(statement.text)}</p>'
        f'<span class="relation-reason">{escape(authority_note)}</span>'
        + (
            f'<span class="projection-source">Source: {statement_sources}</span>'
            if statement_sources
            else ""
        )
        + "</div>"
        '<div class="projection-arrow">→</div>'
        '<div class="projection-column">'
        '<span class="projection-heading">PR says</span>'
        + "".join(claim_rows)
        + claim_diagnostics
        + "</div>"
        '<div class="projection-arrow">→</div>'
        '<div class="projection-column projection-facts">'
        '<span class="projection-heading">Repository facts</span>'
        + "".join(fact_groups)
        + fact_diagnostics
        + "</div></div>"
    )


def _attention(brief: ReviewBrief) -> str:
    rows = (
        '<div class="attention-row">'
        f'<div class="attention-kind">{escape(item.label)}</div>'
        f'<div class="attention-copy">{escape(", ".join(item.focus_statement_ids))}'
        + (" · " if item.focus_statement_ids else "")
        + f"{escape(item.message)}</div></div>"
        for item in brief.overview.attention
    )
    rendered = "".join(rows)
    return rendered or '<p class="empty">No unresolved attention items.</p>'


def render_html(brief: ReviewBrief) -> str:
    packet = brief.packet
    statements = {
        item.id: item for item in (*brief.requirements, *brief.guardrails)
    }
    groups = {
        item.focus_statement_id: item
        for item in brief.projection_candidates.groups
    }
    diagnostics = {
        **brief.projection_candidates.diagnostics_by_id(),
        **brief.candidate_convergence.diagnostics_by_id(),
    }
    cards = []
    for index, review_slice in enumerate(brief.projection.slices):
        statement = statements.get(review_slice.focus_statement_id)
        group = groups.get(review_slice.focus_statement_id)
        if statement is None or group is None:
            raise ValueError(
                f"projection references missing focus: {review_slice.focus_statement_id}"
            )
        slice_diagnostics = tuple(
            diagnostics[diagnostic_id]
            for diagnostic_id in review_slice.diagnostic_ids
            if diagnostic_id in diagnostics
        )
        if len(slice_diagnostics) != len(review_slice.diagnostic_ids):
            raise ValueError(
                f"projection references missing diagnostic: {review_slice.focus_statement_id}"
            )
        cards.append(
            f'<details class="requirement"{" open" if index == 0 else ""}>'
            '<summary>'
            f'<span class="req-id">{escape(statement.id)}</span>'
            f'<span class="req-title">{escape(statement.text)}</span>'
            '</summary><div class="req-body">'
            f"{_projection_slice(review_slice, statement, brief, profile=group.profile, diagnostics=slice_diagnostics)}</div></details>"
        )
    if not cards:
        if brief.overview.empty_review_message is None:
            raise ValueError("projection rendered no cards without an empty-review fact")
        cards.append(
            f'<div class="empty-state">{escape(brief.overview.empty_review_message)}</div>'
        )

    source_priority = {"linked_issue": 0, "ticket": 0, "pull_request": 1}
    source_links = [
        _source(SourceRef(label=record.kind, url=record.url))
        for record in sorted(
            packet.source_records,
            key=lambda item: source_priority.get(item.kind, 2),
        )
        if record.kind in {"linked_issue", "ticket", "pull_request"} and record.url
    ]
    source_line = " · ".join(source_links) or "Source URL not provided."
    pr_label = (
        f"PR #{packet.pull_request}"
        if packet.pull_request is not None
        else "Fixture review"
    )
    pr_state = brief.overview.pull_request_state.title()
    ci_copy = {
        "not_observed": "CI: no run observed",
        "failure": "CI: failure observed",
        "passing": "CI: passing",
        "pending": "CI: queued or running",
    }[brief.overview.ci_state]
    pr_link = (
        _source(SourceRef(label=pr_label, url=packet.source_url))
        if packet.source_url
        else escape(pr_label)
    )
    files = "".join(_changed_file(item) for item in packet.changed_files)
    review_contract = (
        '<div class="review-contract">'
        + _statement_context("Goals", brief.objectives)
        + _statement_context("Scope", brief.scope)
        + _statement_context(
            "Verification expectations",
            brief.verification_expectations,
        )
        + "</div>"
        if (
            brief.objectives
            or brief.scope
            or brief.verification_expectations
        )
        else ""
    )
    semantic_context = _statement_context("PR claim context", brief.claims)
    review_graph = _review_graph(
        brief.projection.review_graph,
        brief.projection,
        brief,
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(packet.title)} · PrismCode</title>
<style>
:root{{color-scheme:dark;--bg:#080c0f;--panel:#10171b;--border:#26373f;--text:#edf3f0;--muted:#9eaaaf;--faint:#6f7d83;--green:#7be3ac;--amber:#e7ca7c;--shadow:0 22px 64px rgba(0,0,0,.28)}}*{{box-sizing:border-box}}body{{margin:0;color:var(--text);line-height:1.55;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:radial-gradient(circle at 18% -8%,rgba(69,167,118,.12),transparent 31rem),var(--bg)}}code{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}}.shell{{width:min(1180px,calc(100% - 40px));margin:30px auto 84px}}.topbar{{margin-bottom:22px;font-weight:720}}.brand-mark{{display:inline-block;width:14px;height:14px;margin-right:10px;border:2px solid white;transform:rotate(45deg);border-radius:3px}}.section{{border:2px solid var(--border);border-radius:18px;background:linear-gradient(180deg,rgba(17,24,28,.97),rgba(11,17,21,.98));box-shadow:var(--shadow);padding:28px;margin-bottom:22px}}h1{{font-size:31px;margin:0 0 14px}}h2{{font-size:22px;margin:0 0 14px}}h3{{font-size:16px;margin:0 0 8px}}.meta{{display:flex;flex-wrap:wrap;gap:9px;color:var(--muted);font-size:13px;margin-bottom:16px}}.intent{{max-width:850px;color:#d2dade;font-size:15px}}.source-link,.file-link{{color:#b9dfff;text-decoration:none}}.source-note,.projection-source,.context-source{{display:block;color:var(--faint);font-size:10px;line-height:1.45}}.requirements{{border-top:1px solid rgba(111,128,135,.24)}}.requirement{{border-bottom:1px solid rgba(111,128,135,.24)}}.requirement summary{{list-style:none;cursor:pointer;display:grid;grid-template-columns:52px minmax(0,1fr);gap:16px;padding:18px 0}}.requirement summary::-webkit-details-marker{{display:none}}.req-id{{color:var(--green);font:760 12px ui-monospace,SFMono-Regular,Menlo,monospace}}.req-title{{font-size:14px;font-weight:640}}.req-body{{padding:0 0 22px 68px}}.projection{{display:grid;grid-template-columns:minmax(0,.85fr) 24px minmax(0,1fr) 24px minmax(0,1.35fr);gap:10px;align-items:start}}.projection-column{{min-width:0;padding:14px;border:1px solid rgba(111,128,135,.22);border-radius:12px;background:rgba(5,10,13,.24)}}.projection-heading,.block-title{{display:block;margin-bottom:9px;color:#89979d;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.045em}}.projection-arrow{{align-self:center;color:var(--faint);text-align:center}}.profile-chip,.relation-label{{display:inline-flex;margin:0 0 8px;padding:3px 7px;border-radius:999px;background:rgba(54,118,87,.20);color:#bfeacf;font-size:8px;font-weight:720}}.projection-copy{{margin:0 0 7px;color:#d7dddf;font-size:11px}}.projection-item{{padding:9px 0;border-bottom:1px solid rgba(111,128,135,.16)}}.projection-item:last-child{{border-bottom:0}}.relation-reason{{display:block;color:var(--faint);font-size:9px;margin-bottom:6px}}.projection-group+.projection-group{{margin-top:15px}}.structural-overlay-summary{{padding-top:2px}}.review-structural-graph{{margin-top:24px;padding:16px;border:1px solid rgba(111,128,135,.22);border-radius:12px;background:rgba(5,10,13,.24)}}.subgraph-summary{{margin-bottom:10px;color:var(--muted);font-size:9px}}.subgraph-nodes{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px}}.subgraph-node{{min-width:0;padding:8px;border:1px solid rgba(111,128,135,.18);border-radius:8px}}.node-focuses{{display:block;margin-bottom:4px;color:var(--green);font-size:8px;line-height:1.35}}.subgraph-node-name{{display:block;overflow-wrap:anywhere;font-size:10px}}.subgraph-edges{{margin-top:10px;border-top:1px solid rgba(111,128,135,.18)}}.subgraph-edge{{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr) auto;gap:7px;padding:7px 0;border-bottom:1px solid rgba(111,128,135,.13);font-size:9px;align-items:center}}.subgraph-relation{{color:#9fcdf0}}.edge-path-count{{color:var(--faint);white-space:nowrap}}.slot-diagnostic{{margin:9px 0;padding:9px;border-radius:8px;background:rgba(106,85,30,.16);color:#e8d18e;font-size:9px}}.slot-diagnostic p{{margin:3px 0 0;color:var(--muted)}}.context{{margin-bottom:12px;padding-bottom:12px;border-bottom:1px solid rgba(111,128,135,.24)}}.context>summary{{cursor:pointer;color:var(--muted);font-size:11px}}.context-row{{display:grid;grid-template-columns:48px minmax(0,1fr) 120px;gap:12px;padding:12px 0;border-bottom:1px solid rgba(111,128,135,.18)}}.context-id{{color:#9fcdf0;font:700 11px ui-monospace,SFMono-Regular,Menlo,monospace}}.context-copy{{font-size:12px}}.context-authority{{color:var(--muted);font-size:10px;text-align:right}}.context-source{{grid-column:2/-1}}.attention-list,.file-list{{border-top:1px solid rgba(111,128,135,.24)}}.attention-row{{display:grid;grid-template-columns:220px minmax(0,1fr);gap:18px;padding:14px 0;border-bottom:1px solid rgba(111,128,135,.24)}}.attention-kind{{color:var(--amber);font-size:10px;font-weight:700;text-transform:uppercase}}.attention-copy{{color:#cbd4d7;font-size:12px}}.file-row{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px;padding:14px 0;border-bottom:1px solid rgba(111,128,135,.24)}}.file-name{{font-size:13px;font-weight:650}}.file-path{{display:block;color:var(--faint);font-size:10px}}.file-state{{color:var(--muted);font-size:10px}}.empty,.empty-state{{color:var(--faint);font-size:12px}}.footer{{margin-top:26px;color:var(--faint);font-size:12px;text-align:center}}@media(max-width:950px){{.projection{{grid-template-columns:1fr}}.projection-arrow{{transform:rotate(90deg)}}.req-body{{padding-left:0}}.subgraph-nodes{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}@media(max-width:600px){{.shell{{width:calc(100% - 18px);margin-top:16px}}.section{{padding:22px 20px}}.attention-row,.context-row,.subgraph-edge{{grid-template-columns:1fr}}.subgraph-nodes{{grid-template-columns:1fr}}}}
</style></head><body><main class="shell">
<div class="topbar"><span class="brand-mark"></span>PrismCode</div>
<section class="section"><div class="meta">{pr_link}<span>·</span><span>{escape(pr_state)}</span><span>·</span><span>{brief.overview.changed_file_count} changed files</span><span>·</span><span>{escape(ci_copy)}</span></div><h1>{escape(packet.title)}</h1><div class="intent">{escape(brief.intent.text)}</div><span class="source-note">Source: {source_line}</span>{review_contract}</section>
<section class="section"><h2>Review checks</h2>{semantic_context}<div class="requirements">{"".join(cards)}</div>{review_graph}</section>
<section class="section"><h2>Needs attention</h2><div class="attention-list">{_attention(brief)}</div></section>
<section class="section"><h2>Changed areas</h2><div class="file-list">{files or '<p class="empty">Not provided.</p>'}</div></section>
<div class="footer">PrismCode · {escape(pr_label)} · Schema {escape(brief.schema_version)} · Generated by {escape(brief.generated_by)}</div>
</main></body></html>"""


def write_html(brief: ReviewBrief, output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(brief), encoding="utf-8")
    return path
