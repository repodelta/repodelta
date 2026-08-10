from __future__ import annotations

from prismcode.pipeline import DeterministicAnalyzer
from prismcode.model.contracts import (
    AnalysisInput,
    ChangedFile,
    Requirement,
    ReviewSourcePacket,
    SourceRef,
    SourceRecord,
)
from prismcode.semantics.criteria import extract_review_semantics
from prismcode.semantics.criteria import parse_markdown_semantics
from prismcode.presentation.html import render_html


def _packet(
    *,
    title: str = "Add structural graph foundation",
    pr_body: str = "",
    issue_body: str | None = None,
    changed_files: tuple[ChangedFile, ...] = (),
) -> ReviewSourcePacket:
    records = [
        SourceRecord(
            id="pr:8",
            kind="pull_request",
            repository="acme/widget",
            url="https://github.com/acme/widget/pull/8",
            title=title,
            body=pr_body,
        )
    ]
    if issue_body is not None:
        records.append(
            SourceRecord(
                id="issue:7",
                kind="linked_issue",
                repository="acme/widget",
                url="https://github.com/acme/widget/issues/7",
                title="Structural review",
                body=issue_body,
            )
        )
    return ReviewSourcePacket(
        repository="acme/widget",
        pull_request=8,
        title=title,
        source_records=tuple(records),
        changed_files=changed_files,
        source_url="https://github.com/acme/widget/pull/8",
    ).with_revision()


def test_issue_obligations_override_pr_authored_acceptance_criteria() -> None:
    semantics = extract_review_semantics(
        issue_body=(
            "## Goals\n"
            "- Make structural evidence available.\n\n"
            "## Acceptance criteria\n"
            "- Map exact changed lines.\n"
            "- Do not infer passing CI.\n"
        ),
        issue_source=SourceRef(
            label="linked issue",
            url="https://github.com/acme/widget/issues/7",
        ),
        pr_body=(
            "Expose structural facts to reviewers.\n\n"
            "## Acceptance criteria\n"
            "- Treat every changed file as implemented.\n\n"
            "## Summary\n"
            "Adds a Codegraph provider.\n"
        ),
        pr_source=_pr_source(),
        pr_title="Add graph support",
    )

    assert [item.text for item in semantics.obligations] == [
        "Map exact changed lines.",
        "Do not infer passing CI.",
    ]
    assert all(item.authority == "issue" for item in semantics.obligations)
    assert [item.id for item in semantics.obligations] == ["R1", "G1"]
    assert semantics.obligations[0].sources[0].label == (
        "linked issue · Acceptance criteria"
    )
    assert semantics.obligations[0].sources[0].line_start == 5
    assert [item.text for item in semantics.claims] == [
        "Adds a Codegraph provider."
    ]


def _pr_source():
    return SourceRef(
        label="pull request description",
        url="https://github.com/acme/widget/pull/8",
    )


def test_semantic_items_follow_explicit_human_and_ai_list_structure() -> None:
    parsed = parse_markdown_semantics(
        "## Goals\n"
        "This paragraph wraps\n"
        "onto another source line; it remains one objective.\n\n"
        "1) First explicit goal\n"
        "   with a continuation line.\n"
        "2、Second explicit goal\n"
        "• Third explicit goal\n"
        "AC4: Fourth explicit goal\n\n"
        "## Summary\n"
        "1) Add the adapter; 2) connect it to runtime; 3) preserve fallback.\n"
        "Normal prose; with a semicolon; remains one claim.\n"
    )

    assert [(item.role, item.text) for item in parsed.items] == [
        (
            "objective",
            "This paragraph wraps onto another source line; "
            "it remains one objective.",
        ),
        ("objective", "First explicit goal with a continuation line."),
        ("objective", "Second explicit goal"),
        ("objective", "Third explicit goal"),
        ("objective", "Fourth explicit goal"),
        ("claim", "Add the adapter"),
        ("claim", "connect it to runtime"),
        ("claim", "preserve fallback. Normal prose; with a semicolon; remains one claim."),
    ]


def test_nested_lists_flatten_leaves_with_parent_context() -> None:
    parsed = parse_markdown_semantics(
        "## Acceptance criteria\n"
        "- Structural mapping\n"
        "  - resolves exact changed symbols\n"
        "  - preserves lexical fallback\n"
        "- [ ] CI reports the current head\n"
    )

    assert [item.text for item in parsed.items] == [
        "Structural mapping: resolves exact changed symbols",
        "Structural mapping: preserves lexical fallback",
        "CI reports the current head",
    ]


