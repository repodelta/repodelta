from __future__ import annotations

from html import escape
from pathlib import Path
from urllib.parse import urlparse

from .contracts import ChangedFile, Diagnostic, Evidence, ReviewBrief, SourceRef


def _safe_href(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else None


def _source(source: SourceRef) -> str:
    label = escape(source.label)
    location = ""
    if source.path:
        location = f"<code>{escape(source.path)}</code>"
        if source.line_start:
            location += f":{source.line_start}"
            if source.line_end and source.line_end != source.line_start:
                location += f"-{source.line_end}"
    content = " · ".join(part for part in (label, location) if part)
    href = _safe_href(source.url)
    return f'<a href="{escape(href, quote=True)}">{content}</a>' if href else content


def _evidence(item: Evidence) -> str:
    sources = "".join(f"<li>{_source(source)}</li>" for source in item.sources)
    return (
        '<div class="evidence">'
        f'<div><span class="kind">{escape(item.kind)}</span> {escape(item.summary)}</div>'
        f'<ul class="sources">{sources}</ul>'
        "</div>"
    )


def _changed_file(item: ChangedFile) -> str:
    stats = []
    if item.additions is not None:
        stats.append(f"+{item.additions}")
    if item.deletions is not None:
        stats.append(f"-{item.deletions}")
    suffix = f" · {' / '.join(stats)}" if stats else ""
    content = (
        f"<code>{escape(item.path)}</code>"
        f'<span class="file-meta"> {escape(item.status)}{escape(suffix)}</span>'
    )
    href = _safe_href(item.source_url)
    return f'<li><a href="{escape(href, quote=True)}">{content}</a></li>' if href else f"<li>{content}</li>"


def _diagnostic(item: Diagnostic) -> str:
    sources = "".join(f"<li>{_source(source)}</li>" for source in item.sources)
    return (
        f'<article class="diagnostic {escape(item.severity)}">'
        f'<div><span class="kind">{escape(item.severity)}</span> <strong>{escape(item.code)}</strong></div>'
        f"<p>{escape(item.message)}</p>"
        f'<ul class="sources">{sources}</ul>'
        "</article>"
    )


def render_html(brief: ReviewBrief) -> str:
    review = brief.review
    requirement_cards = []
    for requirement in review.requirements:
        implemented = "".join(_evidence(x) for x in requirement.implemented) or '<p class="empty">No implementation evidence recorded.</p>'
        verification = "".join(_evidence(x) for x in requirement.verification) or '<p class="empty">No verification evidence recorded.</p>'
        gaps = "".join(f"<li>{escape(gap)}</li>" for gap in requirement.gaps) or "<li>None recorded.</li>"
        sources = "".join(f"<li>{_source(source)}</li>" for source in requirement.sources)
        source_section = f'<section><h3>Requirement source</h3><ul class="sources">{sources}</ul></section>' if sources else ""
        requirement_cards.append(
            '<article class="requirement">'
            f'<header><span class="req-id">{escape(requirement.id)}</span><span class="status {escape(requirement.status)}">{escape(requirement.status.replace("_", " "))}</span></header>'
            f"<h2>{escape(requirement.text)}</h2>"
            f"{source_section}"
            f"<section><h3>Implemented</h3>{implemented}</section>"
            f"<section><h3>Verification</h3>{verification}</section>"
            f"<section><h3>Gaps</h3><ul>{gaps}</ul></section>"
            "</article>"
        )
    files = "".join(_changed_file(item) for item in review.changed_files) or "<li>Not provided.</li>"
    source_href = _safe_href(review.source_url)
    source = f'<a href="{escape(source_href, quote=True)}">Open source pull request</a>' if source_href else "Source URL not provided."
    diagnostics = "".join(_diagnostic(item) for item in review.diagnostics)
    diagnostics_section = (
        f'<section class="changed"><h2>Collection notes</h2>{diagnostics}</section>' if diagnostics else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(review.title)} · PrismCode</title>
<style>
:root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, sans-serif; background:#f5f7fa; color:#172033; }}
body {{ margin:0; }} main {{ max-width:960px; margin:0 auto; padding:48px 24px 80px; }}
.hero,.requirement,.changed {{ background:white; border:1px solid #dfe5ec; border-radius:14px; box-shadow:0 6px 24px rgba(20,35,55,.05); }}
.hero {{ padding:30px; margin-bottom:22px; }} .eyebrow {{ text-transform:uppercase; letter-spacing:.1em; font-size:12px; color:#667085; }}
h1 {{ margin:8px 0 12px; font-size:32px; }} .intent {{ font-size:17px; line-height:1.6; }} .meta,.file-meta {{ color:#667085; }}
.requirement {{ padding:24px; margin:18px 0; }} .requirement header {{ display:flex; justify-content:space-between; gap:12px; }}
.req-id,.kind,.status {{ font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.06em; }}
.status {{ padding:5px 9px; border-radius:999px; background:#eef2f6; }} .verified {{ background:#e9f8ef; }} .partial {{ background:#fff5d9; }} .not_implemented {{ background:#fdecec; }}
h2 {{ margin:14px 0 22px; font-size:21px; }} h3 {{ margin:22px 0 10px; font-size:14px; text-transform:uppercase; letter-spacing:.06em; color:#475467; }}
.evidence {{ border-left:3px solid #98a2b3; padding:8px 0 8px 14px; margin:10px 0; line-height:1.5; }} .kind {{ color:#475467; margin-right:6px; }}
.sources {{ margin:6px 0 0; padding-left:20px; font-size:13px; color:#667085; }} a {{ color:#2457c5; }} code {{ font-family:ui-monospace,SFMono-Regular,monospace; }}
.empty {{ color:#98a2b3; font-style:italic; }} .changed {{ padding:24px; margin-top:22px; }}
.diagnostic {{ border-left:3px solid #f0b429; padding:10px 0 10px 14px; margin:14px 0; }} .diagnostic.error {{ border-left-color:#d92d20; }} .diagnostic.info {{ border-left-color:#2457c5; }}
.diagnostic p {{ margin:7px 0; line-height:1.5; }}
</style></head><body><main>
<section class="hero"><div class="eyebrow">Requirement-first review brief</div><h1>{escape(review.title)}</h1>
<p class="intent">{escape(review.intent)}</p><p class="meta">{escape(review.repository)} · PR {review.pull_request if review.pull_request is not None else "fixture"} · {source}</p></section>
{"".join(requirement_cards)}
{diagnostics_section}
<section class="changed"><h2>Changed areas</h2><ul>{files}</ul><p class="meta">Schema {escape(brief.schema_version)} · Generated by {escape(brief.generated_by)}</p></section>
</main></body></html>"""


def write_html(brief: ReviewBrief, output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(brief), encoding="utf-8")
    return path
