from __future__ import annotations

from dataclasses import replace

import pytest

from repodelta.facts.lexical import association_signature
from repodelta.model.contracts import (
    AnalysisInput,
    AssociationSignature,
    EvidenceCatalog,
    EvidenceItem,
    ObservedTransformation,
    ReviewSourcePacket,
    SourceRef,
    StructuralChangeIdentity,
    TransformationSubjectSelection,
)
from repodelta.pipeline import DeterministicAnalyzer
from repodelta.routing.transformation_subjects import select_transformation_subjects
from repodelta.semantics.criteria import extract_review_semantics


def _contract():
    return extract_review_semantics(
        issue_body=None,
        issue_source=None,
        pr_body=(
            "## Selected region\n- `src/adapter.py`\n\n"
            "## After topology\n- `Adapter` → `Analyzer`\n\n"
            "## Removed legacy paths\n"
            "- Remove `LegacyAdapter` from `src/legacy.py`.\n"
        ),
        pr_source=SourceRef(label="PR #9"),
        pr_title="Select structural subjects",
    ).transformation_contract


def _change(
    identity: str,
    *,
    path: str,
    base_name: str = "",
    head_name: str = "",
) -> EvidenceItem:
    return EvidenceItem(
        id=identity,
        summary=identity,
        kind="structural_change",
        classification="code",
        profile="production",
        authority="structural_provider",
        revision_side="review",
        operation="modified",
        role="changed_anchor",
        changed=True,
        base_signature=(
            association_signature(base_name)
            if base_name
            else AssociationSignature()
        ),
        head_signature=(
            association_signature(head_name)
            if head_name
            else AssociationSignature()
        ),
        structural_change=StructuralChangeIdentity(review_symbol_id=identity),
        metadata={
            "path": path,
            "base_path": path if base_name else None,
            "head_path": path if head_name else None,
        },
    )


def test_explicit_predicates_select_revision_appropriate_structural_subjects() -> None:
    contract = _contract()
    adapter = _change(
        "E:adapter",
        path="src/adapter.py",
        head_name="pkg.Adapter",
    )
    legacy = _change(
        "E:legacy",
        path="src/legacy.py",
        base_name="pkg.LegacyAdapter",
    )
    head_only_legacy = _change(
        "E:head-legacy",
        path="src/new_legacy.py",
        head_name="pkg.LegacyAdapter",
    )
    catalog = EvidenceCatalog(items=(adapter, legacy, head_only_legacy))
    observed = ObservedTransformation(
        structural_change_evidence_ids=(adapter.id, legacy.id, head_only_legacy.id)
    )

    selection = select_transformation_subjects(contract, observed, catalog)

    assert selection.schema_version == "transformation_subject_selection.v1"
    assert [
        (item.claim_id, item.selector_value, item.evidence_id)
        for item in selection.matches
    ] == [
        ("T1", "src/adapter.py", "E:adapter"),
        ("T2", "Adapter", "E:adapter"),
        ("T3", "LegacyAdapter", "E:legacy"),
    ]
    assert [
        (item.claim_id, item.selector_index, item.state)
        for item in selection.diagnostics
    ] == [("T2", 2, "no_structural_match")]
    assert {
        (item.predicate_id, item.selector_index) for item in selection.matches
    } | {
        (item.predicate_id, item.selector_index) for item in selection.diagnostics
    } == {
        (predicate.id, index)
        for predicate in contract.predicates.predicates
        if predicate.role == "target"
        for index in range(1, len(predicate.values) + 1)
    }


def test_state_selectors_cannot_cross_their_declared_revision() -> None:
    contract = extract_review_semantics(
        issue_body=None,
        issue_source=None,
        pr_body=(
            "## Before\n- `LegacyWriter` controlled the result.\n\n"
            "## After\n- `CanonicalWriter` controls the result.\n"
        ),
        pr_source=SourceRef(label="PR #9"),
        pr_title="Replace writer",
    ).transformation_contract
    base_legacy = _change(
        "E:base-legacy",
        path="src/legacy.py",
        base_name="pkg.LegacyWriter",
    )
    head_legacy = _change(
        "E:head-legacy",
        path="src/wrong_head.py",
        head_name="pkg.LegacyWriter",
    )
    head_canonical = _change(
        "E:head-canonical",
        path="src/canonical.py",
        head_name="pkg.CanonicalWriter",
    )
    base_canonical = _change(
        "E:base-canonical",
        path="src/wrong_base.py",
        base_name="pkg.CanonicalWriter",
    )
    catalog = EvidenceCatalog(
        items=(base_legacy, head_legacy, head_canonical, base_canonical)
    )
    observed = ObservedTransformation(
        structural_change_evidence_ids=tuple(item.id for item in catalog.items)
    )

    selection = select_transformation_subjects(contract, observed, catalog)

    assert [(item.claim_id, item.evidence_id) for item in selection.matches] == [
        ("T1", "E:base-legacy"),
        ("T2", "E:head-canonical"),
    ]


def test_subject_selection_rejects_parallel_match_and_diagnostic_truth() -> None:
    contract = _contract()
    adapter = _change(
        "E:adapter",
        path="src/adapter.py",
        head_name="pkg.Adapter",
    )
    catalog = EvidenceCatalog(items=(adapter,))
    observed = ObservedTransformation(
        structural_change_evidence_ids=(adapter.id,)
    )
    selection = select_transformation_subjects(contract, observed, catalog)
    match = selection.matches[0]
    diagnostic = selection.diagnostics[0]

    with pytest.raises(ValueError, match="both matched and diagnostic"):
        replace(
            selection,
            diagnostics=(
                replace(
                    diagnostic,
                    claim_id=match.claim_id,
                    predicate_id=match.predicate_id,
                    selector_index=match.selector_index,
                    id=(
                        f"TSD:{match.predicate_id}:{match.selector_index}:"
                        "no_structural_match"
                    ),
                ),
            ),
        ).validate_consistency(contract, observed, catalog)


def test_pipeline_builds_transformation_subject_selection_once(monkeypatch) -> None:
    import repodelta.pipeline as pipeline

    calls = 0
    real_select = pipeline.select_transformation_subjects

    def counting_select(contract, observed, catalog):
        nonlocal calls
        calls += 1
        return real_select(contract, observed, catalog)

    monkeypatch.setattr(pipeline, "select_transformation_subjects", counting_select)
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=9,
        title="Select structural subjects",
        source_records=(),
    ).with_revision()

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))

    assert calls == 1
    assert isinstance(
        brief.transformation_subject_selection,
        TransformationSubjectSelection,
    )
