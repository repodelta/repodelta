from __future__ import annotations

from dataclasses import fields

from prismcode.convergence.core import ConvergencePolicy, converge_candidates
from prismcode.model.contracts import (
    EvidenceCatalog,
    EvidenceItem,
    ProjectionCandidateGroup,
    ProjectionCandidateSet,
    ProjectionRelation,
    SourceRef,
    VerificationIdentity,
)


def _relation(
    relation_id: str,
    *,
    focus: str = "R1",
    slot: str,
    target: str,
    association: str,
    bridges: tuple[str, ...] = (),
    ordinal: int = 0,
) -> ProjectionRelation:
    return ProjectionRelation(
        id=relation_id,
        focus_statement_id=focus,
        slot=slot,
        target_type="statement" if slot == "claim" else "evidence",
        target_id=target,
        association=association,
        reasons=(),
        bridge_ids=bridges,
        source_ordinal=ordinal,
    )


def _candidates(*relations: ProjectionRelation) -> ProjectionCandidateSet:
    focus_ids = tuple(dict.fromkeys(item.focus_statement_id for item in relations))
    return ProjectionCandidateSet(
        relations=relations,
        groups=tuple(
            ProjectionCandidateGroup(
                focus_statement_id=focus_id,
                profile="generic",
                relation_ids=tuple(
                    item.id for item in relations if item.focus_statement_id == focus_id
                ),
            )
            for focus_id in focus_ids
        ),
    )


def _verification(
    fact_id: str,
    *,
    name: str,
    status: str = "completed",
    conclusion: str = "success",
    kind: str = "check_run",
) -> EvidenceItem:
    return EvidenceItem(
        id=fact_id,
        summary=f"{name}: {status}/{conclusion}",
        kind=kind,
        classification="ci",
        profile="verification",
        authority="verification_provider",
        role="verification",
        observed_head_sha="head",
        verification_identity=VerificationIdentity(
            provider="github",
            kind=kind,
            name=" ".join(name.split()).casefold(),
        ),
        verification_status=status,
        verification_conclusion=conclusion,
        sources=(SourceRef(label=name),),
    )


def _verification_relation(fact_id: str, *, ordinal: int = 0) -> ProjectionRelation:
    return _relation(
        f"relation:{fact_id}",
        slot="verification",
        target=fact_id,
        association="current_head",
        ordinal=ordinal,
    )


def _selected(
    candidates: ProjectionCandidateSet,
    *,
    policy: ConvergencePolicy,
) -> tuple[str, ...]:
    result = converge_candidates(
        candidates,
        evidence_catalog=EvidenceCatalog(),
        policy=policy,
    )
    result.validate_consistency(candidates)
    return result.selected_relation_ids()


def test_routing_relation_has_no_embedded_selection_truth() -> None:
    assert "state" not in {item.name for item in fields(ProjectionRelation)}


def test_convergence_isolated_by_focus_and_prefers_explicit_claim() -> None:
    candidates = _candidates(
        _relation(
            "R1-explicit",
            slot="claim",
            target="C1",
            association="explicit_reference",
        ),
        _relation(
            "R1-phrase",
            slot="claim",
            target="C2",
            association="distinctive_phrase",
        ),
        _relation(
            "R2-phrase",
            focus="R2",
            slot="claim",
            target="C3",
            association="distinctive_phrase",
        ),
    )

    assert _selected(
        candidates,
        policy=ConvergencePolicy(max_claims=1),
    ) == ("R1-explicit", "R2-phrase")


def test_distinct_direct_and_claim_bridged_anchors_form_one_set() -> None:
    candidates = _candidates(
        _relation(
            "claim",
            slot="claim",
            target="C1",
            association="explicit_reference",
        ),
        _relation(
            "provided",
            slot="changed_anchor",
            target="E:provided",
            association="provided_association",
        ),
        _relation(
            "exact",
            slot="changed_anchor",
            target="E:exact",
            association="exact_identifier",
        ),
        _relation(
            "bridge",
            slot="changed_anchor",
            target="E:bridge",
            association="claim_bridge",
            bridges=("C1",),
        ),
    )

    assert _selected(
        candidates,
        policy=ConvergencePolicy(),
    ) == ("claim", "provided", "exact", "bridge")


