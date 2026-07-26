from __future__ import annotations

import pytest

from prismcode.pipeline import DeterministicAnalyzer
from prismcode.model.contracts import (
    AnalysisInput,
    ChangedFile,
    ReviewSourcePacket,
    SourceRef,
    VerificationIdentity,
    VerificationObservation,
    EvidenceItem,
    EvidenceCatalog,
)
from prismcode.facts.catalog import build_evidence_catalog
from prismcode.facts.lexical import association_signature
from prismcode.changes.hunks import parse_changed_files
from prismcode.providers.structural import (
    GraphPathStep,
    GraphSymbol,
    HunkSymbolOverlap,
    StructuralGraphIndexStatus,
    StructuralGraphResult,
    StructuralPath,
)


def _symbol(symbol_id: str, qualified_name: str, path: str) -> GraphSymbol:
    return GraphSymbol(
        id=symbol_id,
        kind="function",
        name=qualified_name.rsplit(".", 1)[-1],
        qualified_name=qualified_name,
        file_path=path,
        language="python",
        start_line=1,
        end_line=3,
        sources=(
            SourceRef(
                label="Codegraph symbol",
                url=f"https://github.com/acme/widget/blob/head123/{path}#L1-L3",
                path=path,
                line_start=1,
                line_end=3,
            ),
        ),
    )


def test_catalog_deduplicates_facts_and_links_unchanged_path_symbols() -> None:
    changed = _symbol("Y", "src.adapter.adapt", "src/adapter.py")
    unchanged = _symbol("X", "src.core.run", "src/core.py")
    test_caller = _symbol("T", "tests.test_adapter.test_adapt", "tests/test_adapter.py")
    runtime_step = GraphPathStep(
        source=changed,
        target=unchanged,
        relation="calls",
        direction="outgoing",
    )
    test_step = GraphPathStep(
        source=changed,
        target=test_caller,
        relation="calls",
        direction="incoming",
    )
    structural = StructuralGraphResult(
        index=StructuralGraphIndexStatus(state="available", provider="codegraph"),
        hunk_count=2,
        overlaps=(
            HunkSymbolOverlap("hunk:1", changed, (2,), sources=changed.sources),
            HunkSymbolOverlap("hunk:2", changed, (3,), sources=changed.sources),
        ),
        paths=(
            StructuralPath(
                seed_symbol_id="Y",
                steps=(runtime_step,),
                classification="runtime",
                sources=(*changed.sources, *unchanged.sources),
            ),
            StructuralPath(
                seed_symbol_id="Y",
                steps=(test_step,),
                classification="mixed",
                sources=(*changed.sources, *test_caller.sources),
            ),
        ),
    )
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=11,
        title="Canonical evidence",
        source_records=(),
        changed_files=(
            ChangedFile(path="src/adapter.py", source_url=changed.sources[0].url),
            ChangedFile(path="src/adapter.py", source_url=changed.sources[0].url),
            ChangedFile(path="tests/test_adapter.py"),
            ChangedFile(path="docs/design.md"),
        ),
        verification_observations=(
            VerificationObservation(
                id="check:test",
                name="test",
                kind="check_run",
                status="completed",
                conclusion="success",
                head_sha="head123",
                details_url="https://github.com/acme/widget/actions/runs/1",
            ),
        ),
        source_url="https://github.com/acme/widget/pull/11",
        head_sha="head123",
    ).with_revision()

    catalog = build_evidence_catalog(
        packet, parse_changed_files(packet.changed_files), structural
    )

    assert len([item for item in catalog.items if item.kind == "changed_file"]) == 3
    symbols = [item for item in catalog.items if item.kind == "symbol"]
    assert {item.metadata["symbol_id"] for item in symbols} == {"Y", "X", "T"}
    changed_item = next(item for item in symbols if item.metadata["symbol_id"] == "Y")
    unchanged_item = next(item for item in symbols if item.metadata["symbol_id"] == "X")
    test_item = next(item for item in symbols if item.metadata["symbol_id"] == "T")
    assert changed_item.changed is True
    assert unchanged_item.changed is False
    assert unchanged_item.classification == "code"
    assert test_item.classification == "test"
    assert len(changed_item.structural_path_ids) == 2
    assert len(unchanged_item.structural_path_ids) == 1
    paths = [item for item in catalog.items if item.kind == "structural_path"]
    assert {item.classification for item in paths} == {"runtime", "mixed"}
    assert all(item.id in item.structural_path_ids for item in paths)
    verification = next(item for item in catalog.items if item.kind == "check_run")
    assert verification.classification == "ci"
    assert verification.verification_identity == VerificationIdentity(
        provider="unknown",
        kind="check_run",
        name="test",
    )
    assert verification.verification_status == "completed"
    assert verification.verification_conclusion == "success"
    assert catalog.schema_version == "evidence_catalog.v5"

    repeated = build_evidence_catalog(
        packet, parse_changed_files(packet.changed_files), structural
    )
    assert [item.id for item in repeated.items] == [item.id for item in catalog.items]


