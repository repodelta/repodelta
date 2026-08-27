from __future__ import annotations

from dataclasses import replace

from repodelta.evaluation.association_attribution import (
    AssociationAttributionObservation,
    AssociationAttributionRow,
)
from repodelta.evaluation.identifier_specificity import (
    compare_identifier_policies,
    observe_identifier_specificity_from_artifacts,
)
from repodelta.evaluation.structural_correctness import (
    StructuralRelationCandidate,
    StructuralSubject,
)
from repodelta.model.contracts import AssociationReason
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
                ),
                matched_terms=(matched_term,),
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
                ),
                matched_terms=(matched_term,),
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
    assert result["overall"]["canonical_unique"] == {
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
