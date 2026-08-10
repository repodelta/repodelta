from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path

from repodelta.evaluation.shadow import (
    ExpectedShadowOutcome,
    HumanShadowLabel,
    HumanShadowLabelSet,
    ShadowEvaluationMetrics,
    evaluate_shadow_outcomes,
    load_human_shadow_labels_from_packet,
    shadow_metrics,
)
from repodelta.llm.admission import ShadowCandidateAdmission
from repodelta.llm.contracts import (
    ShadowEvidenceCandidate,
    ShadowEvidenceSelection,
    ShadowEvidenceSelectionItem,
)
from repodelta.llm.execution import (
    ShadowExecutionBundle,
    ShadowExecutionObservation,
    load_shadow_execution,
)
from repodelta.llm.labeling import (
    ShadowLabelingPacket,
    load_shadow_labeling_packet,
)


@dataclass(frozen=True)
class ShadowComparisonInputs:
    packet: ShadowLabelingPacket
    execution: ShadowExecutionBundle
    labels: HumanShadowLabelSet


def load_shadow_comparison_inputs(
    labeling_packet: str | Path,
    execution_artifact: str | Path,
    human_labels: str | Path,
) -> ShadowComparisonInputs:
    packet = load_shadow_labeling_packet(labeling_packet)
    execution = load_shadow_execution(execution_artifact)
    labels = load_human_shadow_labels_from_packet(human_labels, packet)
    _validate_execution_matches_packet(packet, execution)
    return ShadowComparisonInputs(
        packet=packet,
        execution=execution,
        labels=labels,
    )


def write_shadow_comparison_html(
    labeling_packet: str | Path,
    execution_artifact: str | Path,
    human_labels: str | Path,
    output: str | Path,
) -> Path:
    inputs = load_shadow_comparison_inputs(
        labeling_packet,
        execution_artifact,
        human_labels,
    )
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render(inputs), encoding="utf-8")
    return path


def _validate_execution_matches_packet(
    packet: ShadowLabelingPacket,
    execution: ShadowExecutionBundle,
) -> None:
    if len(packet.admissions) != len(execution.observations):
        raise ValueError(
            "shadow execution does not preserve every labeling admission"
        )
    for admission, observation in zip(
        packet.admissions,
        execution.observations,
        strict=True,
    ):
        if (
            admission.claim_id != observation.claim_id
            or admission.state != observation.admission_state
            or admission.eligible_count != observation.eligible_count
            or admission.deterministic_evidence_ids
            != observation.deterministic_evidence_ids
            or admission.request != observation.request
        ):
            raise ValueError(
                "shadow execution does not match frozen labeling admission: "
                f"{admission.claim_id}"
            )


def _render(inputs: ShadowComparisonInputs) -> str:
    packet = inputs.packet
    outcomes = _outcomes(inputs)
    all_metrics = shadow_metrics(outcomes)
    accepted_outcomes = tuple(
        item
        for item in outcomes
        if item.observed_execution_state == "accepted"
    )
    accepted_metrics = shadow_metrics(accepted_outcomes)
    labels = inputs.labels.by_claim_id()
    observations = {
        item.claim_id: item for item in inputs.execution.observations
    }
    sections = []
    for admission in packet.admissions:
        observation = observations[admission.claim_id]
        label = labels.get(admission.claim_id)
        sections.append(_claim_section(admission, observation, label))
    pr = f"PR #{packet.pull_request}" if packet.pull_request is not None else "fixture"
    title = f"{packet.repository} · {pr} · LLM shadow comparison"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>{_CSS}</style></head>
