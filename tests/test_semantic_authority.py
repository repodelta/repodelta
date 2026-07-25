from __future__ import annotations

from prismcode.analysis import DeterministicAnalyzer
from prismcode.contracts import (
    AnalysisInput,
    ChangedFile,
    Requirement,
    ReviewSourcePacket,
    SourceRef,
    SourceRecord,
)
from prismcode.criteria import extract_review_semantics
from prismcode.criteria import parse_markdown_semantics
from prismcode.rendering import render_html


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
    assert "Provisional PR-authored criterion" in html
    assert "Review checks" in html
    assert "Objective context · 1 statement" in html
    assert "Preserve deterministic review behavior." in html
    assert "Introduces a read-only provider boundary." in html


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
        ("V1", "verification", "pr_description"),
    ]
    assert all(item.sources[0].line_start for item in (*brief.scope, *brief.claims))
    html = render_html(brief)
    assert "Scope context · 2 statements" in html
    assert "Scope guardrails" in html


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
        ("V1", "verification"),
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
                path="src/prismcode/evaluation.py",
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
    assert [item.id for item in brief.claims] == ["C1", "B1", "V1"]
    assert brief.projection.slices == ()