def test_claim_bridge_requires_the_selected_claim() -> None:
    candidates = _candidates(
        _relation(
            "selected-claim",
            slot="claim",
            target="C1",
            association="explicit_reference",
        ),
        _relation(
            "deferred-claim",
            slot="claim",
            target="C2",
            association="distinctive_phrase",
        ),
        _relation(
            "unreachable-anchor",
            slot="changed_anchor",
            target="E:bridge",
            association="claim_bridge",
            bridges=("C2",),
        ),
    )
    result = converge_candidates(
        candidates,
        evidence_catalog=EvidenceCatalog(),
        policy=ConvergencePolicy(max_claims=1),
    )

    assert result.selected_relation_ids() == ("selected-claim",)
    assert any(
        item.slot == "changed_anchor"
        and item.state == "no_association"
        and item.affected_ids == ("E:bridge",)
        for item in result.diagnostics
    )


def test_structural_path_requires_a_selected_changed_anchor() -> None:
    candidates = _candidates(
        _relation(
            "anchor-1",
            slot="changed_anchor",
            target="E:anchor-1",
            association="exact_identifier",
        ),
        _relation(
            "anchor-2",
            slot="changed_anchor",
            target="E:anchor-2",
            association="distinctive_phrase",
        ),
        _relation(
            "path-1",
            slot="structural_path",
            target="E:path-1",
            association="structural_bridge",
            bridges=("E:anchor-1",),
        ),
        _relation(
            "path-2",
            slot="structural_path",
            target="E:path-2",
            association="structural_bridge",
            bridges=("E:anchor-2",),
        ),
    )

    assert _selected(
        candidates,
        policy=ConvergencePolicy(max_direct_anchor_identities=1),
    ) == ("anchor-1", "path-1")


def test_changed_anchor_safety_truncation_is_not_ambiguity() -> None:
    candidates = _candidates(
        *(
            _relation(
                f"anchor-{index}",
                slot="changed_anchor",
                target=f"E:{index}",
                association="exact_identifier",
                ordinal=index,
            )
            for index in range(5)
        )
    )
    result = converge_candidates(
        candidates,
        evidence_catalog=EvidenceCatalog(),
        policy=ConvergencePolicy(
            max_direct_anchor_identities=3,
            max_anchor_identities=3,
            max_candidates_per_slot=2,
        ),
    )

    states = {
        item.state
        for item in result.diagnostics
        if item.slot == "changed_anchor"
    }
    assert result.selected_relation_ids() == ("anchor-0", "anchor-1", "anchor-2")
    assert states == {"budget_truncated"}


def test_changed_anchor_identity_collapses_duplicate_relations() -> None:
    candidates = _candidates(
        _relation(
            "phrase",
            slot="changed_anchor",
            target="E:same",
            association="distinctive_phrase",
            ordinal=0,
        ),
        _relation(
            "exact",
            slot="changed_anchor",
            target="E:same",
            association="exact_identifier",
            ordinal=1,
        ),
        _relation(
            "other-phrase",
            slot="changed_anchor",
            target="E:other",
            association="distinctive_phrase",
            ordinal=2,
        ),
    )

    result = converge_candidates(
        candidates,
        evidence_catalog=EvidenceCatalog(),
    )

    assert result.selected_relation_ids() == ("exact", "other-phrase")
    assert result.groups[0].deferred_relation_ids == ("phrase",)
    assert result.diagnostics == ()


def test_changed_anchor_direct_bridge_and_total_limits_are_independent() -> None:
    candidates = _candidates(
        _relation(
            "claim",
            slot="claim",
            target="C1",
            association="explicit_reference",
        ),
        *(
            _relation(
                f"direct-{index}",
                slot="changed_anchor",
                target=f"E:direct:{index}",
                association="exact_identifier",
                ordinal=index,
            )
            for index in range(3)
        ),
        *(
            _relation(
                f"bridge-{index}",
                slot="changed_anchor",
                target=f"E:bridge:{index}",
                association="claim_bridge",
                bridges=("C1",),
                ordinal=10 + index,
            )
            for index in range(2)
        ),
    )

    result = converge_candidates(
        candidates,
        evidence_catalog=EvidenceCatalog(),
        policy=ConvergencePolicy(
            max_direct_anchor_identities=2,
            max_bridged_anchor_identities=2,
            max_anchor_identities=3,
        ),
    )

    assert result.selected_relation_ids() == (
        "claim",
        "direct-0",
        "direct-1",
        "bridge-0",
    )
    changed_diagnostics = [
        item for item in result.diagnostics if item.slot == "changed_anchor"
    ]
    assert [item.state for item in changed_diagnostics] == ["budget_truncated"]
    assert set(changed_diagnostics[0].affected_ids) == {
        "E:direct:2",
        "E:bridge:1",
    }


