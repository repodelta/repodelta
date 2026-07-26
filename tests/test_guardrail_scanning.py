from __future__ import annotations

import subprocess
from pathlib import Path

from prismcode.guardrails.planning import compile_guardrail_scan_plans
from prismcode.guardrails.scanning import (
    GuardrailScanLimits,
    RepositoryGuardrailScanner,
)
from prismcode.model.contracts import (
    AnalysisInput,
    Requirement,
    ReviewSourcePacket,
)
from prismcode.pipeline import DeterministicAnalyzer
from prismcode.presentation.html import render_html


def _guardrail(text: str) -> Requirement:
    return Requirement(
        id="G1",
        text=text,
        purpose="guardrail",
        kind="guardrail",
    )


def _repository(tmp_path: Path, files: dict[str, str]) -> tuple[Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(root), "config", "user.name", "PrismCode Test"],
        check=True,
    )
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-qm", "fixture"],
        check=True,
    )
    revision = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return root, revision


def test_bounded_scan_matches_typed_phrase_and_ignores_vendor_tree(
    tmp_path: Path,
) -> None:
    root, revision = _repository(
        tmp_path,
        {
            "src/service.py": "# compatibility modules are not loaded\n",
            "node_modules/noise.js": "// compatibility modules\n",
        },
    )
    (root / ".env").write_text(
        "compatibility modules local secret\n",
        encoding="utf-8",
    )
    plans = compile_guardrail_scan_plans(
        (_guardrail("No compatibility modules remain."),)
    )

    result = RepositoryGuardrailScanner(
        root,
        expected_revision=revision,
    ).scan(plans).results[0]

    assert result.state == "complete"
    assert [(item.path, item.line) for item in result.matches] == [
        ("src/service.py", 1)
    ]
    assert result.coverages[0].surface == "paths"
    assert result.coverages[1].surface == "file_content"


def test_complete_zero_match_is_an_observation_not_absence(
    tmp_path: Path,
) -> None:
    root, revision = _repository(tmp_path, {"src/service.py": "VALUE = 1\n"})
    plans = compile_guardrail_scan_plans(
        (_guardrail("No compatibility modules remain."),)
    )
    scanner = RepositoryGuardrailScanner(root, expected_revision=revision)

    brief = DeterministicAnalyzer(guardrail_scanner=scanner).analyze(
        AnalysisInput(
            packet=ReviewSourcePacket(
                repository="acme/widget",
                pull_request=1,
                title="Bounded scan",
                source_records=(),
                head_sha=revision,
            ).with_revision(),
            requirements=(_guardrail("No compatibility modules remain."),),
        )
    )

    facts = [
        item for item in brief.evidence_catalog.items
        if item.role == "boundary_fact"
    ]
    assert len(facts) == 1
    assert facts[0].guardrail_scan_result is not None
    assert facts[0].guardrail_scan_result.matches == ()
    review_slice = brief.projection.slices[0]
    assert len(review_slice.boundary_fact_relation_ids) == 1
    html = render_html(brief)
    assert "No selector match observed within the stated bounded coverage." in html
    assert "guardrail satisfied" not in html.casefold()
    assert "repository absence" not in html.casefold()
    serialized = brief.to_dict()
    serialized_fact = next(
        item
        for item in serialized["evidence_catalog"]["items"]
        if item["role"] == "boundary_fact"
    )
    assert serialized_fact["guardrail_scan_result"]["id"] == "GSR:G1"
    assert "guardrail_scan_results" not in serialized


def test_no_selector_and_stale_checkout_do_not_create_boundary_facts(
    tmp_path: Path,
) -> None:
    root, revision = _repository(tmp_path, {"src/service.py": "VALUE = 1\n"})
    no_selector = compile_guardrail_scan_plans((_guardrail("No fallback."),))
    no_selector_result = RepositoryGuardrailScanner(
        root,
        expected_revision=revision,
    ).scan(no_selector).results[0]
    stale_result = RepositoryGuardrailScanner(
        root,
        expected_revision="0" * 40,
    ).scan(
        compile_guardrail_scan_plans(
            (_guardrail("No compatibility modules remain."),)
        )
    ).results[0]

    assert no_selector_result.state == "unavailable"
    assert no_selector_result.diagnostics[0].code == (
        "guardrail_scan_no_executable_selector"
    )
    assert stale_result.state == "unavailable"
    assert stale_result.diagnostics[0].code == "guardrail_scan_stale_checkout"


def test_explicit_safety_limit_produces_partial_coverage(tmp_path: Path) -> None:
    root, revision = _repository(
        tmp_path,
        {
            "a.txt": "compatibility modules\n",
            "b.txt": "compatibility modules\n",
        },
    )
    plans = compile_guardrail_scan_plans(
        (_guardrail("No compatibility modules remain."),)
    )

    result = RepositoryGuardrailScanner(
        root,
        expected_revision=revision,
        limits=GuardrailScanLimits(max_files=1),
    ).scan(plans).results[0]

    assert result.state == "partial"
    assert result.coverages[0].state == "partial"
    assert result.diagnostics[0].code == "guardrail_scan_budget_truncated"