<body><main><header><p class="eyebrow">Non-authoritative evaluation</p><h1>{escape(title)}</h1>
<p>This report compares frozen deterministic evidence, validated LLM shadow output, and independent human dispositions. It does not change RepoDelta assessment or mergeability.</p>
<div class="revisions"><code>base {escape(packet.base_sha or 'unavailable')}</code><code>head {escape(packet.head_sha or 'unavailable')}</code></div></header>
{_metric_section('All labeled requests', all_metrics)}
{_metric_section('Accepted labeled requests', accepted_metrics)}
<section><h2>Execution</h2><div class="summary-grid">
{_summary_card('state', inputs.execution.summary.state)}
{_summary_card('admitted', inputs.execution.summary.admitted_count)}
{_summary_card('accepted', inputs.execution.summary.completed_count)}
{_summary_card('failed', inputs.execution.summary.failed_count)}
{_summary_card('deferred', inputs.execution.summary.deferred_count)}
</div></section>
{''.join(sections)}
</main></body></html>"""


def _outcomes(inputs: ShadowComparisonInputs):
    expected = tuple(
        ExpectedShadowOutcome(
            claim_id=item.claim_id,
            execution_state=item.execution_state,
            diagnostic_codes=(
                *(value.code for value in item.diagnostics),
                *(
                    value.code
                    for value in (
                        item.run.diagnostics if item.run is not None else ()
                    )
                ),
            ),
        )
        for item in inputs.execution.observations
    )
    return evaluate_shadow_outcomes(
        "comparison",
        expected,
        inputs.labels,
        inputs.execution,
    )


def _metric_section(title: str, metrics: ShadowEvaluationMetrics) -> str:
    candidate_metric_available = metrics.candidate_label_count > 0
    return f"""<section><h2>{escape(title)}</h2><div class="summary-grid">
{_summary_card('labeled requests', metrics.human_labeled_outcome_count)}
{_summary_card('candidate labels', metrics.candidate_label_count)}
{_summary_card('selection precision', _metric(metrics.selection_precision, candidate_metric_available))}
{_summary_card('selection recall', _metric(metrics.selection_recall, candidate_metric_available))}
{_summary_card('disposition accuracy', _metric(metrics.disposition_accuracy, candidate_metric_available))}
{_summary_card('role accuracy', _metric(metrics.role_accuracy, candidate_metric_available))}
{_summary_card('baseline retention', _metric(metrics.baseline_retention, candidate_metric_available))}
{_summary_card('false rejection', _metric(metrics.false_rejection_rate, candidate_metric_available))}
</div></section>"""


def _metric(value: float, available: bool) -> str:
    return f"{value:.4f}" if available else "n/a"


def _summary_card(label: str, value: object) -> str:
    return (
        '<div class="summary-card"><span>'
        + escape(label)
        + "</span><strong>"
        + escape(str(value))
        + "</strong></div>"
    )


def _claim_section(
    admission: ShadowCandidateAdmission,
    observation: ShadowExecutionObservation,
    label: HumanShadowLabel | None,
) -> str:
    diagnostics = tuple(item.code for item in observation.diagnostics)
    if observation.run is not None:
        diagnostics = (
            *diagnostics,
            *(item.code for item in observation.run.diagnostics),
        )
    request = admission.request
    if request is None:
        return f"""<section class="claim"><div class="claim-head"><h2>{escape(admission.claim_id)}</h2>{_pill(observation.execution_state)}</div>
<p>No model request was created.</p>{_diagnostics(diagnostics)}</section>"""
    human = label.selection if label is not None else None
    model = observation.run.selection if observation.run is not None else None
    rows = "".join(
        _candidate_card(
            candidate,
            admission.deterministic_evidence_ids,
            human,
            model,
        )
        for candidate in request.candidates
    )
    human_unresolved = human.unresolved_surfaces if human is not None else ()
    model_unresolved = model.unresolved_surfaces if model is not None else ()
    unresolved_state = (
        "match"
        if model is not None and set(human_unresolved) == set(model_unresolved)
        else "not compared" if model is None else "mismatch"
    )
    return f"""<section class="claim"><div class="claim-head"><div><p class="eyebrow">{escape(request.subject_kind)}</p><h2>{escape(admission.claim_id)}</h2></div>{_pill(observation.execution_state)}</div>
<p class="statement">{escape(request.authored_statement)}</p>
<p class="coverage"><strong>Coverage limits:</strong> {escape(' · '.join(request.coverage_limits) or 'none')}</p>
{_diagnostics(diagnostics)}
<div class="candidate-grid">{rows}</div>
<div class="unresolved"><h3>Unresolved surfaces · {escape(unresolved_state)}</h3>
<p><strong>Human:</strong> {escape(' · '.join(human_unresolved) or 'none')}</p>
<p><strong>LLM:</strong> {escape(' · '.join(model_unresolved) or 'not observed')}</p></div></section>"""


def _candidate_card(
    candidate: ShadowEvidenceCandidate,
    deterministic_ids: tuple[str, ...],
    human: ShadowEvidenceSelection | None,
    model: ShadowEvidenceSelection | None,
) -> str:
    deterministic = candidate.evidence_id in deterministic_ids
    human_item, human_disposition = _disposition(human, candidate.evidence_id)
    model_item, model_disposition = _disposition(model, candidate.evidence_id)
    comparison = _comparison_group(
        deterministic,
        model is not None,
        model_disposition,
    )
    role_match = (
        human_item is not None
        and model_item is not None
        and human_item.role == model_item.role
        and human_item.semantic_role == model_item.semantic_role
    )
    role_state = (
        "match"
        if role_match
        else "mismatch"
        if human_item is not None and model_item is not None
        else "not applicable"
    )
    path = candidate.path or candidate.qualified_name or candidate.kind
    code = _code(candidate)
    return f"""<article class="candidate {escape(comparison)}"><div class="candidate-head"><code>{escape(candidate.evidence_id)}</code>{_pill(comparison)}</div>
