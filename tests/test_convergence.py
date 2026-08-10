from __future__ import annotations

from dataclasses import fields

from repodelta.convergence.core import ConvergencePolicy, converge_candidates
from repodelta.model.contracts import (
    ConvergenceGroup,
    EvidenceCatalog,
    EvidenceItem,
    ProjectionCandidateGroup,
    ProjectionCandidateSet,
    ProjectionRelation,
    SourceRef,
    VerificationIdentity,
    canonical_verification_name,
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
            name=canonical_verification_name(name),
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


def _path(
    fact_id: str,
    *,
    depth: int = 1,
    steps: tuple[tuple[str, str], ...] = (),
) -> EvidenceItem:
    return EvidenceItem(
        id=fact_id,
        summary=f"Structural path at depth {depth}",
        kind="structural_path",
        classification="runtime",
        profile="structural_path",
        authority="structural_provider",
        role="structural_path",
        metadata={
            "depth": depth,
            "steps": tuple(
                {
                    "source_evidence_id": source,
                    "target_evidence_id": target,
                }
                for source, target in steps
            ),
        },
        sources=(SourceRef(label=fact_id),),
    )


def _symbol(fact_id: str, review_symbol_id: str) -> EvidenceItem:
    return EvidenceItem(
        id=fact_id,
        summary=f"Changed function: {review_symbol_id}",
        kind="symbol",
        classification="code",
        profile="production",
        authority="structural_provider",
        role="revision_fact",
        changed=True,
        metadata={"review_symbol_id": review_symbol_id},
    )


def _selected(
    candidates: ProjectionCandidateSet,
    *,
    policy: ConvergencePolicy,
    evidence: tuple[EvidenceItem, ...] = (),
) -> tuple[str, ...]:
    catalog = EvidenceCatalog(items=evidence)
    result = converge_candidates(
        candidates,
        evidence_catalog=catalog,
        policy=policy,
    )
    result.validate_consistency(candidates, catalog)
    return result.selected_relation_ids()


def test_routing_relation_has_no_embedded_selection_truth() -> None:
    assert "state" not in {item.name for item in fields(ProjectionRelation)}
    group_fields = {item.name for item in fields(ConvergenceGroup)}
    assert "structural_closure" in group_fields
    assert "structural_support" not in group_fields


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
        evidence=(_path("E:path-1"), _path("E:path-2")),
    ) == ("anchor-1",)


def test_structural_paths_form_a_non_competing_canonical_set() -> None:
    candidates = _candidates(
        _relation(
            "anchor",
            slot="changed_anchor",
            target="E:anchor",
            association="exact_identifier",
        ),
        *(
            _relation(
                f"path-{index}",
                slot="structural_path",
                target=f"E:path-{index}",
                association="structural_bridge",
                bridges=("E:anchor",),
                ordinal=index,
            )
            for index in range(4)
        ),
    )
    facts = tuple(_path(f"E:path-{index}", depth=index + 1) for index in range(4))

    result = converge_candidates(
        candidates,
        evidence_catalog=EvidenceCatalog(items=facts),
        policy=ConvergencePolicy(max_candidates_per_slot=1),
    )

    assert result.selected_relation_ids() == ("anchor",)
    assert not [
        item
        for item in result.diagnostics
        if item.slot == "structural_path"
    ]


def test_structural_path_identity_collapses_duplicate_relations() -> None:
    candidates = _candidates(
        _relation(
            "anchor",
            slot="changed_anchor",
            target="E:anchor",
            association="exact_identifier",
        ),
        _relation(
            "path-first",
            slot="structural_path",
            target="E:path",
            association="structural_bridge",
            bridges=("E:anchor",),
        ),
        _relation(
            "path-duplicate",
            slot="structural_path",
            target="E:path",
            association="structural_bridge",
            bridges=("E:anchor",),
            ordinal=1,
        ),
    )

    result = converge_candidates(
        candidates,
        evidence_catalog=EvidenceCatalog(items=(_path("E:path"),)),
    )

    assert result.selected_relation_ids() == ("anchor",)
    assert result.groups[0].deferred_relation_ids == (
        "path-first",
        "path-duplicate",
    )
    assert result.diagnostics == ()


