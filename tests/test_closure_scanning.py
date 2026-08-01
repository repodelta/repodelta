from __future__ import annotations

import subprocess
from pathlib import Path

from prismcode.changes.hunks import parse_changed_files
from prismcode.closure.planning import compile_closure_scan_plans
from prismcode.closure.scanning import (
    ClosureScanLimits,
    RepositoryClosureScanner,
)
from prismcode.model.contracts import (
    AnalysisInput,
    Requirement,
    ReviewSourcePacket,
    SourceRef,
    TransformationClaim,
    TransformationContract,
    TransformationPredicate,
    TransformationPredicateSet,
)
from prismcode.facts.catalog import build_evidence_catalog
from prismcode.facts.transformation import reconstruct_observed_transformation
from prismcode.pipeline import DeterministicAnalyzer
from prismcode.presentation.html import render_html
from prismcode.routing.transformation import build_transformation_alignment
from prismcode.assessment.transformation import assess_transformation


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
    plans = compile_closure_scan_plans(
        (_guardrail("No compatibility modules remain."),)
    )

    result = RepositoryClosureScanner(
        root,
        expected_head_revision=revision,
    ).scan(plans).results[0].revisions[0]

    assert result.state == "complete"
    assert [(item.path, item.line) for item in result.matches] == [
        ("src/service.py", 1)
    ]
    assert result.coverages[0].surface == "paths"
    assert result.coverages[1].surface == "file_content"
    assert result.coverages[2].surface == "symbol_names"


def test_complete_zero_match_is_an_observation_not_absence(
    tmp_path: Path,
) -> None:
    root, revision = _repository(tmp_path, {"src/service.py": "VALUE = 1\n"})
    plans = compile_closure_scan_plans(
        (_guardrail("No compatibility modules remain."),)
    )
    scanner = RepositoryClosureScanner(root, expected_head_revision=revision)

    brief = DeterministicAnalyzer(closure_scanner=scanner).analyze(
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
        if item.role == "closure_fact"
    ]
    assert len(facts) == 1
    assert facts[0].closure_scan_result is not None
    assert facts[0].closure_scan_result.revisions[0].matches == ()
    review_slice = brief.projection.slices[0]
    assert len(review_slice.closure_fact_relation_ids) == 1
    html = render_html(brief)
    assert 'data-verification-subject="G1"' in html
    assert "guardrail satisfied" not in html.casefold()
    assert "repository absence" not in html.casefold()
    serialized = brief.to_dict()
    serialized_fact = next(
        item
        for item in serialized["evidence_catalog"]["items"]
        if item["role"] == "closure_fact"
    )
    assert serialized_fact["closure_scan_result"]["id"] == "CSR:G1"
    assert "closure_scan_results" not in serialized


def test_no_selector_and_stale_checkout_do_not_create_closure_facts(
    tmp_path: Path,
) -> None:
    root, revision = _repository(tmp_path, {"src/service.py": "VALUE = 1\n"})
    no_selector = compile_closure_scan_plans((_guardrail("No fallback."),))
    no_selector_result = RepositoryClosureScanner(
        root,
        expected_head_revision=revision,
    ).scan(no_selector).results[0].revisions[0]
    stale_result = RepositoryClosureScanner(
        root,
        expected_head_revision="0" * 40,
    ).scan(
        compile_closure_scan_plans(
            (_guardrail("No compatibility modules remain."),)
        )
    ).results[0].revisions[0]

    assert no_selector_result.state == "unavailable"
    assert no_selector_result.diagnostics[0].code == (
        "closure_scan_no_executable_selector"
    )
    assert stale_result.state == "unavailable"
    assert stale_result.diagnostics[0].code == "closure_scan_stale_checkout"


def test_dirty_tracked_checkout_is_not_reported_as_pr_head(
    tmp_path: Path,
) -> None:
    root, revision = _repository(tmp_path, {"src/service.py": "VALUE = 1\n"})
    (root / "src/service.py").write_text("VALUE = 2\n", encoding="utf-8")
    plans = compile_closure_scan_plans(
        (_guardrail("No compatibility modules remain."),)
    )

    result = RepositoryClosureScanner(
        root,
        expected_head_revision=revision,
    ).scan(plans).results[0].revisions[0]

    assert result.state == "unavailable"
    assert result.diagnostics[0].code == "closure_scan_dirty_checkout"


