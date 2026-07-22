from __future__ import annotations

from html import escape
from pathlib import Path
import re
from urllib.parse import urlparse, urlunparse

from .contracts import ChangedFile, Diagnostic, Evidence, ReviewBrief, SourceRef


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


def _evidence(item: Evidence) -> str:
    sources = " · ".join(_source(source) for source in item.sources)
    return (
        '<div class="evidence">'
        f'<div class="block-copy"><span class="kind">{escape(item.kind)}</span> {escape(item.summary)}</div>'
        + (f'<span class="source-note">Source: {sources}</span>' if sources else "")
        + "</div>"
    )


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


def _diagnostic(item: Diagnostic) -> str:
    sources = " · ".join(_source(source) for source in item.sources)
    return (
        '<div class="attention-row">'
        f'<div class="attention-kind">{escape(item.severity)} · {escape(item.code)}</div>'
        f'<div class="attention-copy">{escape(item.message)}'
        + (f'<span class="source-note">Source: {sources}</span>' if sources else "")
        + "</div></div>"
    )


def _badge_class(implementation: str, verification: str) -> str:
    if verification == "passed":
        return "good"
    if verification in {"failed", "stale"}:
        return "danger"
    if implementation == "observed":
        return "info"
    return "warn"


def render_html(brief: ReviewBrief) -> str:
    packet = brief.packet
    requirement_cards = []
    attention_rows: list[str] = []
    for index, assessment in enumerate(brief.assessments):
        requirement = assessment.requirement
        implemented = "".join(_evidence(x) for x in assessment.implementation.evidence) or '<p class="empty">No implementation evidence recorded.</p>'
        verification = "".join(_evidence(x) for x in assessment.verification.evidence) or '<p class="empty">No verification evidence recorded.</p>'
        gaps = "".join(f"<li>{escape(gap)}</li>" for gap in assessment.gaps) or "<li>None recorded.</li>"
        sources = " · ".join(_source(source) for source in requirement.sources)
        status_copy = (
            f"Implementation {assessment.implementation.status.replace('_', ' ')}"
            f" · Verification {assessment.verification.status.replace('_', ' ')}"
        )
        badge_class = _badge_class(assessment.implementation.status, assessment.verification.status)
        if assessment.gaps:
            attention_rows.append(
                '<div class="attention-row"><div class="attention-kind">'
                + escape(requirement.id)
                + ' · Verification gap</div><div class="attention-copy">'
                + escape(" ".join(assessment.gaps))
                + "</div></div>"
            )
        requirement_cards.append(
            f'<details class="requirement"{" open" if index == 0 else ""}><summary>'
            f'<span class="req-id">{escape(requirement.id)}</span><span class="req-title">{escape(requirement.text)}</span>'
            f'<span class="req-status badge {badge_class}">{escape(status_copy)}</span></summary>'
            '<div class="req-body">'
            + (f'<span class="source-note requirement-source">Source: {sources}</span>' if sources else "")
            + '<div><span class="block-title">Implemented</span>' + implemented + '</div>'
            + '<div class="verification"><div><span class="block-title">Verification</span>' + verification + '</div>'
            + f'<div><span class="block-title">Gaps</span><ul class="gap-list">{gaps}</ul></div></div></div></details>'
        )
    files = "".join(_changed_file(item) for item in packet.changed_files) or '<p class="empty">Not provided.</p>'
    for guardrail in brief.guardrails:
        attention_rows.append(
            '<div class="attention-row"><div class="attention-kind">Scope guardrail · '
            + escape(guardrail.id)
            + '</div><div class="attention-copy">'
            + escape(guardrail.text)
            + "</div></div>"
        )
    attention = "".join(attention_rows) or '<p class="empty">No unresolved attention items.</p>'
    implementation_count = sum(
        item.implementation.status == "observed" for item in brief.assessments
    )
    passed_count = sum(item.verification.status == "passed" for item in brief.assessments)
    source_links = []
    source_priority = {"linked_issue": 0, "ticket": 0, "pull_request": 1}
    for record in sorted(packet.source_records, key=lambda item: source_priority.get(item.kind, 2)):
        if record.kind in {"linked_issue", "ticket", "pull_request"} and record.url:
            source_links.append(_source(SourceRef(label=record.kind, url=record.url)))
    source_line = " · ".join(source_links) or "Source URL not provided."
    diagnostics = "".join(_diagnostic(item) for item in packet.diagnostics)
    diagnostics_section = f'<section class="section"><h2>Collection notes</h2><div class="attention-list">{diagnostics}</div></section>' if diagnostics else ""
    pr_label = f"PR #{packet.pull_request}" if packet.pull_request is not None else "Fixture review"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(packet.title)} · PrismCode</title>
