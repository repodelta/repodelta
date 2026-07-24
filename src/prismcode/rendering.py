from __future__ import annotations

from html import escape
from pathlib import Path
import re
from urllib.parse import quote, urlparse, urlunparse

from .contracts import (
    CandidateBinding,
    ChangedFile,
    EvidenceItem,
    ReviewBrief,
    ReviewStatement,
    SourceRef,
)

_VISIBLE_EVIDENCE_CANDIDATES = 6


def _safe_href(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else None


def _source(source: SourceRef) -> str:
    parsed = urlparse(source.url or "")
    parts = tuple(part for part in parsed.path.split("/") if part)
    concrete_label: str | None = None
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
    location = ""
    if source.path:
        location = f"<code>{escape(source.path)}</code>"
        if source.line_start:
            location += f":{source.line_start}"
            if source.line_end and source.line_end != source.line_start:
                location += f"-{source.line_end}"
    content = " · ".join(part for part in (label, location) if part)
    href = _safe_href(source.url)
    if href and section and not parsed.fragment:
        fragment = re.sub(r"[^a-z0-9]+", "-", section.casefold()).strip("-")
        href = urlunparse(parsed._replace(fragment=fragment))
    return f'<a class="source-link" href="{escape(href, quote=True)}" target="_blank" rel="noopener">{content}</a>' if href else content


def _changed_file(item: ChangedFile) -> str:
    stats = []
    if item.additions is not None:
        stats.append(f"+{item.additions}")
    if item.deletions is not None:
        stats.append(f"-{item.deletions}")
    suffix = f" · {' / '.join(stats)}" if stats else ""
    name = Path(item.path).name
    parent = str(Path(item.path).parent)
    href = _safe_href(item.source_url)
    title = escape(name)
    if href:
        title = f'<a class="file-link file-name" href="{escape(href, quote=True)}" target="_blank" rel="noopener">{title}</a>'
    return (
        '<div class="file-row"><div>'
        f'{title}<span class="file-path">{escape(parent)}/</span>'
        f'</div><span class="file-state">{escape(item.status)}{escape(suffix)}</span></div>'
    )


def _ci_copy(observations: tuple[object, ...]) -> str:
    if not observations:
        return "CI: no run observed"
    if any(getattr(item, "conclusion", "").casefold() in {"failure", "error", "cancelled", "timed_out"} for item in observations):
        return "CI: failure observed"
    if any(getattr(item, "status", "").casefold() in {"queued", "pending", "in_progress"} for item in observations):
        return "CI: running"
    if all(getattr(item, "conclusion", "").casefold() == "success" for item in observations):
        return "CI: passed"
    return f"CI: {len(observations)} observations"


def _statement_row(statement: ReviewStatement) -> str:
    sources = " · ".join(_source(source) for source in statement.sources)
    authority = {
        "issue": "Issue",
        "pr_description": "PR description",
        "pr_title": "PR title",
        "provided": "Provided input",
    }[statement.authority]
    return (
        '<div class="context-row">'
        f'<span class="context-id">{escape(statement.id)}</span>'
        f'<span class="context-copy">{escape(statement.text)}</span>'
        f'<span class="context-authority">{escape(authority)}</span>'
        + (f'<span class="context-source">Source: {sources}</span>' if sources else "")
        + "</div>"
    )


def _binding_basis(binding: CandidateBinding) -> str:
    reasons = []
    for reason in binding.reasons:
        terms = (
            " · " + ", ".join(reason.matched_terms)
            if reason.matched_terms
            else ""
        )
        reasons.append(
            '<span class="basis-chip" title="'
            + escape(reason.detail, quote=True)
            + '">'
            + escape(reason.feature.replace("_", " "))
            + escape(terms)
            + f" · +{reason.weight}</span>"
        )
    return "".join(reasons)


def _candidate_sources(item: EvidenceItem, brief: ReviewBrief) -> str:
    unique: list[SourceRef] = []
    seen: set[tuple[object, ...]] = set()
    for source in item.sources:
        key = (
            source.url,
            source.path,
            source.line_start,
            source.line_end,
        )
        if key not in seen:
            seen.add(key)
            if not source.url and source.path and brief.packet.head_sha:
                source = SourceRef(
                    label=source.label,
                    url=(
                        f"https://github.com/{brief.packet.repository}/blob/"
                        f"{brief.packet.head_sha}/{quote(source.path, safe='/')}"
                    ),
                    path=source.path,
                    line_start=source.line_start,
                    line_end=source.line_end,
                )
            unique.append(source)
    shown = " · ".join(_source(source) for source in unique[:3])
    suffix = (
        f' <span class="candidate-more">+{len(unique) - 3} sources</span>'
        if len(unique) > 3
        else ""
    )
    return shown + suffix


def _candidate_evidence_rows(
    statement_id: str,
    brief: ReviewBrief,
) -> str:
    evidence = brief.evidence_catalog.by_id()
    evidence_bindings = [
        item
        for item in brief.candidate_bindings.items
        if item.kind == "statement_evidence" and item.source_id == statement_id
    ]
    rows = []
    visible_bindings = evidence_bindings[:_VISIBLE_EVIDENCE_CANDIDATES]
    for binding in visible_bindings:
        item = evidence.get(binding.target_id)
        if item is None:
            continue
        is_execution = bool(item.metadata.get("observation_id"))
        kind_label = (
            "EXECUTION"
            if is_execution
            else "FILE FALLBACK"
            if item.kind == "changed_file" and item.changed
            else "FILE"
            if item.kind == "changed_file"
            else "CHANGED HUNK"
            if item.kind == "changed_hunk"
            else "CHANGED " + item.kind.replace("_", " ").upper()
            if item.changed
            else item.kind.replace("_", " ").upper()
        )
        sources = _candidate_sources(item, brief)
        rows.append(
            '<details class="evidence-candidate">'
            '<summary>'
            f'<span class="evidence-kind">{escape(kind_label)}</span>'
            f'<span class="candidate-copy">{escape(item.summary)}</span>'
            f'<span class="candidate-score">relevance {binding.score}</span>'
            "</summary>"
            '<div class="candidate-detail">'
            f'<div class="candidate-basis">{_binding_basis(binding)}</div>'
            + (
                f'<div class="candidate-source">Source: {sources}</div>'
                if sources
                else ""
            )
            + "</div></details>"
        )
    hidden_count = len(evidence_bindings) - len(visible_bindings)
    if hidden_count:
        rows.append(
            '<div class="candidate-overflow">'
            f"{hidden_count} additional candidates retained in report data."
            "</div>"
        )
    return "".join(rows)


def _requirement_candidate_context(
    requirement_id: str,
    brief: ReviewBrief,
) -> str:
    claims = {item.id: item for item in brief.claims}
    claim_bindings = [
        item
        for item in brief.candidate_bindings.items
        if item.kind == "requirement_claim" and item.source_id == requirement_id
    ]
    claim_rows = []
    for binding in claim_bindings:
        claim = claims.get(binding.target_id)
        if claim is None:
            continue
        source = " · ".join(_source(item) for item in claim.sources)
        claim_rows.append(
            '<div class="claim-candidate">'
            f'<span class="candidate-id">{escape(claim.id)}</span>'
            f'<span class="candidate-copy">{escape(claim.text)}</span>'
            f'<span class="candidate-score">relevance {binding.score}</span>'
            f'<div class="candidate-basis">{_binding_basis(binding)}</div>'
            + (
                f'<div class="candidate-source">Source: {source}</div>'
                if source
                else ""
            )
            + "</div>"
    )
    evidence_rows = _candidate_evidence_rows(requirement_id, brief)
    groups = []
    if claim_rows:
        groups.append(
            '<div class="candidate-group"><span class="block-title">Related PR claims</span>'
            + "".join(claim_rows)
            + "</div>"
        )
    if evidence_rows:
        groups.append(
            '<div class="candidate-group"><span class="block-title">Evidence</span>'
            + evidence_rows
            + "</div>"
        )
    if not groups:
        return ""
    return (
        '<div class="candidate-context">'
        '<div class="candidate-heading"><span>Review evidence</span>'
        '<span class="candidate-disclaimer">Retrieval relevance only · not an acceptance conclusion</span></div>'
        + "".join(groups)
        + "</div>"
    )


def _claim_card(statement: ReviewStatement, brief: ReviewBrief, *, open_card: bool) -> str:
    sources = " · ".join(_source(source) for source in statement.sources)
    evidence_rows = _candidate_evidence_rows(statement.id, brief)
    acceptance_ids = [
        item.source_id
        for item in brief.candidate_bindings.items
        if item.kind == "requirement_claim" and item.target_id == statement.id
    ]
    acceptance = (
        "Acceptance link: " + ", ".join(acceptance_ids)
        if acceptance_ids
        else "No acceptance link"
    )
    return (
        f'<details class="requirement claim-check"{" open" if open_card else ""}><summary>'
        f'<span class="req-id">{escape(statement.id)}</span>'
        f'<span class="req-title">{escape(statement.text)}</span>'
        "</summary><div class=\"req-body\">"
        f'<span class="source-note requirement-source">{escape(acceptance)}</span>'
        + (f'<span class="source-note requirement-source">Source: {sources}</span>' if sources else "")
        + (
            '<div class="candidate-context"><div class="candidate-heading">'
            '<span>Evidence</span><span class="candidate-disclaimer">'
            "Retrieval relevance only · not an acceptance conclusion</span></div>"
            + evidence_rows
            + "</div>"
            if evidence_rows
            else '<p class="candidate-empty">No canonical evidence candidate was found.</p>'
        )
        + "</div></details>"
    )


def render_html(brief: ReviewBrief) -> str:
    packet = brief.packet
    requirement_cards = []
    for index, requirement in enumerate(brief.requirements):
        candidate_context = _requirement_candidate_context(
            requirement.id,
            brief,
        )
        sources = " · ".join(_source(source) for source in requirement.sources)
        authority_note = (
            "Provisional PR-authored criterion"
            if requirement.authority == "pr_description"
            else "Issue acceptance criterion"
            if requirement.authority == "issue"
            else "Provided acceptance criterion"
        )
        requirement_cards.append(
            f'<details class="requirement"{" open" if index == 0 else ""}><summary>'
            f'<span class="req-id">{escape(requirement.id)}</span><span class="req-title">{escape(requirement.text)}</span>'
            '</summary>'
            '<div class="req-body">'
            + (
                f'<span class="source-note requirement-source">Source: {sources}'
                f" · {escape(authority_note)}</span>"
                if sources
                else ""
            )
            + candidate_context
            + '</div></details>'
        )
    claim_cards = "".join(
        _claim_card(statement, brief, open_card=index == 0)
        for index, statement in enumerate(brief.claims)
    )
    checks = "".join(requirement_cards) if requirement_cards else claim_cards
    if not checks:
        checks = (
            '<div class="empty-state"><strong>No explicit acceptance criteria or PR claims found.</strong>'
            "<span>The title and prose intent are retained as context, not promoted "
            "to review checks.</span></div>"
        )
    objective_rows = "".join(_statement_row(item) for item in brief.objectives)
    objective_context = (
        '<details class="objective-context"><summary>Objective context · '
        f"{len(brief.objectives)} statement"
        f"{'s' if len(brief.objectives) != 1 else ''}</summary>"
        f'<div class="context-list">{objective_rows}</div></details>'
        if objective_rows
        else ""
    )
    files = "".join(_changed_file(item) for item in packet.changed_files) or '<p class="empty">Not provided.</p>'
    attention_rows: list[str] = []
    if not brief.requirements and not brief.guardrails:
        attention_rows.append(
            '<div class="attention-row"><div class="attention-kind">Acceptance basis</div>'
            '<div class="attention-copy">No explicit acceptance criteria found. '
            "Intent, objectives, and PR claims are not sufficient to determine "
            "requirement satisfaction.</div></div>"
        )
    delivery_requirements = brief.requirements
    requirement_ids_with_claims = {
        item.source_id
        for item in brief.candidate_bindings.items
        if item.kind == "requirement_claim"
    }
    requirement_ids_without_claims = [
        item.id for item in delivery_requirements if item.id not in requirement_ids_with_claims
    ]
    if requirement_ids_without_claims:
        attention_rows.append(
            '<div class="attention-row"><div class="attention-kind">PR claim coverage</div>'
            '<div class="attention-copy">'
            + escape(", ".join(requirement_ids_without_claims))
            + " have no related PR claim candidate. This is a communication gap, "
            "not evidence that the requirement is unimplemented.</div></div>"
        )
    delivery_requirement_ids = {item.id for item in delivery_requirements}
    requirement_ids_without_evidence = tuple(
        item_id
        for item_id in brief.candidate_bindings.coverage.requirement_ids_without_evidence_candidates
        if item_id in delivery_requirement_ids
    )
    if requirement_ids_without_evidence:
        attention_rows.append(
            '<div class="attention-row"><div class="attention-kind">Requirement evidence coverage</div>'
            '<div class="attention-copy">'
            + escape(", ".join(requirement_ids_without_evidence))
            + " have no canonical evidence candidate. Manual review is still required.</div></div>"
        )
    claim_ids_with_evidence = {
        item.source_id
        for item in brief.candidate_bindings.items
        if item.kind == "statement_evidence"
    }
    claim_ids_without_evidence = [
        item.id for item in brief.claims if item.id not in claim_ids_with_evidence
    ]
    if claim_ids_without_evidence:
        attention_rows.append(
            '<div class="attention-row"><div class="attention-kind">Claim evidence coverage</div>'
            '<div class="attention-copy">'
            + escape(", ".join(claim_ids_without_evidence))
            + " have no supporting evidence candidate.</div></div>"
        )
    claims_without_requirements = (
        brief.candidate_bindings.coverage.claim_ids_without_requirement_candidates
    )
    if claims_without_requirements:
        claims_by_id = {item.id: item for item in brief.claims}
        claim_copy = " · ".join(
            f"{claim_id}: {claims_by_id[claim_id].text}"
            for claim_id in claims_without_requirements
            if claim_id in claims_by_id
        )
        attention_rows.append(
            '<div class="attention-row"><div class="attention-kind">Claims without acceptance links</div>'
            '<div class="attention-copy">'
            + escape(claim_copy or ", ".join(claims_without_requirements))
            + " · No related delivery requirement candidate. These remain PR-authored "
            "review context and may need scope review.</div></div>"
        )
    evidence_by_id = brief.evidence_catalog.by_id()
    changed_without_statement = [
        evidence_by_id[item_id]
        for item_id in brief.candidate_bindings.coverage.evidence_ids_without_statement_candidates
        if item_id in evidence_by_id and evidence_by_id[item_id].changed
    ]
    if changed_without_statement:
        summaries = "; ".join(item.summary for item in changed_without_statement[:8])
        suffix = (
            f" (+{len(changed_without_statement) - 8} more)"
            if len(changed_without_statement) > 8
            else ""
        )
        attention_rows.append(
            '<div class="attention-row"><div class="attention-kind">Changed evidence without statement candidates</div>'
            f'<div class="attention-copy">{escape(summaries + suffix)}</div></div>'
        )
    candidate_limits = [
        item.message
        for item in brief.candidate_bindings.diagnostics
        if item.code == "candidate_binding_budget_reached"
    ]
    if candidate_limits:
        attention_rows.append(
            '<div class="attention-row"><div class="attention-kind">Candidate coverage limit</div>'
            f'<div class="attention-copy">{escape(" ".join(candidate_limits))}</div></div>'
        )
    if brief.guardrails:
        guardrail_copy = " · ".join(f"{item.id}: {item.text}" for item in brief.guardrails)
        attention_rows.append(
            '<div class="attention-row"><div class="attention-kind">Scope guardrails</div><div class="attention-copy">'
            + escape(guardrail_copy)
            + "</div></div>"
        )
    source_gap_codes = {"github_linked_issue_not_found", "github_linked_issues_unavailable", "github_patch_unavailable", "github_file_limit_reached"}
    source_gaps = [item.message for item in packet.diagnostics if item.code in source_gap_codes]
    if source_gaps:
        attention_rows.append(
            '<div class="attention-row"><div class="attention-kind">Source coverage</div><div class="attention-copy">'
            + escape(" ".join(source_gaps))
            + "</div></div>"
        )
    attention = "".join(attention_rows) or '<p class="empty">No unresolved attention items.</p>'
    source_links = []
    source_priority = {"linked_issue": 0, "ticket": 0, "pull_request": 1}
    for record in sorted(packet.source_records, key=lambda item: source_priority.get(item.kind, 2)):
        if record.kind in {"linked_issue", "ticket", "pull_request"} and record.url:
            source_links.append(_source(SourceRef(label=record.kind, url=record.url)))
    source_line = " · ".join(source_links) or "Source URL not provided."
    pr_label = f"PR #{packet.pull_request}" if packet.pull_request is not None else "Fixture review"
    pr_state = "Merged" if packet.metadata.get("merged") else ("Draft" if packet.metadata.get("draft") else str(packet.metadata.get("state") or "Unknown").title())
    pr_link = _source(SourceRef(label=pr_label, url=packet.source_url)) if packet.source_url else escape(pr_label)
    ci_summary = _ci_copy(packet.verification_observations)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(packet.title)} · PrismCode</title>