<h3>{escape(candidate.summary)}</h3><p class="path">{escape(path)}</p>
<dl><dt>Deterministic</dt><dd>{'selected' if deterministic else 'not selected'}</dd>
<dt>Human</dt><dd>{escape(_disposition_copy(human_disposition, human_item))}</dd>
<dt>LLM</dt><dd>{escape(_disposition_copy(model_disposition, model_item))}</dd>
<dt>Role comparison</dt><dd>{escape(role_state)}</dd></dl>{code}</article>"""


def _disposition(
    selection: ShadowEvidenceSelection | None,
    evidence_id: str,
) -> tuple[ShadowEvidenceSelectionItem | None, str]:
    if selection is None:
        return None, "not observed"
    selected = next(
        (item for item in selection.selections if item.evidence_id == evidence_id),
        None,
    )
    if selected is not None:
        return selected, "selected"
    if evidence_id in selection.rejected_evidence_ids:
        return None, "rejected"
    if evidence_id in selection.insufficient_evidence_ids:
        return None, "insufficient"
    raise ValueError("validated selection omitted candidate disposition")


def _comparison_group(
    deterministic: bool,
    model_observed: bool,
    model_disposition: str,
) -> str:
    if not model_observed:
        return "not-observed"
    model_selected = model_disposition == "selected"
    if deterministic and model_selected:
        return "shared"
    if deterministic:
        return "deterministic-only"
    if model_selected:
        return "llm-only"
    return "unselected"


def _disposition_copy(
    disposition: str,
    item: ShadowEvidenceSelectionItem | None,
) -> str:
    if item is None:
        return disposition
    return f"{disposition} · {item.role} · {item.semantic_role}"


def _diagnostics(values: tuple[str, ...]) -> str:
    if not values:
        return '<p class="diagnostics">Diagnostics: none</p>'
    return '<p class="diagnostics">Diagnostics: ' + escape(" · ".join(values)) + "</p>"


def _pill(value: str) -> str:
    return f'<span class="pill">{escape(value)}</span>'


def _code(candidate: ShadowEvidenceCandidate) -> str:
    blocks = []
    if candidate.removed_code:
        blocks.append(
            "<details><summary>Removed code</summary><pre>"
            + escape(candidate.removed_code)
            + "</pre></details>"
        )
    if candidate.added_code:
        blocks.append(
            "<details><summary>Added code</summary><pre>"
            + escape(candidate.added_code)
            + "</pre></details>"
        )
    return "".join(blocks)


_CSS = """
:root{color-scheme:dark;--bg:#0a1115;--panel:#111c22;--text:#e8eef0;--muted:#91a0a7;--border:#2b3b43;--green:#77d7a0;--blue:#8ec5ee;--amber:#e6bd6a;--red:#ef8f91}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 ui-sans-serif,system-ui,sans-serif}main{width:min(1180px,calc(100% - 32px));margin:32px auto 80px}header,section{margin:0 0 18px;padding:24px;border:1px solid var(--border);border-radius:14px;background:var(--panel)}h1,h2,h3,p{margin-top:0}.eyebrow{margin-bottom:5px;color:var(--blue);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em}.revisions{display:flex;gap:8px;flex-wrap:wrap}.revisions code,.candidate code{overflow-wrap:anywhere;color:var(--blue)}.summary-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:10px}.summary-card{padding:14px;border:1px solid var(--border);border-radius:10px}.summary-card span{display:block;color:var(--muted);font-size:11px}.summary-card strong{font-size:19px}.claim-head,.candidate-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.pill{display:inline-block;padding:3px 8px;border:1px solid var(--border);border-radius:999px;color:var(--muted);font-size:10px}.statement{font-size:17px}.coverage,.diagnostics,.path{color:var(--muted)}.candidate-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}.candidate{padding:16px;border:1px solid var(--border);border-left:4px solid var(--border);border-radius:10px;background:#0d171c}.candidate.shared{border-left-color:var(--green)}.candidate.llm-only{border-left-color:var(--blue)}.candidate.deterministic-only{border-left-color:var(--amber)}.candidate.not-observed{border-left-color:var(--red)}dl{display:grid;grid-template-columns:120px 1fr;gap:5px 10px}dt{color:var(--muted)}dd{margin:0}details{margin-top:8px}summary{cursor:pointer;color:var(--muted)}pre{max-height:280px;overflow:auto;white-space:pre-wrap;padding:12px;border:1px solid var(--border);border-radius:8px;background:#071014}.unresolved{margin-top:16px;padding-top:14px;border-top:1px solid var(--border)}@media(max-width:620px){main{width:min(100% - 16px,1180px);margin-top:8px}header,section{padding:16px}.candidate-grid{grid-template-columns:1fr}}
"""