def test_authored_statement_labels_do_not_enter_canonical_text() -> None:
    parsed = parse_markdown_semantics(
        "## Goals\n"
        "- O4: Preserve source authority.\n\n"
        "## Scope\n"
        "- S2: Normalize only explicit labels.\n\n"
        "## Acceptance criteria\n"
        "- R7: Assign canonical requirement identities.\n\n"
        "## Scope guardrails\n"
        "- G3: Do not infer labels from prose.\n\n"
        "## Verification\n"
        "- VC9: Semantic tests pass.\n"
    )

    assert [item.text for item in parsed.items] == [
        "Preserve source authority.",
        "Normalize only explicit labels.",
        "Assign canonical requirement identities.",
        "Do not infer labels from prose.",
        "Semantic tests pass.",
    ]
    claims = parse_markdown_semantics(
        "## Summary\n"
        "- R1: Connect the canonical parser.\n"
    )
    assert [item.text for item in claims.items] == [
        "R1: Connect the canonical parser."
    ]


def test_code_fences_do_not_create_semantic_items() -> None:
    parsed = parse_markdown_semantics(
        "## Implementation\n"
        "- Add the adapter.\n"
        "```markdown\n"
        "- This is an example, not a claim.\n"
        "```\n"
        "- Wire the adapter into runtime.\n"
    )

    assert [item.text for item in parsed.items] == [
        "Add the adapter.",
        "Wire the adapter into runtime.",
    ]


def test_exact_implementation_aliases_share_one_typed_claim_path() -> None:
    parsed = parse_markdown_semantics(
        "## Semantic atom\n"
        "- Replace the former relation parser.\n\n"
        "## Implementation details\n"
        "Wire canonical relations into evidence.\n\n"
        "## Technical approach\n"
        "- Preserve stable source identities.\n\n"
        "## Semantic atom rationale\n"
        "- This unknown prose heading is not a claim.\n"
    )

    assert [
        (item.role, item.purpose, item.section, item.text)
        for item in parsed.items
    ] == [
        (
            "claim",
            "implementation",
            "Semantic atom",
            "Replace the former relation parser.",
        ),
        (
            "claim",
            "implementation",
            "Implementation details",
            "Wire canonical relations into evidence.",
        ),
        (
            "claim",
            "implementation",
            "Technical approach",
            "Preserve stable source identities.",
        ),
    ]


def test_pr57_semantic_atom_is_preserved_as_typed_implementation_claims() -> None:
    packet = _packet(
        pr_body=(
            "Closes #56.\n\n"
            "## Semantic atom\n\n"
            "This replaces the former untyped representation with one "
            "canonical relation pipeline:\n\n"
            "`unified patch → ChangeRelation[] → "
            "EvidenceCatalog.change_relations → relation-referenced changed "
            "evidence`\n\n"
            "- the patch parser alone classifies contiguous changes as "
            "added, removed, or replaced;\n"
            "- exact symbols and uncovered diff facts reference stable "
            "relation IDs instead of inferring operation from whole hunks;\n"
            "- multiple relations may jointly support one changed symbol "
            "without competing or overwriting its operation;\n"
            "- the structural-path pass no longer performs a second write "
            "of changed symbols;\n"
            "- legacy models, IDs, metadata, routing kinds, fixtures, and "
            "terminology are removed.\n\n"
            "## Boundaries\n\n"
            "This PR does not introduce a base Codegraph index, rename "
            "inference, change-graph presentation, LLM judgment, or "
            "acceptance conclusions.\n\n"
            "## Verification\n\n"
            "- 122 passed\n"
            "- deterministic evaluation: PASS\n"
            "- git diff --check\n"
            "- repository audit finds no legacy production references\n"
        )
    )

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))

    implementation = tuple(
        item for item in brief.claims if item.purpose == "implementation"
    )
    assert [item.id for item in implementation] == [
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
        "C7",
    ]
    assert all(
        item.sources[0].label
        == "pull request description · Semantic atom"
        for item in implementation
    )
    assert [item.sources[0].line_start for item in implementation] == [
        5,
        7,
        9,
        10,
        11,
        12,
        13,
    ]
    assert implementation[1].text.startswith("unified patch → ChangeRelation[]")
    assert "patch parser alone classifies" in implementation[2].text
    assert "exact symbols and uncovered diff facts" in implementation[3].text
    assert "multiple relations may jointly support" in implementation[4].text
    assert "no longer performs a second write" in implementation[5].text
    assert "legacy models" in implementation[6].text
    assert [
        (item.id, item.purpose)
        for item in brief.claims[len(implementation) :]
    ] == [
        ("C8", "boundary"),
        ("VC1", "verification"),
        ("VC2", "verification"),
        ("VC3", "verification"),
        ("VC4", "verification"),
    ]