<style>
:root {{ color-scheme:dark;--bg:#080c0f;--panel:#10171b;--border:#26373f;--text:#edf3f0;--muted:#9eaaaf;--faint:#6f7d83;--green:#7be3ac;--green-bg:rgba(46,111,78,.18);--blue-bg:rgba(49,91,121,.18);--amber-bg:rgba(106,85,30,.20);--red-bg:rgba(131,55,49,.20);--shadow:0 22px 64px rgba(0,0,0,.28);}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;color:var(--text);line-height:1.55;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:radial-gradient(circle at 18% -8%,rgba(69,167,118,.12),transparent 31rem),radial-gradient(circle at 92% 8%,rgba(84,139,180,.06),transparent 28rem),var(--bg)}}
code{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;letter-spacing:-.015em}}.shell{{width:min(1160px,calc(100% - 40px));margin:30px auto 84px}}.topbar{{display:flex;align-items:center;justify-content:space-between;gap:18px;margin-bottom:22px}}.brand{{display:inline-flex;align-items:center;gap:11px;font-weight:720}}.brand-mark{{width:14px;height:14px;border:2px solid rgba(255,255,255,.92);transform:rotate(45deg);border-radius:3px;box-shadow:0 0 0 5px rgba(117,224,167,.06)}}
.section{{border:2px solid var(--border);border-radius:18px;background:linear-gradient(180deg,rgba(17,24,28,.97),rgba(11,17,21,.98));box-shadow:var(--shadow);padding:28px;margin-bottom:22px}}h1{{font-size:31px;margin:0 0 14px;letter-spacing:-.025em}}h2{{font-size:22px;margin:0 0 12px;letter-spacing:-.02em}}.meta{{display:flex;flex-wrap:wrap;gap:9px;color:var(--muted);font-size:13px;margin-bottom:16px}}.intent{{max-width:850px;color:#d2dade;font-size:15px}}.source-link,.file-link{{color:#b9dfff;text-decoration:none;background-image:linear-gradient(currentColor,currentColor);background-size:0 1px;background-position:0 100%;background-repeat:no-repeat;transition:background-size .18s ease}}.source-link:hover,.file-link:hover{{background-size:100% 1px}}
.summary{{display:flex;flex-wrap:wrap;gap:8px;margin-top:18px}}.badge{{display:inline-flex;align-items:center;padding:5px 9px;border-radius:999px;font-size:11px;font-weight:760;box-shadow:inset 0 0 0 1px rgba(255,255,255,.08)}}.badge.good{{background:var(--green-bg);color:#c7f4d9}}.badge.info{{background:var(--blue-bg);color:#cce8ff}}.badge.warn{{background:var(--amber-bg);color:#ffe3a0}}.badge.danger{{background:var(--red-bg);color:#ffb0a9}}
.requirements{{border-top:1px solid rgba(111,128,135,.24)}}.requirement{{border-bottom:1px solid rgba(111,128,135,.24)}}.requirement summary{{list-style:none;cursor:pointer;display:grid;grid-template-columns:52px minmax(0,1fr) 250px;gap:16px;align-items:center;padding:18px 0}}.requirement summary::-webkit-details-marker{{display:none}}.req-id{{color:var(--green);font-size:12px;font-weight:760;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}}.req-title{{font-size:14px;font-weight:640}}.req-status{{justify-self:end;text-align:center}}.req-body{{padding:0 0 20px 68px}}.requirement-source{{margin:0 0 16px}}.block-title{{display:block;margin-bottom:5px;color:#89979d;font-size:10px;letter-spacing:.045em;font-weight:700;text-transform:uppercase}}.block-copy{{color:#d7dddf;font-size:13px}}.source-note{{display:block;margin-top:8px;color:var(--faint);font-size:10px;line-height:1.45}}.evidence{{margin:0 0 12px}}.kind{{color:#a9d8fb;font-size:10px;font-weight:760;text-transform:uppercase;margin-right:5px}}.verification{{display:grid;grid-template-columns:1.25fr 1fr;gap:28px;margin-top:14px;padding-top:14px;border-top:1px solid rgba(111,128,135,.18)}}.gap-list{{margin:0;padding-left:18px;color:#d9c88c;font-size:12px}}
.sources{{color:var(--faint);font-size:11px;line-height:1.7}}.attention-list{{border-top:1px solid rgba(111,128,135,.24)}}.attention-row{{display:grid;grid-template-columns:210px minmax(0,1fr);gap:18px;padding:14px 0;border-bottom:1px solid rgba(111,128,135,.24)}}.attention-kind{{color:#e7ca7c;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em}}.attention-copy{{color:#cbd4d7;font-size:12px}}.file-list{{display:grid;gap:0;border-top:1px solid rgba(111,128,135,.24)}}.file-row{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px;align-items:center;padding:14px 0;border-bottom:1px solid rgba(111,128,135,.24)}}.file-name{{font-size:13px;font-weight:650}}.file-path{{display:block;color:var(--faint);font-size:10px}}.file-state{{color:var(--muted);font-size:10px;white-space:nowrap}}.empty{{color:var(--faint);font-size:12px;font-style:italic}}.footer{{margin-top:26px;color:var(--faint);font-size:12px;text-align:center}}
@media(max-width:900px){{.requirement summary{{grid-template-columns:46px 1fr}}.req-status{{grid-column:2;justify-self:start}}.req-body{{grid-template-columns:1fr;padding-left:62px}}.verification{{grid-template-columns:1fr}}.attention-row{{grid-template-columns:1fr;gap:8px}}}}@media(max-width:560px){{.shell{{width:min(100% - 18px,1160px);margin-top:16px}}.section{{padding:22px 20px}}.topbar{{align-items:flex-start;flex-direction:column}}.file-row{{grid-template-columns:1fr}}.file-state{{white-space:normal}}.req-body{{padding-left:0}}.coverage{{grid-template-columns:1fr}}}}
</style></head><body><main class="shell">
<div class="topbar"><div class="brand"><span class="brand-mark"></span> PrismCode</div></div>
<section class="section"><div class="meta"><span>{escape(packet.repository)}</span><span>·</span><span>{escape(pr_label)}</span><span>·</span><span>{len(packet.changed_files)} changed files</span></div>
<h1>{escape(packet.title)}</h1><div class="intent">{escape(brief.intent)}</div>
<span class="source-note">Source: {source_line}</span>
<div class="summary"><span class="badge info">{len(brief.assessments)} delivery requirements</span><span class="badge good">{implementation_count} with implementation evidence</span><span class="badge warn">{passed_count} independently verified</span><span class="badge warn">{len(packet.verification_observations)} CI/Actions observations</span></div></section>
<section class="section"><h2>Requirement checks</h2><div class="requirements">{"".join(requirement_cards)}</div></section>
{diagnostics_section}
<section class="section"><h2>Needs attention</h2><div class="attention-list">{attention}</div></section>
<section class="section"><h2>Changed areas</h2><div class="file-list">{files}</div></section>
<div class="footer">PrismCode · {escape(pr_label)} · Schema {escape(brief.schema_version)} · Generated by {escape(brief.generated_by)}</div>
</main></body></html>"""


def write_html(brief: ReviewBrief, output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(brief), encoding="utf-8")
    return path
