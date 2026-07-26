from __future__ import annotations

import ast
from pathlib import Path

import prismcode.pipeline as pipeline
from prismcode.intake.fixture import load_fixture


SOURCE = Path("src/prismcode")
STAGES = (
    "model",
    "intake",
    "semantics",
    "guardrails",
    "changes",
    "providers",
    "facts",
    "routing",
    "convergence",
    "projection",
    "presentation",
    "evaluation",
)
ALLOWED = {
    "model": {"model", "changes", "providers"},
    "intake": {"model", "intake"},
    "semantics": {"model", "semantics"},
    "guardrails": {"model", "guardrails"},
    "changes": {"model", "changes"},
    "providers": {"model", "changes", "providers"},
    "facts": {"model", "changes", "providers", "facts"},
    "routing": {"model", "facts", "providers", "routing"},
    "convergence": {"model", "convergence"},
    "projection": {"model", "providers", "projection"},
    "presentation": {"model", "presentation"},
    "evaluation": set(STAGES),
}
REQUIRED_README_SECTIONS = (
    "## Owns",
    "## Input / output",
    "## Invariants",
    "## Must not",
    "## Diagnostics",
    "## Extension points",
)
REMOVED_ROOT_MODULES = (
    "analysis.py",
    "association.py",
    "codegraph.py",
    "contracts.py",
    "coverage.py",
    "criteria.py",
    "diff_hunks.py",
    "evaluation.py",
    "evidence_graph.py",
    "fact_semantics.py",
    "fixture.py",
    "github.py",
    "projection.py",
    "rendering.py",
    "selection.py",
    "structural_graph.py",
    "structural_mapping.py",
)


def test_stage_dependencies_follow_the_canonical_pipeline() -> None:
    violations = []
    for stage in STAGES:
        for path in (SOURCE / stage).glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or not node.module:
                    continue
                parts = node.module.split(".")
                if parts[0] != "prismcode" or len(parts) < 2:
                    continue
                dependency = parts[1]
                if dependency in STAGES and dependency not in ALLOWED[stage]:
                    violations.append(f"{path}: {stage} -> {dependency}")
    assert violations == []


def test_each_stage_documents_its_local_contract() -> None:
    for stage in STAGES:
        readme = (SOURCE / stage / "README.md").read_text(encoding="utf-8")
        for heading in REQUIRED_README_SECTIONS:
            assert heading in readme, f"{stage} is missing {heading}"


def test_obsolete_root_modules_are_not_compatibility_paths() -> None:
    assert [name for name in REMOVED_ROOT_MODULES if (SOURCE / name).is_file()] == []
    assert not (SOURCE / "routing" / "selection.py").exists()


def test_presentation_does_not_read_raw_truth_sources() -> None:
    presentation = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (SOURCE / "presentation").glob("*.py")
    )
    forbidden = (
        "verification_observations",
        "packet.diagnostics",
        "structural_graph",
        'metadata.get("merged")',
        'metadata.get("draft")',
        'metadata.get("state")',
        "github_linked_issue_not_found",
        "github_patch_unavailable",
    )
    assert [value for value in forbidden if value in presentation] == []


def test_pipeline_parses_changed_files_once(monkeypatch) -> None:
    analysis_input = load_fixture("fixtures/pr574.json")
    real_parser = pipeline.parse_changed_files
    calls = 0

    def counting_parser(changed_files):
        nonlocal calls
        calls += 1
        return real_parser(changed_files)

    monkeypatch.setattr(pipeline, "parse_changed_files", counting_parser)
    pipeline.DeterministicAnalyzer().analyze(analysis_input)

    assert calls == 1