def test_explicit_safety_limit_produces_partial_coverage(tmp_path: Path) -> None:
    root, revision = _repository(
        tmp_path,
        {
            "a.txt": "compatibility modules\n",
            "b.txt": "compatibility modules\n",
        },
    )
    plans = compile_closure_scan_plans(
        (_guardrail("No compatibility modules remain."),)
    )

    result = RepositoryClosureScanner(
        root,
        expected_head_revision=revision,
        limits=ClosureScanLimits(max_files=1),
    ).scan(plans).results[0].revisions[0]

    assert result.state == "partial"
    assert result.coverages[0].state == "partial"
    assert len(result.truncations) == 1
    assert result.truncations[0].kind == "file_limit"
    assert result.truncations[0].surface == "paths"
    assert result.truncations[0].limit == 1
    assert result.truncations[0].observed == 2
    assert result.diagnostics[0].code == "closure_scan_budget_truncated"
    assert "file_limit reached 1 while observing 2 items on paths" in (
        result.diagnostics[0].message
    )


def test_byte_and_match_limits_retain_exact_typed_boundaries(
    tmp_path: Path,
) -> None:
    root, revision = _repository(
        tmp_path,
        {"a.txt": "compatibility modules\ncompatibility modules\n"},
    )
    plans = compile_closure_scan_plans(
        (_guardrail("No compatibility modules remain."),)
    )

    byte_result = RepositoryClosureScanner(
        root,
        expected_head_revision=revision,
        limits=ClosureScanLimits(max_bytes=1),
    ).scan(plans).results[0].revisions[0]
    match_result = RepositoryClosureScanner(
        root,
        expected_head_revision=revision,
        limits=ClosureScanLimits(max_matches_per_plan=1),
    ).scan(plans).results[0].revisions[0]

    assert byte_result.truncations[0].kind == "byte_limit"
    assert byte_result.truncations[0].surface == "file_content"
    assert byte_result.truncations[0].limit == 1
    assert match_result.truncations[0].kind == "match_limit"
    assert match_result.truncations[0].surface == "file_content"
    assert match_result.truncations[0].limit == 1


def test_identifier_selector_scans_symbol_name_surface(tmp_path: Path) -> None:
    root, revision = _repository(
        tmp_path,
        {"src/service.py": "legacy_mode = False\n"},
    )
    plans = compile_closure_scan_plans(
        (_guardrail("No `legacy_mode` remains."),)
    )

    result = RepositoryClosureScanner(
        root,
        expected_head_revision=revision,
    ).scan(plans).results[0].revisions[0]

    assert result.state == "complete"
    assert any(item.surface == "symbol_names" for item in result.matches)
    assert result.coverages[2].state == "complete"
    assert result.coverages[2].inspected_count > 0


