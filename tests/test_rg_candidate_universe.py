from __future__ import annotations

import json
import sys
from dataclasses import replace

import pytest

from repodelta.cli import build_parser, main
from repodelta.evaluation.rg_candidate_universe import (
    RGSemanticReferenceGap,
    RGSemanticReferenceLabel,
    compare_rg_retrieval,
    load_rg_candidate_universe,
    load_rg_retrieval_observation,
    load_rg_semantic_reference,
    observe_rg_retrieval,
    prepare_rg_candidate_universe,
    prepare_rg_semantic_reference_template,
    verify_rg_semantic_reference,
    write_rg_candidate_artifact,
)
from repodelta.evaluation.structural_correctness import (
    prepare_structural_correctness_packet,
)
from repodelta.model.contracts import (
    EvidenceCatalog,
    EvidenceItem,
    SourceRef,
    StructuralChangeIdentity,
)

from test_focus_provenance import _association_brief


def _brief():
    source = _association_brief()
    changed_symbol = EvidenceItem(
        id="EV:anchor:a",
        summary="Changed anchor a",
        kind="structural_change",
        classification="code",
        profile="production",
        revision_side="head",
        operation="modified",
        role="changed_anchor",
        changed=True,
        structural_change=StructuralChangeIdentity(review_symbol_id="N:a"),
        sources=(
            SourceRef(
                "src/a.py changed anchor",
                "https://example.test/pull/1/files#R10",
                "src/a.py",
                10,
                12,
            ),
        ),
        metadata={"path": "src/a.py"},
    )
    changed_file = EvidenceItem(
        id="EV:anchor:file",
        summary="Changed unindexed file",
        kind="changed_file",
        classification="document",
        profile="document",
        revision_side="head",
        operation="modified",
        role="changed_anchor",
        changed=True,
        sources=(SourceRef("docs/notes.md", path="docs/notes.md"),),
        metadata={"path": "docs/notes.md"},
    )
    generated = EvidenceItem(
        id="EV:anchor:generated",
        summary="Generated code",
        kind="changed_file",
        classification="code",
        profile="generated",
        revision_side="head",
        operation="modified",
        role="changed_anchor",
        changed=True,
    )
    relation = next(
        item
        for item in source.projection_candidates.relations
        if item.focus_statement_id == "R1"
    )
    candidates = replace(
        source.projection_candidates,
        relations=tuple(
            replace(
                item,
                target_id=(
                    "EV:anchor:a"
                    if item.focus_statement_id == "R1"
                    else "EV:anchor:file"
                ),
            )
            if item.focus_statement_id in {"R1", "G1"}
            else item
            for item in source.projection_candidates.relations
        ),
    )
    return replace(
        source,
        evidence_catalog=EvidenceCatalog(
            (*source.evidence_catalog.items, changed_symbol, changed_file, generated)
        ),
        projection_candidates=candidates,
    )


def _reference(universe):
    template = prepare_rg_semantic_reference_template(
        universe, proposed_by="independent-labeler"
    )
    labels = []
    for label in template.labels:
        if label.candidate_id == "C:R1:EV:anchor:a":
            labels.append(
                RGSemanticReferenceLabel(
                    candidate_id=label.candidate_id,
                    semantic_relation="implements",
                    proofability="direct_capable",
                    proof_basis="typed_predicate",
                    evidence_witnesses=("src/a.py#L10",),
                )
            )
        elif label.candidate_id == "C:G1:EV:anchor:a":
            labels.append(
                RGSemanticReferenceLabel(
                    candidate_id=label.candidate_id,
                    semantic_relation="contextual_support",
                    proofability="not_applicable",
                    proof_basis="none",
                )
            )
        else:
            labels.append(replace(label, review_status="reviewed"))
    return replace(template, labels=tuple(sorted(labels, key=lambda item: item.candidate_id)))


def _verified_reference(universe):
    return verify_rg_semantic_reference(
        _reference(universe),
        universe,
        verified_by="independent-reviewer",
        verification_method="reviewed source anchors without retrieval observation",
        verification_evidence=("https://example.test/pull/1/files",),
        system_under_test_isolated=True,
    )