def test_review_brief_serializes_one_canonical_catalog() -> None:
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=11,
        title="No explicit requirement",
        source_records=(),
        changed_files=(ChangedFile(path="src/a.py"),),
    ).with_revision()

    brief = DeterministicAnalyzer().analyze(AnalysisInput(packet=packet))
    serialized = brief.to_dict()

    assert brief.schema_version == "review_brief.v17"
    assert serialized["evidence_catalog"]["schema_version"] == "evidence_catalog.v5"
    assert "structural_graph" not in serialized
    assert len(serialized["evidence_catalog"]["items"]) == 1
    assert serialized["evidence_catalog"]["items"][0]["kind"] == "changed_file"


def test_canonical_evidence_rejects_contradictory_identity() -> None:
    catalog = EvidenceCatalog(
        items=(
            EvidenceItem(
                id="E:bad",
                summary="Contradictory",
                kind="changed_span",
                classification="code",
                profile="production",
                changed=True,
                role="changed_anchor",
                revision_side="review",
                operation="observed",
            ),
        )
    )

    with pytest.raises(ValueError, match="head or base"):
        catalog.validate_consistency()


def test_patch_spans_are_canonical_fallback_evidence() -> None:
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=11,
        title="Canonical hunk evidence",
        source_records=(),
        changed_files=(
            ChangedFile(
                path="src/service.py",
                patch="@@ -1 +1 @@\n-old_call()\n+new_bounded_call()\n",
            ),
        ),
    ).with_revision()
    catalog = build_evidence_catalog(
        packet, parse_changed_files(packet.changed_files)
    )
    assert [item.kind for item in catalog.items] == ["changed_span"]
    assert catalog.items[0].metadata["head_preview"] == "new_bounded_call()"
    assert catalog.items[0].metadata["base_preview"] == "old_call()"
    assert "newboundedcall" in catalog.items[0].head_signature.identifiers
    assert "oldcall" in catalog.items[0].base_signature.identifiers
    assert catalog.items[0].revision_side == "head"
    assert catalog.items[0].operation == "modified"


def test_exact_symbol_replaces_its_mapped_hunk_evidence() -> None:
    symbol = _symbol("S", "src.service.run", "src/service.py")
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=11,
        title="Map exact symbol",
        source_records=(),
        changed_files=(
            ChangedFile(
                path="src/service.py",
                patch="@@ -1 +1 @@\n-old_call()\n+new_call()\n",
            ),
        ),
    ).with_revision()
    structural = StructuralGraphResult(
        index=StructuralGraphIndexStatus(state="available", provider="codegraph"),
        hunk_count=1,
        overlaps=(
            HunkSymbolOverlap(
                "hunk:src/service.py:0",
                symbol,
                (1,),
                sources=symbol.sources,
            ),
        ),
    )

    catalog = build_evidence_catalog(
        packet, parse_changed_files(packet.changed_files), structural
    )

    assert not [item for item in catalog.items if item.kind == "changed_span"]
    assert [item.metadata["symbol_id"] for item in catalog.items] == ["S"]
    assert "newcall" in catalog.items[0].head_signature.identifiers
    assert "oldcall" in catalog.items[0].base_signature.identifiers


def test_partial_symbol_mapping_keeps_only_uncovered_span_content() -> None:
    symbol = _symbol("S", "src.service.first", "src/service.py")
    packet = ReviewSourcePacket(
        repository="acme/widget",
        pull_request=11,
        title="Partially map span",
        source_records=(),
        changed_files=(
            ChangedFile(
                path="src/service.py",
                patch=(
                    "@@ -1,0 +1,2 @@\n"
                    "+first_mapped_call()\n"
                    "+second_uncovered_call()\n"
                ),
            ),
        ),
    ).with_revision()
    structural = StructuralGraphResult(
        index=StructuralGraphIndexStatus(state="available", provider="codegraph"),
        hunk_count=1,
        overlaps=(
            HunkSymbolOverlap(
                "hunk:src/service.py:0",
                symbol,
                (1,),
                sources=symbol.sources,
            ),
        ),
    )

    catalog = build_evidence_catalog(
        packet,
        parse_changed_files(packet.changed_files),
        structural,
    )

    changed_symbol = next(item for item in catalog.items if item.kind == "symbol")
    fallback = next(item for item in catalog.items if item.kind == "changed_span")
    assert "firstmappedcall" in changed_symbol.head_signature.identifiers
    assert "seconduncoveredcall" not in changed_symbol.head_signature.identifiers
    assert "seconduncoveredcall" in fallback.head_signature.identifiers
    assert "firstmappedcall" not in fallback.head_signature.identifiers
    assert fallback.metadata["added_lines"] == (2,)