def test_pr_acceptance_criteria_are_provisional_without_linked_issue() -> None:
    packet = _packet(
        pr_body=(
            "Add structure-aware review support.\n\n"
            "## Acceptance criteria\n"
            "- Map changed hunks to exact symbols.\n"
            "- Missing indexes must not fail the report.\n\n"
            "## Goals\n"
            "- Preserve deterministic review behavior.\n\n"
            "## Implementation\n"
            "Introduces a read-only provider boundary.\n"
        )
    )

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))

    assert [item.id for item in brief.requirements] == ["R1", "R2"]
    assert all(
        item.authority == "pr_description"
        for item in brief.requirements
    )
    assert brief.requirements[0].sources[0].label == (
        "pull request description · Acceptance criteria"
    )
    assert [item.id for item in brief.objectives] == ["O1"]
    assert [item.id for item in brief.claims] == ["C1"]
    assert brief.intent.text == "Add structure-aware review support."
    html = render_html(brief)
    assert "PR #8 · Acceptance criteria" in html
    assert "pr description" not in html
    assert 'data-verification-subject="R1"' in html
    assert "<h2>Verification</h2>" in html
    assert '<h2 class="brief-goals-heading" id="brief-goals-heading">Goals</h2>' in html
    assert "Goals · 1 statement" not in html
    assert html.index("brief-goals-heading") < html.index("<h2>Verification</h2>")
    assert "Preserve deterministic review behavior." in html
    assert "PR introduction · 1 statement" in html
    assert "Introduces a read-only provider boundary." in html


def test_linked_issue_goals_replace_pr_introduction_in_brief_header() -> None:
    packet = _packet(
        pr_body="Closes #7\n",
        issue_body=(
            "## Goals\n"
            "- Preserve every directly changed anchor.\n"
            "- Keep repository-reachable context bounded.\n"
        ),
    )

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    html = render_html(brief)

    assert html.count('id="brief-goals-heading"') == 1
    assert "Preserve every directly changed anchor." in html
    assert "Keep repository-reachable context bounded." in html
    assert '<div class="intent">Closes #7</div>' not in html
    assert "PR introduction · 1 statement" in html
    assert html.index("Preserve every directly changed anchor.") < html.index(
        "PR introduction · 1 statement"
    )


def test_pr_introduction_remains_primary_when_no_goal_exists() -> None:
    packet = _packet(pr_body="Explain the bounded review change.\n")

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    html = render_html(brief)

    assert (
        '<div class="intent">Explain the bounded review change.</div>' in html
    )
    assert 'id="brief-goals-heading"' not in html
    assert "PR introduction · 1 statement" not in html