def test_candidate_universe_precedes_association_and_retains_unresolved_nodes() -> None:
    brief = _brief()
    packet = prepare_structural_correctness_packet(brief)

    universe = prepare_rg_candidate_universe(brief, packet)

    assert [item.candidate_id for item in universe.candidates] == [
        "C:G1:EV:anchor:a",
        "C:G1:EV:anchor:file",
        "C:R1:EV:anchor:a",
        "C:R1:EV:anchor:file",
    ]
    assert [item.evidence_id for item in universe.anchors] == [
        "EV:anchor:a",
        "EV:anchor:file",
    ]
    resolved = next(item for item in universe.anchors if item.evidence_id == "EV:anchor:a")
    assert resolved.canonical_review_symbol_id == "N:a"
    assert resolved.canonical_node_id == "N:a"
    assert resolved.node_state == "node_resolved"
    unindexed = next(item for item in universe.anchors if item.evidence_id == "EV:anchor:file")
    assert unindexed.node_state == "not_node_backed"
    assert "EV:anchor:generated" not in str(universe)
    assert "exact_identifier" not in str(universe)


def test_retrieval_is_observed_separately_from_semantic_reference(tmp_path) -> None:
    brief = _brief()
    packet = prepare_structural_correctness_packet(brief)
    universe = prepare_rg_candidate_universe(brief, packet)
    retrieval = observe_rg_retrieval(brief, packet, universe)

    selected = next(
        item for item in retrieval.rows if item.candidate_id == "C:R1:EV:anchor:a"
    )
    assert selected.retrieval_state == "selected"
    assert selected.association == "exact_identifier"
    assert next(
        item for item in retrieval.rows if item.candidate_id == "C:G1:EV:anchor:file"
    ).retrieval_state == "deferred"
    assert all(
        item.retrieval_state == "not_retrieved"
        for item in retrieval.rows
        if item.candidate_id not in {"C:R1:EV:anchor:a", "C:G1:EV:anchor:file"}
    )

    reference = _verified_reference(universe)
    comparison = compare_rg_retrieval(universe, retrieval, reference)
    assert comparison["production_changed"] is False
    assert comparison["overall"]["retrieval_against_semantic_direct"] == {
        "false_inclusions": 0,
        "false_exclusions": 0,
    }
    assert comparison["overall"]["direct_attempt_against_direct_capable"] == {
        "false_inclusions": 0,
        "false_exclusions": 0,
    }
    assert comparison["coverage"]["not_node_backed_candidates"] == 2

    universe_path = write_rg_candidate_artifact(universe, tmp_path / "universe.json")
    retrieval_path = write_rg_candidate_artifact(retrieval, tmp_path / "retrieval.json")
    reference_path = write_rg_candidate_artifact(reference, tmp_path / "reference.json")
    assert load_rg_candidate_universe(universe_path) == universe
    assert load_rg_retrieval_observation(retrieval_path) == retrieval
    assert load_rg_semantic_reference(reference_path) == reference

    raw_reference = json.loads(reference_path.read_text(encoding="utf-8"))
    raw_reference["authority"]["system_under_test_isolated"] = "false"
    invalid_reference_path = tmp_path / "invalid-reference.json"
    invalid_reference_path.write_text(
        json.dumps(raw_reference), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="system_under_test_isolated must be a boolean"):
        load_rg_semantic_reference(invalid_reference_path)


def test_reference_coverage_and_verification_are_explicit() -> None:
    brief = _brief()
    packet = prepare_structural_correctness_packet(brief)
    universe = prepare_rg_candidate_universe(brief, packet)
    retrieval = observe_rg_retrieval(brief, packet, universe)
    reference = replace(
        _reference(universe),
        out_of_universe=(
            RGSemanticReferenceGap(
                subject_id="R1",
                semantic_relation="implements",
                source_identity="unmapped changed API surface",
                evidence_witnesses=("issue#304",),
            ),
        ),
    )

    verified = verify_rg_semantic_reference(
        reference,
        universe,
        verified_by="independent-reviewer",
        verification_method="reviewed diff and source anchors without retrieval observation",
        verification_evidence=("https://example.test/pull/1/files",),
        system_under_test_isolated=True,
    )
    comparison = compare_rg_retrieval(universe, retrieval, verified)
    assert comparison["coverage"]["out_of_universe_references"] == 1
    assert comparison["reference_authority"]["status"] == "verified"


