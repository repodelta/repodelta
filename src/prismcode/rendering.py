from __future__ import annotations

from html import escape
from pathlib import Path
import re
from urllib.parse import quote, urlparse, urlunparse

from .contracts import (
    ChangedFile,
    ReviewBrief,
    ReviewStatement,
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


def _is_test_path(path: str | None) -> bool:
    lowered = (path or "").casefold()
    return lowered.startswith("tests/") or "/test" in lowered or lowered.endswith("_test.py")


def _evidence_source_chip(source: SourceRef, brief: ReviewBrief) -> str:
    path = source.path
    label = source.label
    if path:
        label = f"{'TEST' if _is_test_path(path) else 'CODE'} · {Path(path).name}"
    href = _safe_href(source.url)
    if not href and path and brief.packet.head_sha:
        href = (
            f"https://github.com/{brief.packet.repository}/blob/{brief.packet.head_sha}/"
            + quote(path, safe="/")
        )
    content = escape(label)
    if href:
        return f'<a class="source-chip {"test" if _is_test_path(path) else "code"}" href="{escape(href, quote=True)}" target="_blank" rel="noopener">{content}</a>'
    return f'<span class="source-chip {"test" if _is_test_path(path) else "code"}">{content}</span>'


def _implementation(assessment: object, brief: ReviewBrief) -> tuple[str, str, int, int]:
    evidence = getattr(getattr(assessment, "implementation"), "evidence")
    copy = " ".join(item.summary for item in evidence) or "No implementation evidence recorded."
    sources: list[SourceRef] = []
    seen: set[tuple[str | None, str | None]] = set()
    for item in evidence:
        for source in item.sources:
            key = (source.path, source.url)
            if key not in seen:
                sources.append(source)
                seen.add(key)
    source_chips = "".join(_evidence_source_chip(source, brief) for source in sources)
    code_count = sum(not _is_test_path(source.path) for source in sources)
    test_count = sum(_is_test_path(source.path) for source in sources)
    return escape(copy), source_chips, code_count, test_count


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


def render_html(brief: ReviewBrief) -> str:
    packet = brief.packet
    requirement_cards = []
    for index, assessment in enumerate(brief.assessments):
        requirement = assessment.requirement
        implemented, evidence_sources, code_count, test_count = _implementation(assessment, brief)
        sources = " · ".join(_source(source) for source in requirement.sources)
        authority_note = (
            "Provisional PR-authored criterion"
            if requirement.authority == "pr_description"
            else "Issue acceptance criterion"
            if requirement.authority == "issue"
            else "Provided acceptance criterion"
        )
        implementation_chip = f"Implemented across {code_count} file{'s' if code_count != 1 else ''}" if code_count else "Implementation not observed"
        test_chip = f"Tests present across {test_count} file{'s' if test_count != 1 else ''}" if test_count else "No related test evidence"
        verification_chip = {
            "passed": "Requirement CI passed",
            "failed": "Requirement CI failed",
            "pending": "Requirement CI pending",
            "stale": "Only stale CI observed",
        }.get(assessment.verification.status, "CI not observed")
        requirement_cards.append(
            f'<details class="requirement"{" open" if index == 0 else ""}><summary>'
            f'<span class="req-id">{escape(requirement.id)}</span><span class="req-title">{escape(requirement.text)}</span>'
            '<span class="req-chips">'
            f'<span class="badge {"good" if code_count else "warn"}">{escape(implementation_chip)}</span>'
            f'<span class="badge {"info" if test_count else "muted"}">{escape(test_chip)}</span>'
            f'<span class="badge {"good" if assessment.verification.status == "passed" else "warn"}">{escape(verification_chip)}</span>'
            '</span></summary>'
            '<div class="req-body">'
            + (
                f'<span class="source-note requirement-source">Source: {sources}'
                f" · {escape(authority_note)}</span>"
                if sources
                else ""
            )
            + f'<div><span class="block-title">Implemented</span><div class="block-copy">{implemented}</div></div>'
            + (f'<div class="evidence-sources"><span class="block-title">Sources</span>{evidence_sources}</div>' if evidence_sources else "")
            + '</div></details>'
        )
    requirements = (
        "".join(requirement_cards)
        or (
            '<div class="empty-state"><strong>No explicit acceptance criteria found.</strong>'
            "<span>The PR title and summary are retained as intent or claims, "
            "not promoted to requirements.</span></div>"
        )
    )
    context_rows = "".join(
        _statement_row(statement)
        for statement in (*brief.objectives, *brief.claims)
    )
    review_context = (
        '<section class="section"><h2>Review context</h2>'
        '<p class="section-copy">Objectives and PR-authored claims provide retrieval context; '
        "they are not acceptance evidence.</p>"
        f'<div class="context-list">{context_rows}</div></section>'
        if context_rows
        else ""
    )
    files = "".join(_changed_file(item) for item in packet.changed_files) or '<p class="empty">Not provided.</p>'
    attention_rows: list[str] = []
    if not brief.assessments and not brief.guardrails:
        attention_rows.append(
            '<div class="attention-row"><div class="attention-kind">Acceptance basis</div>'
            '<div class="attention-copy">No explicit acceptance criteria were found. '
            "Intent, objectives, and PR claims are not sufficient to determine "
            "requirement satisfaction.</div></div>"
        )
    ci_gaps = [item.requirement.id for item in brief.assessments if item.verification.status != "passed"]
    if ci_gaps:
        attention_rows.append(
            '<div class="attention-row"><div class="attention-kind">CI gap</div><div class="attention-copy">'
            + escape(", ".join(ci_gaps))
            + " have no passing requirement-specific CI or independent runtime observation.</div></div>"
        )
    non_ci_gaps: dict[str, list[str]] = {}
    for item in brief.assessments:
        for gap in item.gaps:
            if gap.startswith("No requirement-specific CI"):
                continue
            non_ci_gaps.setdefault(gap, []).append(item.requirement.id)
    for gap, ids in non_ci_gaps.items():
        attention_rows.append(
            '<div class="attention-row"><div class="attention-kind">Verification gap · '
            + escape(", ".join(ids))
            + '</div><div class="attention-copy">'
            + escape(gap)
            + "</div></div>"
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
.requirements{{border-top:1px solid rgba(111,128,135,.24)}}.requirement{{border-bottom:1px solid rgba(111,128,135,.24)}}.requirement summary{{list-style:none;cursor:pointer;display:grid;grid-template-columns:52px minmax(0,1fr) minmax(280px,auto);gap:16px;align-items:center;padding:18px 0}}.requirement summary::-webkit-details-marker{{display:none}}.req-id{{color:var(--green);font-size:12px;font-weight:760;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}}.req-title{{font-size:14px;font-weight:640}}.req-chips{{justify-self:end;display:flex;justify-content:flex-end;flex-wrap:wrap;gap:6px}}.req-body{{padding:0 0 20px 68px}}.requirement-source{{margin:0 0 16px}}.block-title{{display:block;margin-bottom:5px;color:#89979d;font-size:10px;letter-spacing:.045em;font-weight:700;text-transform:uppercase}}.block-copy{{color:#d7dddf;font-size:13px}}.source-note{{display:block;margin-top:8px;color:var(--faint);font-size:10px;line-height:1.45}}.evidence-sources{{margin-top:14px}}.source-chip{{display:inline-flex;margin:0 7px 7px 0;padding:4px 8px;border-radius:999px;text-decoration:none;font-size:10px;font-weight:740;box-shadow:inset 0 0 0 1px rgba(255,255,255,.08)}}.source-chip.code{{background:var(--green-bg);color:#c7f4d9}}.source-chip.test{{background:var(--blue-bg);color:#cce8ff}}
.sources{{color:var(--faint);font-size:11px;line-height:1.7}}.section-copy{{margin:-4px 0 16px;color:var(--muted);font-size:12px}}.empty-state{{display:grid;gap:5px;padding:18px 0;color:var(--muted);font-size:12px}}.empty-state strong{{color:#e8d18e;font-size:13px}}.context-list{{border-top:1px solid rgba(111,128,135,.24)}}.context-row{{display:grid;grid-template-columns:48px minmax(0,1fr) 120px;gap:12px;align-items:start;padding:14px 0;border-bottom:1px solid rgba(111,128,135,.24)}}.context-id{{color:#9fcdf0;font:700 11px ui-monospace,SFMono-Regular,Menlo,monospace}}.context-copy{{font-size:13px}}.context-authority{{color:var(--muted);font-size:10px;text-align:right}}.context-source{{grid-column:2/-1;color:var(--faint);font-size:10px}}.attention-list{{border-top:1px solid rgba(111,128,135,.24)}}.attention-row{{display:grid;grid-template-columns:210px minmax(0,1fr);gap:18px;padding:14px 0;border-bottom:1px solid rgba(111,128,135,.24)}}.attention-kind{{color:#e7ca7c;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em}}.attention-copy{{color:#cbd4d7;font-size:12px}}.file-list{{display:grid;gap:0;border-top:1px solid rgba(111,128,135,.24)}}.file-row{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px;align-items:center;padding:14px 0;border-bottom:1px solid rgba(111,128,135,.24)}}.file-name{{font-size:13px;font-weight:650}}.file-path{{display:block;color:var(--faint);font-size:10px}}.file-state{{color:var(--muted);font-size:10px;white-space:nowrap}}.empty{{color:var(--faint);font-size:12px;font-style:italic}}.footer{{margin-top:26px;color:var(--faint);font-size:12px;text-align:center}}
@media(max-width:900px){{.requirement summary{{grid-template-columns:46px 1fr}}.req-chips{{grid-column:2;justify-self:start;justify-content:flex-start}}.req-body{{padding-left:62px}}.attention-row{{grid-template-columns:1fr;gap:8px}}}}@media(max-width:560px){{.shell{{width:min(100% - 18px,1160px);margin-top:16px}}.section{{padding:22px 20px}}.topbar{{align-items:flex-start;flex-direction:column}}.file-row{{grid-template-columns:1fr}}.file-state{{white-space:normal}}.req-body{{padding-left:0}}}}
</style></head><body><main class="shell">
<div class="topbar"><div class="brand"><span class="brand-mark"></span> PrismCode</div></div>
<section class="section"><div class="meta">{pr_link}<span>·</span><span>{escape(pr_state)}</span><span>·</span><span>{len(packet.changed_files)} changed files</span><span>·</span><span>{escape(ci_summary)}</span></div>
<h1>{escape(packet.title)}</h1><div class="intent">{escape(brief.intent.text)}</div>
<span class="source-note">Source: {source_line}</span>
</section>
<section class="section"><h2>Requirement checks</h2><div class="requirements">{requirements}</div></section>
{review_context}
<section class="section"><h2>Needs attention</h2><div class="attention-list">{attention}</div></section>
<section class="section"><h2>Changed areas</h2><div class="file-list">{files}</div></section>
<div class="footer">PrismCode · {escape(pr_label)} · Schema {escape(brief.schema_version)} · Generated by {escape(brief.generated_by)}</div>
</main></body></html>"""


def write_html(brief: ReviewBrief, output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(brief), encoding="utf-8")
    return path