def test_structural_path_safety_prefers_shorter_paths_without_ambiguity() -> None:
    candidates = _candidates(
        _relation(
            "anchor",
            slot="changed_anchor",
            target="E:anchor",
            association="exact_identifier",
        ),
        _relation(
            "long",
            slot="structural_path",
            target="E:long",
            association="structural_bridge",
            bridges=("E:anchor",),
        ),
        _relation(
            "short",
            slot="structural_path",
            target="E:short",
            association="structural_bridge",
            bridges=("E:anchor",),
            ordinal=1,
        ),
        _relation(
            "runtime",
            slot="runtime_context",
            target="E:runtime",
            association="structural_bridge",
            bridges=("E:long", "E:short"),
        ),
    )

    result = converge_candidates(
        candidates,
        evidence_catalog=EvidenceCatalog(
            items=(_path("E:long", depth=3), _path("E:short", depth=1))
        ),
        policy=ConvergencePolicy(
            max_paths_per_anchor=1,
            max_path_identities=1,
        ),
    )

    assert result.selected_relation_ids() == ("anchor", "short", "runtime")
    assert not [
        item
        for item in result.diagnostics
        if item.slot == "structural_path"
    ]


def test_contexts_form_sets_and_deferred_paths_are_explicit() -> None:
    candidates = _candidates(
        _relation(
            "anchor",
            slot="changed_anchor",
            target="E:anchor",
            association="exact_identifier",
        ),
        _relation(
            "selected-path",
            slot="structural_path",
            target="E:path:selected",
            association="structural_bridge",
            bridges=("E:anchor",),
        ),
        _relation(
            "deferred-path",
            slot="structural_path",
            target="E:path:deferred",
            association="structural_bridge",
            bridges=("E:anchor",),
            ordinal=1,
        ),
        _relation(
            "runtime-selected",
            slot="runtime_context",
            target="E:runtime:selected",
            association="structural_bridge",
            bridges=("E:path:selected",),
        ),
        _relation(
            "runtime-deferred",
            slot="runtime_context",
            target="E:runtime:deferred",
            association="structural_bridge",
            bridges=("E:path:deferred",),
            ordinal=1,
        ),
        _relation(
            "test-selected",
            slot="test_context",
            target="E:test:selected",
            association="structural_bridge",
            bridges=("E:path:selected",),
        ),
    )

    result = converge_candidates(
        candidates,
        evidence_catalog=EvidenceCatalog(
            items=(
                _path("E:path:selected", depth=1),
                _path("E:path:deferred", depth=2),
            )
        ),
        policy=ConvergencePolicy(
            max_paths_per_anchor=1,
            max_path_identities=1,
        ),
    )

    assert result.selected_relation_ids() == (
        "anchor",
        "selected-path",
        "runtime-selected",
        "test-selected",
    )
    runtime_diagnostics = [
        item
        for item in result.diagnostics
        if item.slot == "runtime_context"
    ]
    assert [item.state for item in runtime_diagnostics] == [
        "upstream_deferred"
    ]
    assert "runtime-deferred" in result.groups[0].deferred_relation_ids


def test_terminal_path_replaces_unrelated_shallow_path() -> None:
    candidates = _candidates(
        _relation(
            "anchor",
            slot="changed_anchor",
            target="E:anchor",
            association="exact_identifier",
        ),
        _relation(
            "selected-path",
            slot="structural_path",
            target="E:path:selected",
            association="structural_bridge",
            bridges=("E:anchor",),
        ),
        _relation(
            "deferred-path",
            slot="structural_path",
            target="E:path:deferred",
            association="structural_bridge",
            bridges=("E:anchor",),
            ordinal=1,
        ),
        _relation(
            "runtime-deferred",
            slot="runtime_context",
            target="E:runtime:deferred",
            association="structural_bridge",
            bridges=("E:path:deferred",),
        ),
    )

    result = converge_candidates(
        candidates,
        evidence_catalog=EvidenceCatalog(
            items=(
                _path("E:path:selected", depth=1),
                _path("E:path:deferred", depth=2),
            )
        ),
        policy=ConvergencePolicy(
            max_paths_per_anchor=1,
            max_path_identities=1,
        ),
    )

    assert result.selected_relation_ids() == (
        "anchor",
        "deferred-path",
        "runtime-deferred",
    )
    assert not [
        item
        for item in result.diagnostics
        if item.slot == "runtime_context"
    ]