def test_reference_and_retrieval_fail_closed_when_candidate_disposition_is_missing() -> None:
    brief = _brief()
    packet = prepare_structural_correctness_packet(brief)
    universe = prepare_rg_candidate_universe(brief, packet)
    template = prepare_rg_semantic_reference_template(universe)

    assert all(label.review_status == "pending" for label in template.labels)
    with pytest.raises(ValueError, match="pending candidate labels"):
        verify_rg_semantic_reference(
            template,
            universe,
            verified_by="reviewer",
            verification_method="independent",
            verification_evidence=("evidence",),
            system_under_test_isolated=True,
        )
    with pytest.raises(ValueError, match="verified R/G semantic reference"):
        compare_rg_retrieval(
            universe,
            observe_rg_retrieval(brief, packet, universe),
            template,
        )
    with pytest.raises(ValueError, match="verified R/G semantic reference"):
        compare_rg_retrieval(
            universe,
            observe_rg_retrieval(brief, packet, universe),
            _reference(universe),
        )

    with pytest.raises(ValueError, match="dispose every candidate"):
        compare_rg_retrieval(
            universe,
            replace(
                observe_rg_retrieval(brief, packet, universe),
                rows=observe_rg_retrieval(brief, packet, universe).rows[1:],
            ),
            template,
        )
    with pytest.raises(ValueError, match="dispose every candidate"):
        verify_rg_semantic_reference(
            replace(template, labels=template.labels[1:]),
            universe,
            verified_by="reviewer",
            verification_method="independent",
            verification_evidence=("evidence",),
            system_under_test_isolated=True,
        )


def test_retrieval_fails_closed_when_current_association_escapes_universe() -> None:
    brief = _brief()
    packet = prepare_structural_correctness_packet(brief)
    universe = prepare_rg_candidate_universe(brief, packet)
    escaped = replace(
        brief,
        projection_candidates=replace(
            brief.projection_candidates,
            relations=tuple(
                replace(item, target_id="EV:N:b")
                if item.focus_statement_id == "G1"
                else item
                for item in brief.projection_candidates.relations
            ),
        ),
    )

    with pytest.raises(ValueError, match="escaped the frozen"):
        observe_rg_retrieval(escaped, packet, universe)


def test_cli_exposes_explicit_candidate_comparison_inputs() -> None:
    args = build_parser().parse_args(
        [
            "compare-rg-semantic-candidates",
            "--candidate-universe",
            "candidates.json",
            "--retrieval-observation",
            "retrieval.json",
            "--reference-labels",
            "reference.json",
            "--output",
            "comparison.json",
        ]
    )
    assert args.candidate_universe == "candidates.json"
    assert args.retrieval_observation == "retrieval.json"

    template = build_parser().parse_args(
        [
            "prepare-rg-semantic-reference",
            "--candidate-universe",
            "candidates.json",
            "--proposed-by",
            "independent-labeler",
            "--output",
            "reference.json",
        ]
    )
    assert template.candidate_universe == "candidates.json"
    assert template.proposed_by == "independent-labeler"

    verification = build_parser().parse_args(
        [
            "verify-rg-semantic-reference",
            "--candidate-universe",
            "candidates.json",
            "--reference-labels",
            "proposal.json",
            "--verified-by",
            "independent-reviewer",
            "--verification-method",
            "blind source review",
            "--verification-evidence",
            "issue#304",
            "--verification-evidence",
            "pr#305",
            "--system-under-test-isolated",
            "--output",
            "reference.json",
        ]
    )
    assert verification.reference_labels == "proposal.json"
    assert verification.verification_evidence == ["issue#304", "pr#305"]
    assert verification.system_under_test_isolated is True


def test_cli_only_verifies_a_fully_reviewed_semantic_reference(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief = _brief()
    packet = prepare_structural_correctness_packet(brief)
    universe = prepare_rg_candidate_universe(brief, packet)
    universe_path = write_rg_candidate_artifact(universe, tmp_path / "universe.json")
    proposal_path = write_rg_candidate_artifact(
        _reference(universe), tmp_path / "proposal.json"
    )
    verified_path = tmp_path / "verified.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "repodelta",
            "verify-rg-semantic-reference",
            "--candidate-universe",
            str(universe_path),
            "--reference-labels",
            str(proposal_path),
            "--verified-by",
            "independent-reviewer",
            "--verification-method",
            "blind source review",
            "--verification-evidence",
            "issue#304",
            "--system-under-test-isolated",
            "--output",
            str(verified_path),
        ],
    )

    assert main() == 0
    assert load_rg_semantic_reference(verified_path).authority.status == "verified"