def test_guardrail_and_verification_aliases_preserve_source_authority() -> None:
    packet = _packet(
        issue_body=(
            "## Scope guardrails\n"
            "- G1: No parallel semantic parser.\n\n"
            "## Constraints\n"
            "- G2: Do not infer acceptance.\n\n"
            "## Regression coverage\n"
            "- V1: Cover source-aware guardrail extraction.\n\n"
            "## Validation results\n"
            "- V2: Confirm every statement retains its source line.\n\n"
            "## Guardrail discussion for maintainers\n"
            "- This near-match prose heading is not a guardrail.\n"
        ),
        pr_body=(
            "## Safety boundaries\n"
            "- No renderer fallback is introduced.\n\n"
            "## Test evidence\n"
            "- Semantic authority tests pass.\n\n"
            "## Regression coverage notes for maintainers\n"
            "- This near-match prose heading is not verification evidence.\n"
        ),
    )

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))

    assert [
        (item.id, item.authority, item.text, item.sources[0].label)
        for item in brief.guardrails
    ] == [
        (
            "G1",
            "issue",
            "No parallel semantic parser.",
            "linked issue · Scope guardrails",
        ),
        (
            "G2",
            "issue",
            "Do not infer acceptance.",
            "linked issue · Constraints",
        ),
    ]
    assert [
        (item.id, item.authority, item.text, item.sources[0].label)
        for item in brief.verification_expectations
    ] == [
        (
            "V1",
            "issue",
            "Cover source-aware guardrail extraction.",
            "linked issue · Regression coverage",
        ),
        (
            "V2",
            "issue",
            "Confirm every statement retains its source line.",
            "linked issue · Validation results",
        ),
    ]
    assert [
        (item.id, item.purpose, item.authority, item.text, item.sources[0].label)
        for item in brief.claims
    ] == [
        (
            "C1",
            "boundary",
            "pr_description",
            "No renderer fallback is introduced.",
            "pull request description · Safety boundaries",
        ),
        (
            "VC1",
            "verification",
            "pr_description",
            "Semantic authority tests pass.",
            "pull request description · Test evidence",
        ),
    ]
    assert all(
        item.sources[0].line_start is not None
        for item in (
            *brief.guardrails,
            *brief.verification_expectations,
            *brief.claims,
        )
    )


def test_issue_acceptance_is_primary_but_pr_claims_remain_context() -> None:
    packet = _packet(
        issue_body=(
            "## Acceptance criteria\n"
            "- Map changed lines to exact symbols.\n"
        ),
        pr_body=(
            "Wire structural mapping into the CLI.\n\n"
            "## Acceptance criteria\n"
            "- Use every changed file as evidence.\n\n"
            "## Summary\n"
            "- Adds Codegraph index diagnostics.\n"
        ),
    )

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))

    assert [item.text for item in brief.requirements] == [
        "Map changed lines to exact symbols."
    ]
    assert brief.requirements[0].authority == "issue"
    assert [item.text for item in brief.claims] == [
        "Adds Codegraph index diagnostics."
    ]
    assert "Use every changed file as evidence." not in {
        item.text for item in brief.requirements
    }


def test_summary_and_title_do_not_become_requirements() -> None:
    packet = _packet(
        pr_body=(
            "Expose structural facts to the report.\n\n"
            "## Summary\n"
            "Adds a repository-local graph provider.\n"
        )
    )

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))

    assert brief.requirements == ()
    assert brief.guardrails == ()
    assert brief.intent.text == "Expose structural facts to the report."
    assert brief.intent.authority == "pr_description"
    assert [item.text for item in brief.claims] == [
        "Adds a repository-local graph provider."
    ]
    html = render_html(brief)
    assert "No explicit acceptance criteria found." in html
    assert "Acceptance basis" in html
    assert ">R1<" not in html


def test_pr_title_is_intent_only_when_description_has_no_intro() -> None:
    packet = _packet(
        pr_body="## Summary\n- Adds structural mapping.\n",
    )

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))

    assert brief.intent.text == "Add structural graph foundation"
    assert brief.intent.authority == "pr_title"
    assert brief.intent.role == "intent"
    assert brief.requirements == ()


def test_provided_requirements_override_extraction_without_losing_context() -> None:
    packet = _packet(
        pr_body=(
            "Review structural evidence.\n\n"
            "## Acceptance criteria\n"
            "- Extracted criterion.\n\n"
            "## Goals\n"
            "- Keep the provider replaceable.\n\n"
            "## Summary\n"
            "- Adds a structural port.\n"
        )
    )
    provided = Requirement(id="R1", text="Provided criterion.")

    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(packet=packet, requirements=(provided,))
    )

    assert [item.text for item in brief.requirements] == [
        "Provided criterion."
    ]
    assert [item.text for item in brief.objectives] == [
        "Keep the provider replaceable."
    ]
    assert [item.text for item in brief.claims] == [
        "Adds a structural port."
    ]