def test_changed_anchor_claim_bridge_limit_truncates_independently() -> None:
    candidates = _candidates(
        _relation(
            "claim",
            slot="claim",
            target="C1",
            association="explicit_reference",
        ),
        _relation(
            "direct",
            slot="changed_anchor",
            target="E:direct",
            association="exact_identifier",
        ),
        *(
            _relation(
                f"bridge-{index}",
                slot="changed_anchor",
                target=f"E:bridge:{index}",
                association="claim_bridge",
                bridges=("C1",),
                ordinal=index + 1,
            )
            for index in range(3)
        ),
    )

    result = converge_candidates(
        candidates,
        evidence_catalog=EvidenceCatalog(),
        policy=ConvergencePolicy(
            max_direct_anchor_identities=5,
            max_bridged_anchor_identities=1,
            max_anchor_identities=10,
        ),
    )

    assert result.selected_relation_ids() == ("claim", "direct", "bridge-0")
    changed_diagnostics = [
        item for item in result.diagnostics if item.slot == "changed_anchor"
    ]
    assert [item.state for item in changed_diagnostics] == ["budget_truncated"]
    assert changed_diagnostics[0].affected_ids == (
        "E:bridge:1",
        "E:bridge:2",
    )


def test_distinct_current_head_checks_form_one_non_competing_set() -> None:
    facts = (
        _verification("E:test", name="test"),
        _verification("E:review", name="review"),
    )
    candidates = _candidates(
        _verification_relation("E:test"),
        _verification_relation("E:review", ordinal=1),
    )

    result = converge_candidates(
        candidates,
        evidence_catalog=EvidenceCatalog(items=facts),
    )

    assert result.selected_relation_ids() == (
        "relation:E:review",
        "relation:E:test",
    )
    assert not [
        item
        for item in result.diagnostics
        if item.slot == "verification" and item.state == "ambiguous"
    ]


def test_equivalent_verification_duplicates_collapse_by_identity() -> None:
    facts = (
        _verification("E:first", name=" Test "),
        _verification("E:duplicate", name="test"),
    )
    candidates = _candidates(
        _verification_relation("E:first"),
        _verification_relation("E:duplicate", ordinal=1),
    )

    result = converge_candidates(
        candidates,
        evidence_catalog=EvidenceCatalog(items=facts),
    )

    assert result.selected_relation_ids() == ("relation:E:first",)
    assert result.groups[0].deferred_relation_ids == ("relation:E:duplicate",)
    assert result.diagnostics == ()


def test_conflicting_completed_outcomes_remain_visible_for_one_identity() -> None:
    facts = (
        _verification("E:success", name="test", conclusion="success"),
        _verification("E:failure", name="test", conclusion="failure"),
    )
    candidates = _candidates(
        _verification_relation("E:success"),
        _verification_relation("E:failure", ordinal=1),
    )

    result = converge_candidates(
        candidates,
        evidence_catalog=EvidenceCatalog(items=facts),
    )

    assert set(result.selected_relation_ids()) == {
        "relation:E:success",
        "relation:E:failure",
    }
    assert [
        item.state
        for item in result.diagnostics
        if item.slot == "verification"
    ] == ["conflicting_facts"]


def test_verification_safety_limit_prioritizes_failure_then_pending() -> None:
    facts = (
        _verification("E:success", name="success", conclusion="success"),
        _verification(
            "E:pending",
            name="pending",
            status="in_progress",
            conclusion="",
        ),
        _verification("E:failure", name="failure", conclusion="failure"),
    )
    candidates = _candidates(
        *(
            _verification_relation(fact.id, ordinal=index)
            for index, fact in enumerate(facts)
        )
    )

    result = converge_candidates(
        candidates,
        evidence_catalog=EvidenceCatalog(items=facts),
        policy=ConvergencePolicy(max_verification_identities=2),
    )

    assert result.selected_relation_ids() == (
        "relation:E:failure",
        "relation:E:pending",
    )
    assert [
        item.state
        for item in result.diagnostics
        if item.slot == "verification"
    ] == ["budget_truncated"]