<style>
:root {{ color-scheme:dark;--bg:#080c0f;--panel:#10171b;--border:#26373f;--text:#edf3f0;--muted:#9eaaaf;--faint:#6f7d83;--green:#7be3ac;--green-bg:rgba(46,111,78,.18);--blue-bg:rgba(49,91,121,.18);--amber-bg:rgba(106,85,30,.20);--red-bg:rgba(131,55,49,.20);--shadow:0 22px 64px rgba(0,0,0,.28);}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;color:var(--text);line-height:1.55;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:radial-gradient(circle at 18% -8%,rgba(69,167,118,.12),transparent 31rem),radial-gradient(circle at 92% 8%,rgba(84,139,180,.06),transparent 28rem),var(--bg)}}
code{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;letter-spacing:-.015em}}.shell{{width:min(1160px,calc(100% - 40px));margin:30px auto 84px}}.topbar{{display:flex;align-items:center;justify-content:space-between;gap:18px;margin-bottom:22px}}.brand{{display:inline-flex;align-items:center;gap:11px;font-weight:720}}.brand-mark{{width:14px;height:14px;border:2px solid rgba(255,255,255,.92);transform:rotate(45deg);border-radius:3px;box-shadow:0 0 0 5px rgba(117,224,167,.06)}}
.section{{border:2px solid var(--border);border-radius:18px;background:linear-gradient(180deg,rgba(17,24,28,.97),rgba(11,17,21,.98));box-shadow:var(--shadow);padding:28px;margin-bottom:22px}}h1{{font-size:31px;margin:0 0 14px;letter-spacing:-.025em}}h2{{font-size:22px;margin:0 0 12px;letter-spacing:-.02em}}.meta{{display:flex;flex-wrap:wrap;gap:9px;color:var(--muted);font-size:13px;margin-bottom:16px}}.intent{{max-width:850px;color:#d2dade;font-size:15px}}.source-link,.file-link{{color:#b9dfff;text-decoration:none;background-image:linear-gradient(currentColor,currentColor);background-size:0 1px;background-position:0 100%;background-repeat:no-repeat;transition:background-size .18s ease}}.source-link:hover,.file-link:hover{{background-size:100% 1px}}
.badge{{display:inline-flex;align-items:center;padding:5px 9px;border-radius:999px;font-size:10px;font-weight:760;box-shadow:inset 0 0 0 1px rgba(255,255,255,.08)}}.badge.good{{background:var(--green-bg);color:#c7f4d9}}.badge.info{{background:var(--blue-bg);color:#cce8ff}}.badge.warn{{background:var(--amber-bg);color:#ffe3a0}}.badge.danger{{background:var(--red-bg);color:#ffb0a9}}.badge.muted{{background:rgba(111,128,135,.12);color:#aeb9be}}
.requirements{{border-top:1px solid rgba(111,128,135,.24)}}.requirement{{border-bottom:1px solid rgba(111,128,135,.24)}}.requirement summary{{list-style:none;cursor:pointer;display:grid;grid-template-columns:52px minmax(0,1fr);gap:16px;align-items:center;padding:18px 0}}.requirement summary::-webkit-details-marker{{display:none}}.req-id{{color:var(--green);font-size:12px;font-weight:760;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}}.req-title{{font-size:14px;font-weight:640}}.req-body{{padding:0 0 20px 68px}}.requirement-source{{margin:0 0 12px}}.block-title{{display:block;margin-bottom:5px;color:#89979d;font-size:10px;letter-spacing:.045em;font-weight:700;text-transform:uppercase}}.block-copy{{color:#d7dddf;font-size:13px}}.source-note{{display:block;margin-top:8px;color:var(--faint);font-size:10px;line-height:1.45}}.evidence-sources{{margin-top:14px}}.source-chip{{display:inline-flex;margin:0 7px 7px 0;padding:4px 8px;border-radius:999px;text-decoration:none;font-size:10px;font-weight:740;box-shadow:inset 0 0 0 1px rgba(255,255,255,.08)}}.source-chip.code{{background:var(--green-bg);color:#c7f4d9}}.source-chip.test{{background:var(--blue-bg);color:#cce8ff}}
.sources{{color:var(--faint);font-size:11px;line-height:1.7}}.objective-context{{margin-bottom:12px;padding:0 0 12px;border-bottom:1px solid rgba(111,128,135,.24)}}.objective-context>summary{{cursor:pointer;color:var(--muted);font-size:11px;font-weight:680;list-style:none}}.objective-context>summary::-webkit-details-marker{{display:none}}.objective-context .context-list{{margin-top:10px}}.candidate-context{{margin-top:16px;padding-top:14px;border-top:1px solid rgba(111,128,135,.24)}}.candidate-heading{{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:15px;font-size:12px;font-weight:720}}.candidate-disclaimer{{color:var(--faint);font-size:9px;font-weight:560}}.candidate-group+ .candidate-group{{margin-top:16px}}.claim-candidate{{display:grid;grid-template-columns:38px minmax(0,1fr) auto;gap:8px 10px;padding:10px 0;border-bottom:1px solid rgba(111,128,135,.16)}}.candidate-id{{color:#9fcdf0;font:700 10px ui-monospace,SFMono-Regular,Menlo,monospace}}.candidate-copy{{font-size:11px;color:#d7dddf}}.candidate-score{{color:var(--faint);font-size:9px;white-space:nowrap}}.candidate-basis{{grid-column:2/-1;display:flex;flex-wrap:wrap;gap:5px}}.basis-chip{{display:inline-flex;padding:3px 7px;border-radius:999px;background:rgba(92,116,128,.13);color:#aebdc4;font-size:8px;box-shadow:inset 0 0 0 1px rgba(255,255,255,.06)}}.candidate-source{{grid-column:2/-1;color:var(--faint);font-size:9px}}.candidate-more{{color:var(--faint)}}.candidate-empty{{margin:4px 0 0;color:var(--faint);font-size:10px;font-style:italic}}.candidate-overflow{{padding:9px 0;color:var(--faint);font-size:9px}}.evidence-candidate{{border-bottom:1px solid rgba(111,128,135,.16)}}.evidence-candidate summary{{display:grid;grid-template-columns:112px minmax(0,1fr) auto;gap:10px;align-items:center;padding:9px 0;cursor:pointer;list-style:none}}.evidence-candidate summary::-webkit-details-marker{{display:none}}.evidence-kind{{color:#a7d8bd;font-size:8px;font-weight:760;letter-spacing:.035em}}.candidate-detail{{padding:0 0 10px 122px}}.section-copy{{margin:-4px 0 16px;color:var(--muted);font-size:12px}}.empty-state{{display:grid;gap:5px;padding:18px 0;color:var(--muted);font-size:12px}}.empty-state strong{{color:#e8d18e;font-size:13px}}.context-list{{border-top:1px solid rgba(111,128,135,.24)}}.context-row{{display:grid;grid-template-columns:48px minmax(0,1fr) 120px;gap:12px;align-items:start;padding:14px 0;border-bottom:1px solid rgba(111,128,135,.24)}}.context-id{{color:#9fcdf0;font:700 11px ui-monospace,SFMono-Regular,Menlo,monospace}}.context-copy{{font-size:13px}}.context-authority{{color:var(--muted);font-size:10px;text-align:right}}.context-source{{grid-column:2/-1;color:var(--faint);font-size:10px}}.attention-list{{border-top:1px solid rgba(111,128,135,.24)}}.attention-row{{display:grid;grid-template-columns:210px minmax(0,1fr);gap:18px;padding:14px 0;border-bottom:1px solid rgba(111,128,135,.24)}}.attention-kind{{color:#e7ca7c;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em}}.attention-copy{{color:#cbd4d7;font-size:12px}}.file-list{{display:grid;gap:0;border-top:1px solid rgba(111,128,135,.24)}}.file-row{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px;align-items:center;padding:14px 0;border-bottom:1px solid rgba(111,128,135,.24)}}.file-name{{font-size:13px;font-weight:650}}.file-path{{display:block;color:var(--faint);font-size:10px}}.file-state{{color:var(--muted);font-size:10px;white-space:nowrap}}.empty{{color:var(--faint);font-size:12px;font-style:italic}}.footer{{margin-top:26px;color:var(--faint);font-size:12px;text-align:center}}
@media(max-width:900px){{.requirement summary{{grid-template-columns:46px 1fr}}.req-body{{padding-left:62px}}.attention-row{{grid-template-columns:1fr;gap:8px}}}}@media(max-width:560px){{.shell{{width:min(100% - 18px,1160px);margin-top:16px}}.section{{padding:22px 20px}}.topbar{{align-items:flex-start;flex-direction:column}}.file-row{{grid-template-columns:1fr}}.file-state{{white-space:normal}}.req-body{{padding-left:0}}.candidate-heading{{align-items:flex-start;flex-direction:column}}.claim-candidate{{grid-template-columns:32px minmax(0,1fr)}}.candidate-score{{grid-column:2}}.evidence-candidate summary{{grid-template-columns:1fr}}.candidate-detail{{padding-left:0}}.candidate-basis,.candidate-source{{grid-column:1/-1}}}}
</style></head><body><main class="shell">
<div class="topbar"><div class="brand"><span class="brand-mark"></span> PrismCode</div></div>
<section class="section"><div class="meta">{pr_link}<span>·</span><span>{escape(pr_state)}</span><span>·</span><span>{len(packet.changed_files)} changed files</span><span>·</span><span>{escape(ci_summary)}</span></div>
<h1>{escape(packet.title)}</h1><div class="intent">{escape(brief.intent.text)}</div>
<span class="source-note">Source: {source_line}</span>
</section>
<section class="section"><h2>Review checks</h2>{objective_context}<div class="requirements">{checks}</div></section>
<section class="section"><h2>Needs attention</h2><div class="attention-list">{attention}</div></section>
<section class="section"><h2>Changed areas</h2><div class="file-list">{files}</div></section>
<div class="footer">PrismCode · {escape(pr_label)} · Schema {escape(brief.schema_version)} · Generated by {escape(brief.generated_by)}</div>
</main></body></html>"""


def write_html(brief: ReviewBrief, output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(brief), encoding="utf-8")
    return path