def test_scope_boundary_baseline_and_verification_preserve_authority() -> None:
    packet = _packet(
        issue_body=(
            "## Goal\n"
            "- Make evaluation repeatable.\n\n"
            "## Scope\n"
            "- Define evaluation contracts.\n"
            "- Add offline golden cases.\n\n"
            "## Acceptance criteria\n"
            "- Evaluation output is deterministic.\n\n"
            "## Out of scope\n"
            "- Changing candidate ranking.\n"
            "- Adding an LLM.\n"
        ),
        pr_body=(
            "Add an offline evaluation foundation.\n\n"
            "## Summary\n"
            "- Add evaluation contracts.\n\n"
            "## Boundary\n"
            "- Candidate ranking is unchanged.\n"
            "- No LLM is introduced.\n\n"
            "## Baseline\n"
            "- Precision at five is 1.0.\n\n"
            "## Verification\n"
            "- The full test suite passes.\n"
        ),
    )

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))

    assert [
        (item.id, item.purpose, item.authority)
        for item in brief.requirements
    ] == [("R1", "acceptance", "issue")]
    assert [
        (item.id, item.purpose, item.authority)
        for item in brief.guardrails
    ] == [
        ("G1", "guardrail", "issue"),
        ("G2", "guardrail", "issue"),
    ]
    assert [
        (item.id, item.purpose, item.authority)
        for item in brief.objectives
    ] == [("O1", "goal", "issue")]
    assert [
        (item.id, item.purpose, item.authority)
        for item in brief.scope
    ] == [
        ("S1", "scope", "issue"),
        ("S2", "scope", "issue"),
    ]
    assert [
        (item.id, item.purpose, item.authority)
        for item in brief.claims
    ] == [
        ("C1", "implementation", "pr_description"),
        ("C2", "boundary", "pr_description"),
        ("C3", "boundary", "pr_description"),
        ("B1", "baseline", "pr_description"),
        ("VC1", "verification", "pr_description"),
    ]
    assert all(item.sources[0].line_start for item in (*brief.scope, *brief.claims))
    html = render_html(brief)
    assert "Scope · 2 statements" in html
    assert "Objective context" not in html
    assert "Scope context" not in html
    assert "Scope guardrails" in html


def test_review_contract_aliases_preserve_source_and_verification_identity() -> None:
    packet = _packet(
        issue_body=(
            "## 1. 🎯 Desired outcomes (why):\n"
            "- Make review intent visible.\n\n"
            "## Scope of work\n"
            "- Present the authored contract.\n\n"
            "## ✅ How to verify:\n"
            "- Confirm the contract appears before review checks.\n\n"
            "## Verification notes for maintainers\n"
            "- This prose heading is not a contract section.\n"
        ),
        pr_body=(
            "## What we want to achieve\n"
            "- Keep the renderer concise.\n\n"
            "## Pipeline boundary\n"
            "- Move contract context into the brief.\n\n"
            "## Quality checks\n"
            "- The semantic tests pass.\n\n"
            "## Project motivation details\n"
            "- This prose heading is not an objective section.\n"
        ),
    )

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))

    assert [
        (item.id, item.authority, item.text)
        for item in brief.objectives
    ] == [
        ("O1", "issue", "Make review intent visible."),
        ("O2", "pr_description", "Keep the renderer concise."),
    ]
    assert [
        (item.id, item.authority, item.text)
        for item in brief.scope
    ] == [
        ("S1", "issue", "Present the authored contract."),
        ("S2", "pr_description", "Move contract context into the brief."),
    ]
    assert [
        (item.id, item.role, item.authority, item.text)
        for item in brief.verification_expectations
    ] == [
        (
            "V1",
            "context",
            "issue",
            "Confirm the contract appears before review checks.",
        ),
    ]
    assert [
        (item.id, item.role, item.authority, item.text)
        for item in brief.claims
    ] == [
        (
            "VC1",
            "claim",
            "pr_description",
            "The semantic tests pass.",
        ),
    ]
    serialized = brief.to_dict()
    assert serialized["verification_expectations"][0]["id"] == "V1"
    assert brief.overview.ci_state == "not_observed"
    assert not [
        item
        for item in brief.evidence_catalog.items
        if item.role == "verification"
    ]
    html = render_html(brief)
    assert html.count("Verification expectations · 1 statement") == 1
    assert html.index("Verification expectations · 1 statement") < html.index(
        "<h2>Verification</h2>"
    )
    assert "Verification notes for maintainers" not in html
    assert "Project motivation details" not in html


