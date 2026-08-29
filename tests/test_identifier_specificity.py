from __future__ import annotations

from dataclasses import replace

import pytest

from repodelta.evaluation.association_attribution import (
    AssociationAttributionObservation,
    AssociationAttributionRow,
)
from repodelta.evaluation.identifier_specificity import (
    _term_observation,
    compare_identifier_policies,
    IdentifierTermObservation,
    load_identifier_specificity,
    observe_identifier_specificity_from_artifacts,
    term_ok,
    write_identifier_specificity,
)
from repodelta.evaluation.structural_correctness import (
    StructuralRelationCandidate,
    StructuralSubject,
)
from repodelta.model.contracts import AssociationReason
from repodelta.model.contracts import AssociationSignature, EvidenceItem
from repodelta.cli import build_parser

from test_structural_correctness import _labels, _observation, _packet


def _inputs(term: str = "verificationworkspace"):
    source = _packet()
    matched_term = (
        "verificationworkspace" if term == "verification_workspace" else term
    )
    statement_term = (
        "VerificationWorkspace"
        if term == "verificationworkspace"
        else "verification_workspace"
    )
    packet = replace(
        source,
        subjects=(
            StructuralSubject("R1", "requirement", f"Change {statement_term}."),
            StructuralSubject("G1", "guardrail", "Do not change c."),
        ),
        symbols=(replace(source.symbols[0], qualified_name="VerificationWorkspace"),)
        + source.symbols[1:],
        relations=source.relations
        + (StructuralRelationCandidate("REL:2", "S:c", "S:b", "calls", "modified"),),
        relation_ids=("REL:1", "REL:2"),
    )
    observation = replace(_observation(source), packet_digest=packet.digest)
    labels = replace(_labels(source), packet_digest=packet.digest)
    attribution = AssociationAttributionObservation(
        packet_digest=packet.digest,
        subject_kinds=(("G1", "guardrail"), ("R1", "requirement")),
        rows=(
            AssociationAttributionRow(
                subject_id="R1",
                subject_kind="requirement",
                relation_id="REL:1",
                slot="changed_anchor",
                target_type="evidence",
                target_id="E:target",
                association="exact_identifier",
                reasons=(
                    AssociationReason(
                        "exact_identifier", "identifier overlap", (matched_term,)
                    ),
                    AssociationReason(
                        "claim_bridge", "supporting bridge", ("review",)
                    ),
                ),
                matched_terms=(matched_term, "review"),
                source_channel="evidence",
                evidence_role="primary",
                bridge_ids=(),
                candidate_state="selected",
                candidate_node_id="S:a",
                structural_member_id="S:a",
                structural_membership_class="matched",
            ),
            AssociationAttributionRow(
                subject_id="R1",
                subject_kind="requirement",
                relation_id="REL:2",
                slot="changed_anchor",
                target_type="evidence",
                target_id="E:target-2",
                association="exact_identifier",
                reasons=(
                    AssociationReason(
                        "exact_identifier", "identifier overlap", (matched_term,)
                    ),
                    AssociationReason(
                        "claim_bridge", "supporting bridge", ("review",)
                    ),
                ),
                matched_terms=(matched_term, "review"),
                source_channel="evidence",
                evidence_role="primary",
                bridge_ids=(),
                candidate_state="selected",
                candidate_node_id="S:c",
                structural_member_id="S:c",
                structural_membership_class="matched",
            ),
        ),
    )
    return packet, observation, labels, attribution


def test_canonical_full_identifier_is_distinguished_from_suffix_alias() -> None:
    packet, _, _, attribution = _inputs("verification_workspace")
    full = observe_identifier_specificity_from_artifacts(packet, attribution)
    full_term = full.rows[0].terms[0]
    assert full_term.source_forms == ("full_identifier",)
    assert full_term.origins == ("qualified_name",)
    assert full_term.canonical_resolution == "unique"

    packet, _, _, attribution = _inputs("workspace")
    suffix = observe_identifier_specificity_from_artifacts(packet, attribution)
    suffix_term = suffix.rows[0].terms[0]
    assert suffix_term.source_forms == ("suffix_alias",)
    assert suffix_term.canonical_resolution == "none"


def test_orthogonal_policy_shadows_keep_origin_and_fanout_separate() -> None:
    canonical_fanout_two = IdentifierTermObservation(
        term="verificationworkspace",
        source_forms=("full_identifier",),
        origins=("qualified_name",),
        canonical_full_match_count=1,
        canonical_resolution="unique",
        fanout=2,
    )
    unobserved_fanout_one = IdentifierTermObservation(
        term="verificationworkspace",
        source_forms=("full_identifier",),
        origins=("unobserved",),
        canonical_full_match_count=1,
        canonical_resolution="unique",
        fanout=1,
    )

    assert term_ok("qualified_token_present", canonical_fanout_two)
    assert not term_ok("full_token_low_fanout", canonical_fanout_two)
    assert not term_ok("qualified_token_present", unobserved_fanout_one)
    assert term_ok("full_token_low_fanout", unobserved_fanout_one)


def test_identifier_token_collision_fails_closed() -> None:
    packet, observation, labels, attribution = _inputs()
    symbols = list(packet.symbols)
    symbols[0] = replace(
        symbols[0], qualified_name="pkg.alpha.VerificationWorkspace"
    )
    symbols[2] = replace(
        symbols[2], qualified_name="pkg.beta.VerificationWorkspace"
    )
    packet = replace(packet, symbols=tuple(symbols))
    observation = replace(observation, packet_digest=packet.digest)
    labels = replace(labels, packet_digest=packet.digest)
    attribution = replace(attribution, packet_digest=packet.digest)

    specificity = observe_identifier_specificity_from_artifacts(
        packet, attribution
    )
    term = specificity.rows[0].terms[0]

    assert term.canonical_full_match_count == 2
    assert term.canonical_resolution == "multiple"
    assert term.origins == ("qualified_name",)
    result = compare_identifier_policies(
        packet, observation, labels, attribution, specificity
    )
    assert result["overall"]["canonical_token_unique"] == {
        "false_inclusions": 0,
        "false_exclusions": 1,
    }


