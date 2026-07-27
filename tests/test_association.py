from prismcode.facts.lexical import association_signature
from prismcode.model.contracts import (
    EvidenceCatalog,
    EvidenceItem,
    Requirement,
    ReviewStatement,
)
from prismcode.routing.association import (
    distinctive_text_terms,
    evidence_reasons,
    statement_reasons,
)
from prismcode.routing.candidates import build_projection_candidates


def _focus(identifier: str, text: str) -> Requirement:
    return Requirement(id=identifier, text=text)


def _claim(identifier: str, text: str) -> ReviewStatement:
    return ReviewStatement(
        id=identifier,
        text=text,
        role="claim",
        purpose="implementation",
        authority="pr_description",
    )


def test_ubiquitous_phrase_does_not_associate_without_focus_meaning() -> None:
    focuses = (
        _focus("R1", "Project canonical structural graph nodes"),
        _focus("R2", "Project canonical structural graph edges"),
        _focus("R3", "Project canonical structural graph overlays"),
    )
    vocabulary = distinctive_text_terms(
        tuple((item.id, item.text) for item in focuses)
    )

    assert not statement_reasons(
        focuses[0],
        _claim("C1", "Project the canonical structural graph"),
        distinctive_terms=vocabulary["R1"],
    )
    reason = statement_reasons(
        focuses[0],
        _claim("C2", "Project canonical structural graph nodes once"),
        distinctive_terms=vocabulary["R1"],
    )[0]
    assert reason.kind == "distinctive_phrase"
    assert reason.matched_terms == ("nodes",)


def test_identical_focus_meanings_share_the_same_distinctive_terms() -> None:
    focuses = (
        _focus("R1", "Render focus overlay nodes"),
        _focus("R2", "Render focus overlay nodes"),
    )
    vocabulary = distinctive_text_terms(
        tuple((item.id, item.text) for item in focuses)
    )

    assert vocabulary["R1"] == vocabulary["R2"]
    assert statement_reasons(
        focuses[0],
        _claim("C1", "Render focus overlay nodes from the graph"),
        distinctive_terms=vocabulary["R1"],
    )
    assert statement_reasons(
        focuses[1],
        _claim("C1", "Render focus overlay nodes from the graph"),
        distinctive_terms=vocabulary["R2"],
    )


def test_exact_identifier_does_not_depend_on_phrase_distinctiveness() -> None:
    focus = _focus("R1", "Call build_focus_overlay")

    reason = evidence_reasons(
        focus,
        association_signature("Changed function: build_focus_overlay"),
        distinctive_terms=frozenset(),
    )[0]

    assert reason.kind == "exact_identifier"
    assert "buildfocusoverlay" in reason.matched_terms


def test_claim_bridge_requires_claim_and_anchor_distinctiveness() -> None:
    focuses = (
        _focus("R1", "Preserve nodes membership projection"),
        _focus("R2", "Preserve edges membership projection"),
    )
    claims = (
        _claim(
            "C1",
            "Build focus overlay nodes and preserve membership projection",
        ),
        _claim(
            "C2",
            "Build focus overlay edges and preserve membership projection",
        ),
    )

    def anchor(identifier: str, text: str) -> EvidenceItem:
        return EvidenceItem(
            id=identifier,
            summary=text,
            kind="change_relation",
            classification="code",
            profile="production",
            authority="github_diff",
            revision_side="head",
            operation="modified",
            role="changed_anchor",
            changed=True,
            head_signature=association_signature(text),
        )

    candidates = build_projection_candidates(
        requirements=focuses,
        claims=claims,
        evidence_catalog=EvidenceCatalog(
            items=(
                anchor("E:nodes", "Changed focus overlay nodes builder"),
                anchor("E:edges", "Changed focus overlay edges builder"),
                anchor("E:generic", "Changed focus overlay builder"),
            )
        ),
        structural_graph=None,
        head_sha=None,
    )
    anchors = {
        (item.focus_statement_id, item.target_id, item.association)
        for item in candidates.relations
        if item.slot == "changed_anchor"
    }

    assert anchors == {
        ("R1", "E:nodes", "claim_bridge"),
        ("R2", "E:edges", "claim_bridge"),
    }
    bridge_terms = {
        (item.focus_statement_id, item.target_id): item.reasons[0].matched_terms
        for item in candidates.relations
        if item.slot == "changed_anchor"
    }
    assert bridge_terms == {
        ("R1", "E:nodes"): ("nodes",),
        ("R2", "E:edges"): ("edges",),
    }