def test_pr_scope_never_becomes_provisional_acceptance() -> None:
    packet = _packet(
        pr_body=(
            "## Scope\n"
            "- Add a deterministic evaluator.\n\n"
            "## Results\n"
            "- Precision at five is 1.0.\n\n"
            "## Testing\n"
            "- Evaluation tests pass.\n"
        )
    )

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))

    assert brief.requirements == ()
    assert [item.id for item in brief.scope] == ["S1"]
    assert [(item.id, item.purpose) for item in brief.claims] == [
        ("B1", "baseline"),
        ("VC1", "verification"),
    ]


def test_context_and_typed_claims_use_the_canonical_binding_path() -> None:
    packet = _packet(
        pr_body=(
            "## Scope\n"
            "- Serialize statement purpose and authority.\n\n"
            "## Boundary\n"
            "- Candidate ranking remains unchanged.\n\n"
            "## Baseline\n"
            "- Statement accuracy is measured offline.\n\n"
            "## Verification\n"
            "- Semantic taxonomy tests pass.\n"
        ),
        changed_files=(
            ChangedFile(
                base_path="src/prismcode/evaluation/core.py",
                head_path="src/prismcode/evaluation/core.py",
                patch=(
                    "@@ -1,1 +1,4 @@\n"
                    "+statement purpose and authority\n"
                    "+candidate ranking unchanged\n"
                    "+statement accuracy measured offline\n"
                    "+semantic taxonomy tests pass\n"
                ),
            ),
        ),
    )

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    assert [item.id for item in brief.scope] == ["S1"]
    assert [item.id for item in brief.claims] == ["C1", "B1", "VC1"]
    assert brief.projection.slices == ()


def test_pr_transformation_contract_preserves_typed_structure_once() -> None:
    packet = _packet(
        pr_body=(
            "## Change\n"
            "Move transformation declaration authority into semantics.\n\n"
            "## Selected region\n"
            "- `ReviewSourcePacket` to `ReviewBrief` semantics boundary.\n\n"
            "### Inputs\n"
            "- Pull request description Markdown.\n\n"
            "### Outputs\n"
            "- `TransformationContract`.\n\n"
            "### Boundaries\n"
            "- Facts and projection remain unchanged.\n\n"
            "## Before topology\n"
            "- PR transformation prose entered generic claims or was ignored.\n\n"
            "## After topology\n"
            "- PR description → semantics → TransformationContract.\n\n"
            "## Canonical authority\n"
            "- Semantics owns transformation declaration extraction.\n\n"
            "## Production path\n"
            "- `extract_packet_semantics()` produces the contract once.\n\n"
            "## Migration\n"
            "### Producers\n"
            "- GitHub and fixture packets remain unchanged.\n"
            "### Consumers\n"
            "- `DeterministicAnalyzer` carries the contract into `ReviewBrief`.\n"
            "### Tests\n"
            "- Semantic authority tests cover typed fields and provenance.\n\n"
            "## Removed legacy paths\n"
            "- No transformation item also enters the generic C claim lane.\n\n"
            "## Completion conditions\n"
            "CC9: Every supported section has one typed identity.\n"
            "CC10: The renderer performs no transformation parsing.\n\n"
            "## Uncertainty\n"
            "- Repository observations are intentionally deferred.\n\n"
            "## Out of scope\n"
            "- Transformation assessment remains a later change.\n"
        )
    )

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    contract = brief.transformation_contract

    assert contract.source_state == "available"
    assert [(item.id, item.kind) for item in contract.claims] == [
        ("T1", "change"),
        ("T2", "selected_region"),
        ("T3", "input_boundary"),
        ("T4", "output_boundary"),
        ("T5", "boundary"),
        ("T6", "before_topology"),
        ("T7", "after_topology"),
        ("T8", "authority"),
        ("T9", "production_path"),
        ("T10", "producer_migration"),
        ("T11", "consumer_migration"),
        ("T12", "test_migration"),
        ("T13", "removal"),
        ("CC1", "completion_condition"),
        ("CC2", "completion_condition"),
        ("T14", "uncertainty"),
    ]
    assert all(item.authority == "pr_description" for item in contract.claims)
    assert all(item.sources[0].line_start for item in contract.claims)
    assert contract.region.selected_claim_ids == ("T2",)
    assert contract.region.input_boundary_claim_ids == ("T3",)
    assert contract.region.output_boundary_claim_ids == ("T4",)
    assert contract.region.boundary_claim_ids == ("T5",)
    assert contract.topology.before_claim_ids == ("T6",)
    assert contract.topology.after_claim_ids == ("T7",)
    assert contract.authority_claim_ids == ("T8",)
    assert contract.production_path_claim_ids == ("T9",)
    assert contract.migration.producer_claim_ids == ("T10",)
    assert contract.migration.consumer_claim_ids == ("T11",)
    assert contract.migration.test_claim_ids == ("T12",)
    assert contract.removal_claim_ids == ("T13",)
    assert contract.completion_condition_claim_ids == ("CC1", "CC2")
    assert contract.uncertainty_claim_ids == ("T14",)
    assert [item.text for item in brief.claims] == [
        "Transformation assessment remains a later change."
    ]
    serialized = brief.to_dict()["transformation_contract"]
    assert serialized["schema_version"] == "transformation_contract.v4"
    assert serialized["claims"][8]["text"] == (
        "extract_packet_semantics() produces the contract once."
    )
    assert serialized["region"]["boundary_claim_ids"] == ("T5",)
    assert [
        (
            item.claim_id,
            item.selector_kind,
            item.values,
            item.expectation,
            item.role,
        )
        for item in contract.predicates.predicates
    ] == [
        ("T2", "symbol", ("ReviewSourcePacket",), "reference", "target"),
        ("T2", "symbol", ("ReviewBrief",), "reference", "target"),
        ("T4", "symbol", ("TransformationContract",), "reference", "target"),
        (
            "T9",
            "symbol",
            ("extract_packet_semantics()",),
            "present_head",
            "target",
        ),
        ("T11", "symbol", ("DeterministicAnalyzer",), "present_head", "target"),
        ("T11", "symbol", ("ReviewBrief",), "present_head", "target"),
    ]
    assert {item.claim_id for item in contract.predicates.diagnostics} == {
        "T1", "T3", "T5", "T6", "T7", "T8", "T10", "T12", "T13",
        "CC1", "CC2", "T14",
    }