def test_missing_origin_metadata_is_not_guessed_as_canonical() -> None:
    packet, _, _, attribution = _inputs()
    first = attribution.rows[0]
    attribution = replace(
        attribution,
        rows=(
            replace(
                first,
                candidate_node_id=None,
                structural_member_id=None,
                structural_membership_class=None,
            ),
            *attribution.rows[1:],
        ),
    )

    specificity = observe_identifier_specificity_from_artifacts(
        packet, attribution
    )
    term = specificity.rows[0].terms[0]

    assert term.origins == ("unobserved",)
    assert "qualified_name" not in term.origins
    assert specificity.origin_completeness == "partial"


def test_signature_without_canonical_origin_is_classified_explicitly() -> None:
    target = EvidenceItem(
        id="E:signature-only",
        summary="Signature-only evidence",
        kind="structural_change",
        classification="code",
        head_signature=AssociationSignature(identifiers=("github",)),
        metadata={"summary": "GitHub appears in a non-diff summary"},
    )
    observed = _term_observation(
        "github",
        {"github": ("full_identifier",)},
        target,
        None,
        (),
        (),
        (),
    )

    assert observed.origins == ("signature_unattributed",)
    assert observed.canonical_resolution == "unobserved"


def test_packet_digest_mismatch_fails_closed() -> None:
    packet, observation, labels, attribution = _inputs()
    mismatched_attribution = replace(attribution, packet_digest="wrong")

    with pytest.raises(ValueError, match="association attribution does not match"):
        observe_identifier_specificity_from_artifacts(packet, mismatched_attribution)

    specificity = observe_identifier_specificity_from_artifacts(packet, attribution)
    mismatched_observation = replace(observation, packet_digest="wrong")
    with pytest.raises(ValueError, match="observation does not match"):
        compare_identifier_policies(
            packet,
            mismatched_observation,
            labels,
            attribution,
            specificity,
        )


def test_identifier_specificity_round_trip_is_deterministic(tmp_path) -> None:
    packet, _, _, attribution = _inputs()
    value = observe_identifier_specificity_from_artifacts(packet, attribution)

    first_path = write_identifier_specificity(value, tmp_path / "first.json")
    loaded = load_identifier_specificity(first_path)
    second_path = write_identifier_specificity(loaded, tmp_path / "second.json")

    assert loaded == value
    assert first_path.read_text(encoding="utf-8") == second_path.read_text(
        encoding="utf-8"
    )


def test_policy_shadow_is_direct_only_and_rejects_suffix_without_mutating_observation() -> None:
    packet, observation, labels, attribution = _inputs("workspace")
    specificity = observe_identifier_specificity_from_artifacts(packet, attribution)
    result = compare_identifier_policies(
        packet, observation, labels, attribution, specificity
    )
    assert result["causal_replay"] is False
    assert result["downstream_replay"] is False
    assert result["overall"]["current"] == {
        "false_inclusions": 1,
        "false_exclusions": 0,
    }
    assert result["overall"]["canonical_token_unique"] == {
        "false_inclusions": 0,
        "false_exclusions": 1,
    }
    assert observation.focuses[0].direct_node_ids == ("S:a", "S:c")


def test_current_policy_reproduces_observed_direct_membership() -> None:
    packet, observation, labels, attribution = _inputs()
    specificity = observe_identifier_specificity_from_artifacts(packet, attribution)
    result = compare_identifier_policies(
        packet, observation, labels, attribution, specificity
    )
    focus = next(item for item in result["per_focus"] if item["subject_id"] == "R1")
    assert focus["policies"]["current"][
        "observed_direct_nodes"
    ] == ["S:a", "S:c"]


def test_identifier_shadow_commands_have_explicit_inputs() -> None:
    parser = build_parser()
    observe = parser.parse_args(
        [
            "observe-structural-identifier",
            "--labeling-packet",
            "packet.json",
            "--association-attribution",
            "association.json",
            "--output",
            "specificity.json",
        ]
    )
    assert observe.association_attribution == "association.json"
    compare = parser.parse_args(
        [
            "compare-structural-identifier",
            "--labeling-packet",
            "packet.json",
            "--observation",
            "observation.json",
            "--association-attribution",
            "association.json",
            "--identifier-specificity",
            "specificity.json",
            "--reference-labels",
            "labels.json",
            "--output",
            "shadow.json",
        ]
    )
    assert compare.identifier_specificity == "specificity.json"


def test_structural_change_diff_origin_uses_canonical_relation_identity() -> None:
    target = EvidenceItem(
        id="E:structural-change",
        summary="Modified function: adapter",
        kind="structural_change",
        classification="code",
        head_signature=AssociationSignature(identifiers=("github",)),
        change_relation_ids=("CR:1",),
    )
    diff = EvidenceItem(
        id="E:change-relation",
        summary="Added change",
        kind="change_relation",
        classification="code",
        metadata={"head_preview": "uses GitHub app credentials"},
        change_relation_ids=("CR:1",),
    )
    observed = _term_observation(
        "github",
        {"github": ("full_identifier",)},
        target,
        None,
        (),
        [],
        (diff,),
    )
    assert observed.origins == ("diff_text",)
