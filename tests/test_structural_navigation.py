from __future__ import annotations

import hashlib

from prismcode.model.contracts import (
    EvidenceItem,
    ReviewSourcePacket,
    StructuralGraphEdge,
    StructuralGraphNode,
)
from prismcode.presentation.html import _structural_node_href
from prismcode.projection.structural_navigation import (
    project_structural_navigation,
)


def _fact(
    fact_id: str,
    *,
    revision: str,
    operation: str,
    path: str,
    changed_lines: tuple[int, ...] = (),
) -> EvidenceItem:
    return EvidenceItem(
        id=fact_id,
        summary=f"{operation} function: example",
        kind="symbol",
        classification="code",
        profile="production",
        authority="structural_provider",
        revision_side=revision,
        operation=operation,
        role="revision_fact",
        changed=bool(changed_lines),
        metadata={
            "path": path,
            "start_line": 10,
            "end_line": 30,
            "changed_lines": changed_lines,
        },
    )


def _node(
    node_id: str,
    *,
    delta: str,
    evidence_id: str,
) -> StructuralGraphNode:
    return StructuralGraphNode(
        id=node_id,
        review_symbol_id=f"RS:{node_id}",
        delta=delta,
        evidence_ids=(evidence_id,),
        display_evidence_id=evidence_id,
    )


def _packet() -> ReviewSourcePacket:
    return ReviewSourcePacket(
        repository="acme/widget",
        pull_request=17,
        title="Navigation",
        source_records=(),
        head_sha="head123",
        base_sha="base123",
    ).with_revision()


def test_projects_head_diff_and_symbol_targets_for_changed_node() -> None:
    path = "src/example.py"
    fact = _fact(
        "E:head",
        revision="head",
        operation="modified",
        path=path,
        changed_lines=(18, 19),
    )
    node = _node("N:head", delta="modified", evidence_id=fact.id)

    result = project_structural_navigation(
        nodes=(node,),
        edges=(),
        evidence={fact.id: fact},
        packet=_packet(),
    )

    symbol, change = result.targets
    assert symbol.kind == "revision_symbol"
    assert symbol.revision_side == "head"
    assert symbol.url == (
        "https://github.com/acme/widget/blob/head123/"
        "src/example.py#L10-L30"
    )
    digest = hashlib.sha256(path.encode()).hexdigest()
    assert change.kind == "pull_request_diff"
    assert change.revision_side == "head"
    assert change.url == (
        f"https://github.com/acme/widget/pull/17/files#diff-{digest}R18"
    )
    assert _structural_node_href(result.nodes[0], result.targets) == change.url


def test_removed_node_uses_base_and_deleted_diff_side() -> None:
    fact = _fact(
        "E:base",
        revision="base",
        operation="removed",
        path="src/legacy.py",
        changed_lines=(41,),
    )
    node = _node("N:base", delta="removed", evidence_id=fact.id)

    result = project_structural_navigation(
        nodes=(node,),
        edges=(),
        evidence={fact.id: fact},
        packet=_packet(),
    )

    symbol, change = result.targets
    assert "/blob/base123/src/legacy.py#L10-L30" in symbol.url
    assert change.revision_side == "base"
    assert change.url.endswith("L41")


def test_retained_context_has_symbol_target_and_explicit_no_change_target() -> None:
    fact = _fact(
        "E:retained",
        revision="head",
        operation="retained",
        path="src/context.py",
    )
    node = _node("N:retained", delta="retained", evidence_id=fact.id)

    result = project_structural_navigation(
        nodes=(node,),
        edges=(),
        evidence={fact.id: fact},
        packet=_packet(),
    )

    symbol, change = result.targets
    assert symbol.state == "available"
    assert change.state == "unavailable"
    assert change.reason
    assert _structural_node_href(result.nodes[0], result.targets) == symbol.url


def test_base_only_retained_context_keeps_its_explicit_revision() -> None:
    fact = _fact(
        "E:base-context",
        revision="base",
        operation="retained",
        path="src/base_context.py",
    )
    node = _node("N:base-context", delta="retained", evidence_id=fact.id)

    result = project_structural_navigation(
        nodes=(node,),
        edges=(),
        evidence={fact.id: fact},
        packet=_packet(),
    )

    symbol, change = result.targets
    assert symbol.revision_side == "base"
    assert "/blob/base123/" in symbol.url
    assert change.state == "unavailable"


def test_missing_revision_location_remains_unavailable() -> None:
    fact = _fact(
        "E:missing",
        revision="head",
        operation="modified",
        path="",
        changed_lines=(2,),
    )
    node = _node("N:missing", delta="modified", evidence_id=fact.id)

    result = project_structural_navigation(
        nodes=(node,),
        edges=(),
        evidence={fact.id: fact},
        packet=None,
    )

    assert all(item.state == "unavailable" for item in result.targets)
    assert _structural_node_href(result.nodes[0], result.targets) is None


def test_changed_node_does_not_relabel_opposite_revision_location() -> None:
    fact = _fact(
        "E:wrong-revision",
        revision="base",
        operation="modified",
        path="src/old_location.py",
        changed_lines=(12,),
    )
    node = _node("N:wrong-revision", delta="modified", evidence_id=fact.id)

    result = project_structural_navigation(
        nodes=(node,),
        edges=(),
        evidence={fact.id: fact},
        packet=_packet(),
    )

    symbol, change = result.targets
    assert symbol.state == "unavailable"
    assert change.state == "unavailable"
    assert "/blob/head123/" not in str(symbol.url)


def test_exact_member_edge_references_both_endpoint_navigation_targets() -> None:
    source_fact = _fact(
        "E:source",
        revision="head",
        operation="modified",
        path="src/source.py",
        changed_lines=(12,),
    )
    target_fact = _fact(
        "E:target",
        revision="head",
        operation="retained",
        path="src/target.py",
    )
    source = _node("N:source", delta="modified", evidence_id=source_fact.id)
    target = _node("N:target", delta="retained", evidence_id=target_fact.id)
    edge = StructuralGraphEdge(
        id="E:edge",
        source_node_id=source.id,
        target_node_id=target.id,
        relation="calls",
        operation="added",
        relation_change_evidence_id="E:relation",
    )

    result = project_structural_navigation(
        nodes=(source, target),
        edges=(edge,),
        evidence={
            source_fact.id: source_fact,
            target_fact.id: target_fact,
        },
        packet=_packet(),
    )

    projected_edge = result.edges[0]
    by_id = {item.id: item for item in result.targets}
    assert by_id[
        projected_edge.source_navigation_target_id
    ].owner_node_id == source.id
    assert by_id[
        projected_edge.target_navigation_target_id
    ].owner_node_id == target.id