def test_generic_transition_states_are_preserved_without_topology_inference() -> None:
    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(
            packet=_packet(
                pr_body=(
                    "## Before\n"
                    "- `LegacyWriter` controlled the visible result.\n\n"
                    "## After\n"
                    "- `CanonicalWriter` controls the visible result.\n\n"
                    "## Before topology\n"
                    "- `Adapter` → `LegacyWriter`.\n\n"
                    "## After topology\n"
                    "- `Adapter` → `CanonicalWriter`.\n"
                )
            )
        )
    )
    contract = brief.transformation_contract

    assert [(item.id, item.kind) for item in contract.claims] == [
        ("T1", "before_state"),
        ("T2", "after_state"),
        ("T3", "before_topology"),
        ("T4", "after_topology"),
    ]
    assert contract.state_transition.before_claim_ids == ("T1",)
    assert contract.state_transition.after_claim_ids == ("T2",)
    assert contract.topology.before_claim_ids == ("T3",)
    assert contract.topology.after_claim_ids == ("T4",)
    assert {item.claim_id for item in contract.predicates.predicates} == {
        "T3",
        "T4",
    }
    assert not any(
        item.claim_id in {"T1", "T2"}
        for item in brief.transformation_alignment.bindings
    )
    assert {
        item.claim_id: item.state
        for item in brief.transformation_alignment.diagnostics
        if item.claim_id in {"T1", "T2"}
    } == {"T1": "no_eligible_fact", "T2": "no_eligible_fact"}
    assessments = brief.transformation_assessment.by_claim_id()
    assert assessments["T1"].status == "unverified"
    assert assessments["T2"].status == "unverified"
    assert assessments["T1"].reasons[0].kind == "generic_transition_context"
    summary = brief.projection.verification_workspace.transformation_summary
    assert summary.before_state_claim_ids == ("T1",)
    assert summary.after_state_claim_ids == ("T2",)
    assert {
        item.subject_id
        for item in brief.projection.verification_workspace.matrix
    } == {"T1", "T2", "T3", "T4"}


def test_empty_generic_transition_sections_do_not_manufacture_claims() -> None:
    brief = DeterministicAnalyzer().analyze(
        AnalysisInput(
            packet=_packet(
                pr_body=(
                    "## Before\n\n"
                    "## After\n\n"
                    "## Change\n"
                    "- Preserve the only authored statement.\n"
                )
            )
        )
    )

    assert [(item.id, item.kind) for item in brief.transformation_contract.claims] == [
        ("T1", "change"),
    ]
    assert brief.transformation_contract.state_transition.before_claim_ids == ()
    assert brief.transformation_contract.state_transition.after_claim_ids == ()