def test_equivalent_shortest_terminal_paths_converge_to_one_support() -> None:
    candidates = _candidates(
        _relation(
            "anchor",
            slot="changed_anchor",
            target="E:anchor",
            association="exact_identifier",
        ),
        _relation(
            "path-a",
            slot="structural_path",
            target="E:path:a",
            association="structural_bridge",
            bridges=("E:anchor",),
        ),
        _relation(
            "path-b",
            slot="structural_path",
            target="E:path:b",
            association="structural_bridge",
            bridges=("E:anchor",),
            ordinal=1,
        ),
        _relation(
            "runtime",
            slot="runtime_context",
            target="E:runtime",
            association="structural_bridge",
            bridges=("E:path:a", "E:path:b"),
        ),
    )

    result = converge_candidates(
        candidates,
        evidence_catalog=EvidenceCatalog(
            items=(
                _path("E:path:a", depth=2),
                _path("E:path:b", depth=2),
            )
        ),
        policy=ConvergencePolicy(
            max_paths_per_anchor=2,
            max_path_identities=2,
        ),
    )

    assert result.selected_relation_ids() == (
        "anchor",
        "path-a",
        "runtime",
    )
    assert result.groups[0].structural_closure.path_relation_ids == (
        "path-a",
    )


def test_changed_anchor_connection_is_a_backbone_closure_obligation() -> None:
    candidates = _candidates(
        _relation(
            "anchor-a",
            slot="changed_anchor",
            target="E:anchor:a",
            association="exact_identifier",
        ),
        _relation(
            "anchor-b",
            slot="changed_anchor",
            target="E:anchor:b",
            association="exact_identifier",
            ordinal=1,
        ),
        _relation(
            "backbone-path",
            slot="structural_path",
            target="E:path:backbone",
            association="structural_bridge",
            bridges=("E:anchor:a",),
        ),
    )

    result = converge_candidates(
        candidates,
        evidence_catalog=EvidenceCatalog(
            items=(
                _symbol("E:anchor:a", "S:a"),
                _symbol("E:anchor:b", "S:b"),
                _path(
                    "E:path:backbone",
                    steps=(("E:anchor:a", "E:anchor:b"),),
                ),
            )
        ),
        policy=ConvergencePolicy(
            max_paths_per_anchor=1,
            max_path_identities=1,
        ),
    )

    assert result.selected_relation_ids() == (
        "anchor-a",
        "anchor-b",
        "backbone-path",
    )
    assert result.groups[0].structural_closure.path_relation_ids == (
        "backbone-path",
    )


def test_distinct_terminals_precede_redundant_shortest_support() -> None:
    candidates = _candidates(
        _relation(
            "anchor",
            slot="changed_anchor",
            target="E:anchor",
            association="exact_identifier",
        ),
        _relation(
            "runtime-path",
            slot="structural_path",
            target="E:path:runtime",
            association="structural_bridge",
            bridges=("E:anchor",),
        ),
        _relation(
            "runtime-alternative",
            slot="structural_path",
            target="E:path:runtime-alt",
            association="structural_bridge",
            bridges=("E:anchor",),
            ordinal=1,
        ),
        _relation(
            "test-path",
            slot="structural_path",
            target="E:path:test",
            association="structural_bridge",
            bridges=("E:anchor",),
            ordinal=2,
        ),
        _relation(
            "runtime",
            slot="runtime_context",
            target="E:runtime",
            association="structural_bridge",
            bridges=("E:path:runtime", "E:path:runtime-alt"),
        ),
        _relation(
            "test",
            slot="test_context",
            target="E:test",
            association="structural_bridge",
            bridges=("E:path:test",),
            ordinal=1,
        ),
    )

    result = converge_candidates(
        candidates,
        evidence_catalog=EvidenceCatalog(
            items=(
                _path("E:path:runtime", depth=1),
                _path("E:path:runtime-alt", depth=1),
                _path("E:path:test", depth=2),
            )
        ),
        policy=ConvergencePolicy(
            max_paths_per_anchor=2,
            max_path_identities=2,
        ),
    )

    assert result.selected_relation_ids() == (
        "anchor",
        "runtime-path",
        "test-path",
        "runtime",
        "test",
    )
    assert "runtime-alternative" in result.groups[0].deferred_relation_ids


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