def test_removal_scan_preserves_base_head_transition_and_path_profiles(
    tmp_path: Path,
) -> None:
    base, base_revision = _repository(
        tmp_path,
        {
            "src/service.py": "legacy_writer = True\n",
            "tests/test_service.py": "assert legacy_writer\n",
            "docs/design.md": "legacy_writer\n",
        },
    )
    head = tmp_path / "head"
    subprocess.run(["git", "clone", "-q", str(base), str(head)], check=True)
    subprocess.run(
        ["git", "-C", str(head), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(head), "config", "user.name", "PrismCode Test"],
        check=True,
    )
    for relative in ("src/service.py", "tests/test_service.py", "docs/design.md"):
        (head / relative).write_text("replacement = True\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(head), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(head), "commit", "-qm", "remove legacy writer"],
        check=True,
    )
    head_revision = subprocess.run(
        ["git", "-C", str(head), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    claim = TransformationClaim(
        id="T1",
        kind="removal",
        text="Remove `legacy_writer`.",
        sources=(SourceRef(label="PR #1"),),
    )
    contract = TransformationContract(
        claims=(claim,),
        predicates=TransformationPredicateSet(
            predicates=(
                TransformationPredicate(
                    id="TP:T1:1",
                    claim_id="T1",
                    selector_kind="symbol",
                    values=("legacy_writer",),
                    expectation="absent_head",
                    sources=claim.sources,
                ),
            ),
        ),
        removal_claim_ids=("T1",),
        source_state="available",
    )
    plans = compile_closure_scan_plans((), contract)

    result_set = RepositoryClosureScanner(
        head,
        expected_head_revision=head_revision,
        base_root=base,
        expected_base_revision=base_revision,
    ).scan(plans)
    result = result_set.results[0]

    assert tuple(item.revision_side for item in result.revisions) == (
        "base",
        "head",
    )
    assert {item.profile for item in result.revisions[0].matches} >= {
        "production",
        "test",
        "document",
    }
    assert result.revisions[1].matches == ()

    catalog = build_evidence_catalog(
        ReviewSourcePacket(
            repository="acme/widget",
            pull_request=1,
            title="Remove legacy writer",
            source_records=(),
            head_sha=head_revision,
            base_sha=base_revision,
        ).with_revision(),
        parse_changed_files(()),
        closure_scan_results=result_set,
    )
    closure_facts = tuple(
        item for item in catalog.items if item.role == "closure_fact"
    )
    assert len(closure_facts) == 1
    assert closure_facts[0].associated_statement_ids == ("T1",)
    assert closure_facts[0].id not in repr(
        reconstruct_observed_transformation(catalog)
    )
    alignment = build_transformation_alignment(
        contract,
        reconstruct_observed_transformation(catalog),
        catalog,
    )
    assert len(alignment.bindings) == 1
    assert alignment.bindings[0].evidence_role == "closure"
    assert alignment.bindings[0].association == "provided_association"
    assessment = assess_transformation(
        contract,
        alignment,
        catalog,
        plans,
        head_sha=head_revision,
    )
    assert assessment.claims[0].status == "demonstrated"
    assert assessment.claims[0].reasons[0].kind == (
        "closure_transition_observed"
    )


def test_scoped_removal_ignores_same_symbol_outside_declared_path(
    tmp_path: Path,
) -> None:
    base, base_revision = _repository(
        tmp_path,
        {
            "src/prismcode/convergence/structural.py": (
                "def _review_symbol_id():\n    return 'legacy'\n"
            ),
            "src/prismcode/facts/catalog.py": (
                "def _review_symbol_id():\n    return 'canonical-other-surface'\n"
            ),
        },
    )
    head = tmp_path / "head"
    subprocess.run(["git", "clone", "-q", str(base), str(head)], check=True)
    subprocess.run(
        ["git", "-C", str(head), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(head), "config", "user.name", "PrismCode Test"],
        check=True,
    )
    (head / "src/prismcode/convergence/structural.py").write_text(
        "from prismcode.model.structural_refs import review_symbol_id\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(head), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(head), "commit", "-qm", "move identity authority"],
        check=True,
    )
    head_revision = subprocess.run(
        ["git", "-C", str(head), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    claim = TransformationClaim(
        id="T1",
        kind="removal",
        text=(
            "Removed `_review_symbol_id` from "
            "`src/prismcode/convergence/structural.py`."
        ),
        sources=(SourceRef(label="PR #1"),),
    )
    contract = TransformationContract(
        claims=(claim,),
        predicates=TransformationPredicateSet(
            predicates=(
                TransformationPredicate(
                    id="TP:T1:1",
                    claim_id="T1",
                    selector_kind="symbol",
                    values=("_review_symbol_id",),
                    expectation="absent_head",
                    sources=claim.sources,
                ),
                TransformationPredicate(
                    id="TP:T1:2",
                    claim_id="T1",
                    selector_kind="repository_path",
                    values=("src/prismcode/convergence/structural.py",),
                    expectation="absent_head",
                    role="path_scope",
                    sources=claim.sources,
                ),
            ),
        ),
        removal_claim_ids=("T1",),
        source_state="available",
    )
    plans = compile_closure_scan_plans((), contract)
    result_set = RepositoryClosureScanner(
        head,
        expected_head_revision=head_revision,
        base_root=base,
        expected_base_revision=base_revision,
    ).scan(plans)
    result = result_set.results[0]

    assert {item.path for item in result.revisions[0].matches} == {
        "src/prismcode/convergence/structural.py"
    }
    assert result.revisions[1].matches == ()

    catalog = build_evidence_catalog(
        ReviewSourcePacket(
            repository="acme/widget",
            pull_request=1,
            title="Move identity authority",
            source_records=(),
            head_sha=head_revision,
            base_sha=base_revision,
        ).with_revision(),
        parse_changed_files(()),
        closure_scan_results=result_set,
    )
    alignment = build_transformation_alignment(
        contract,
        reconstruct_observed_transformation(catalog),
        catalog,
    )
    assessment = assess_transformation(
        contract,
        alignment,
        catalog,
        plans,
        head_sha=head_revision,
    )

    assert assessment.claims[0].status == "demonstrated"
    assert assessment.claims[0].reasons[0].kind == (
        "closure_transition_observed"
    )