def test_transformation_predicates_require_explicit_code_selectors() -> None:
    semantics = extract_review_semantics(
        issue_body=None,
        issue_source=None,
        pr_body=(
            "## Selected region\n"
            "- `src/input.py` and prose_module are in the region.\n\n"
            "## After topology\n"
            "- `Adapter` → `Analyzer` → `ReviewBrief`.\n\n"
            "## Removed legacy paths\n"
            "- Remove `legacy/adapter.py`.\n\n"
            "## Canonical authority\n"
            "- Analyzer owns assessment authority.\n"
        ),
        pr_source=_pr_source(),
        pr_title="Type predicates",
    )
    contract = semantics.transformation_contract

    assert [
        (
            item.claim_id,
            item.selector_kind,
            item.values,
            item.expectation,
            item.role,
        )
        for item in contract.predicates.predicates
    ] == [
        ("T1", "repository_path", ("src/input.py",), "reference", "target"),
        (
            "T2",
            "ordered_path",
            ("Adapter", "Analyzer", "ReviewBrief"),
            "present_head",
            "target",
        ),
        (
            "T3",
            "repository_path",
            ("legacy/adapter.py",),
            "absent_head",
            "target",
        ),
    ]
    assert [item.claim_id for item in contract.predicates.diagnostics] == ["T4"]
    assert "prose_module" not in {
        value
        for item in contract.predicates.predicates
        for value in item.values
    }


def test_transformation_predicates_preserve_path_scope_role() -> None:
    semantics = extract_review_semantics(
        issue_body=None,
        issue_source=None,
        pr_body=(
            "## Removed legacy paths\n"
            "- Remove `_review_symbol_id` from "
            "`src/prismcode/convergence/structural.py`.\n"
        ),
        pr_source=_pr_source(),
        pr_title="Preserve predicate roles",
    )

    assert [
        (item.selector_kind, item.values, item.role)
        for item in semantics.transformation_contract.predicates.predicates
    ] == [
        ("symbol", ("_review_symbol_id",), "target"),
        (
            "repository_path",
            ("src/prismcode/convergence/structural.py",),
            "path_scope",
        ),
    ]


def test_transformation_heading_aliases_are_exact_and_context_aware() -> None:
    semantics = extract_review_semantics(
        issue_body=None,
        issue_source=None,
        pr_body=(
            "## Transformation region\n"
            "- semantics and model\n"
            "### Inputs\n"
            "- PR body\n"
            "### Outputs\n"
            "- typed contract\n\n"
            "## Migrations\n"
            "### Producers\n"
            "- source packets\n"
            "### Consumers\n"
            "- review brief\n"
            "### Tests\n"
            "- semantic tests\n\n"
            "## Target topology\n"
            "- packet → semantics → contract\n\n"
            "## Completion condition\n"
            "- No duplicate claim identity.\n\n"
            "## Testing\n"
            "- Existing regression tests pass.\n"
        ),
        pr_source=_pr_source(),
        pr_title="Type transformation declarations",
    )

    assert [item.kind for item in semantics.transformation_contract.claims] == [
        "selected_region",
        "input_boundary",
        "output_boundary",
        "producer_migration",
        "consumer_migration",
        "test_migration",
        "after_topology",
        "completion_condition",
    ]
    assert [(item.id, item.purpose) for item in semantics.claims] == [
        ("VC1", "verification"),
    ]


def test_transformation_source_state_distinguishes_missing_extraction() -> None:
    absent = extract_review_semantics(
        issue_body=None,
        issue_source=None,
        pr_body=None,
        pr_source=_pr_source(),
        pr_title="No description",
    )
    unrelated = extract_review_semantics(
        issue_body=None,
        issue_source=None,
        pr_body="## Summary\n- Ordinary implementation claim.\n",
        pr_source=_pr_source(),
        pr_title="Ordinary PR",
    )

    assert absent.transformation_contract.source_state == "source_absent"
    assert unrelated.transformation_contract.source_state == "extraction_missing"
    assert unrelated.transformation_contract.claims == ()
