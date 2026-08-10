from __future__ import annotations

from repodelta.llm.packet import (
    ShadowCodePacketPolicy,
    build_shadow_code_packet,
)
from repodelta.model.contracts import (
    ChangeRelation,
    ChangedLine,
    EvidenceCatalog,
    EvidenceItem,
    SourceRef,
)


def _catalog() -> tuple[EvidenceItem, EvidenceCatalog]:
    relation = ChangeRelation(
        id="relation:service",
        hunk_id="hunk:service",
        base_path="src/service.py",
        head_path="src/service.py",
        kind="replaced",
        added=(ChangedLine(number=10, text="return new_value"),),
        removed=(ChangedLine(number=10, text="return old_value"),),
    )
    path = EvidenceItem(
        id="E:path",
        summary="service →[calls] repository",
        kind="structural_path",
        classification="runtime",
        profile="structural_path",
        authority="structural_provider",
        revision_side="head",
        operation="observed",
        role="structural_path",
        structural_traversal_coverage="complete",
    )
    changed = EvidenceItem(
        id="E:changed",
        summary="Modified function: service",
        kind="symbol",
        classification="code",
        profile="production",
        authority="structural_provider",
        revision_side="head",
        operation="modified",
        role="revision_fact",
        changed=True,
        sources=(
            SourceRef(
                label="Codegraph symbol",
                path="src/service.py",
                line_start=8,
                line_end=12,
            ),
        ),
        change_relation_ids=(relation.id,),
        structural_path_ids=(path.id,),
        metadata={
            "path": "src/service.py",
            "symbol_kind": "function",
            "qualified_name": "service",
        },
    )
    return changed, EvidenceCatalog(
        items=(changed, path),
        change_relations=(relation,),
    )


def test_packet_preserves_directional_code_and_structural_context() -> None:
    changed, catalog = _catalog()

    candidates, limits = build_shadow_code_packet((changed,), catalog)

    candidate = candidates[0]
    assert candidate.path == "src/service.py"
    assert candidate.line_start == 8
    assert candidate.line_end == 12
    assert candidate.symbol_kind == "function"
    assert candidate.qualified_name == "service"
    assert candidate.added_code == "return new_value"
    assert candidate.removed_code == "return old_value"
    assert candidate.structural_context == ("service →[calls] repository",)
    assert limits == ()


def test_packet_reports_code_truncation_without_dropping_identity() -> None:
    changed, catalog = _catalog()

    candidates, limits = build_shadow_code_packet(
        (changed,),
        catalog,
        policy=ShadowCodePacketPolicy(
            max_candidate_code_chars=8,
            max_request_code_chars=8,
        ),
    )

    assert candidates[0].evidence_id == changed.id
    assert candidates[0].added_code == "retu"
    assert candidates[0].removed_code == "retu"
    assert "Code excerpts were truncated for 1 evidence candidates" in limits[0]