def test_phrase_relevance_must_discriminate_the_changed_anchor_corpus() -> None:
    focus = _focus("R1", "Render canonical structural graph nodes")

    def anchor(identifier: str, text: str) -> EvidenceItem:
        return EvidenceItem(
            id=identifier,
            summary=text,
            kind="change_relation",
            classification="code",
            profile="production",
            authority="github_diff",
            revision_side="head",
            operation="modified",
            role="changed_anchor",
            changed=True,
            head_signature=association_signature(text),
        )

    candidates = build_projection_candidates(
        requirements=(focus,),
        claims=(),
        evidence_catalog=EvidenceCatalog(
            items=(
                anchor("E:nodes", "Render canonical structural graph nodes"),
                anchor("E:edges", "Render canonical structural graph edges"),
                anchor("E:overlay", "Render canonical structural graph overlay"),
            )
        ),
        structural_graph=None,
        head_sha=None,
    )

    anchors = tuple(
        (item.target_id, item.association, item.reasons[0].matched_terms)
        for item in candidates.relations
        if item.slot == "changed_anchor"
    )

    assert anchors == (("E:nodes", "distinctive_phrase", ("nodes",)),)


def test_multiple_identical_relevant_anchor_meanings_remain_a_set() -> None:
    focus = _focus("R1", "Render canonical structural graph nodes")
    anchors = tuple(
        EvidenceItem(
            id=f"E:nodes:{index}",
            summary=f"Render canonical structural graph nodes in layer {index}",
            kind="change_relation",
            classification="code",
            profile="production",
            authority="github_diff",
            revision_side="head",
            operation="modified",
            role="changed_anchor",
            changed=True,
            head_signature=association_signature(
                "Render canonical structural graph nodes"
            ),
        )
        for index in range(2)
    )

    candidates = build_projection_candidates(
        requirements=(focus,),
        claims=(),
        evidence_catalog=EvidenceCatalog(items=anchors),
        structural_graph=None,
        head_sha=None,
    )

    assert {
        item.target_id
        for item in candidates.relations
        if item.slot == "changed_anchor"
    } == {"E:nodes:0", "E:nodes:1"}


def test_phrase_cohorts_do_not_suppress_other_fact_profiles() -> None:
    focus = _focus("R1", "Render canonical structural graph nodes")

    def anchor(
        identifier: str,
        text: str,
        *,
        profile: str,
    ) -> EvidenceItem:
        return EvidenceItem(
            id=identifier,
            summary=text,
            kind="change_relation",
            classification="document" if profile == "document" else "code",
            profile=profile,
            authority="github_diff",
            revision_side="head",
            operation="modified",
            role="changed_anchor",
            changed=True,
            head_signature=association_signature(text),
        )

    candidates = build_projection_candidates(
        requirements=(focus,),
        claims=(),
        evidence_catalog=EvidenceCatalog(
            items=(
                anchor(
                    "E:production",
                    "Render canonical structural graph",
                    profile="production",
                ),
                anchor(
                    "E:document:nodes",
                    "Render canonical structural graph nodes",
                    profile="document",
                ),
                anchor(
                    "E:document:edges",
                    "Render canonical structural graph edges",
                    profile="document",
                ),
            )
        ),
        structural_graph=None,
        head_sha=None,
    )

    assert {
        item.target_id
        for item in candidates.relations
        if item.slot == "changed_anchor"
    } == {"E:production", "E:document:nodes"}
