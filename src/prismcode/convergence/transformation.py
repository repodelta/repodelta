from __future__ import annotations

from dataclasses import dataclass

from prismcode.model.structural_refs import path_review_ids, review_symbol_id
from prismcode.model.contracts import (
    EvidenceCatalog,
    EvidenceItem,
    TransformationContract,
    TransformationStructuralClosure,
    TransformationStructuralClosureDiagnostic,
    TransformationStructuralClosureGroup,
    TransformationSubjectSelection,
)


@dataclass(frozen=True)
class TransformationClosurePolicy:
    max_depth: int = 3
    max_path_identities: int = 30
    max_ownership_depth: int = 3


def converge_transformation_closure(
    contract: TransformationContract,
    selection: TransformationSubjectSelection,
    evidence_catalog: EvidenceCatalog,
    *,
    policy: TransformationClosurePolicy = TransformationClosurePolicy(),
) -> TransformationStructuralClosure:
    """Close selected subjects over bounded, already-collected structural facts."""

    evidence = evidence_catalog.by_id()
    matches_by_claim = selection.by_claim_id()
    relation_changes = tuple(
        item
        for item in evidence_catalog.items
        if item.kind == "structural_relation_change"
        and item.structural_relation_change is not None
    )
    ownership_changes = tuple(
        item
        for item in evidence_catalog.items
        if item.kind == "structural_ownership_change"
        and item.structural_ownership_change is not None
    )
    groups: list[TransformationStructuralClosureGroup] = []
    diagnostics: list[TransformationStructuralClosureDiagnostic] = []

    for claim in contract.claims:
        matches = matches_by_claim.get(claim.id, ())
        seed_ids = tuple(dict.fromkeys(item.evidence_id for item in matches))
        candidate_path_ids = tuple(
            sorted(
                {
                    path_id
                    for seed_id in seed_ids
                    for path_id in evidence[seed_id].structural_path_ids
                    if path_id in evidence
                    and evidence[path_id].kind == "structural_path"
                },
                key=lambda path_id: (_path_depth(evidence[path_id]), path_id),
            )
        )
        depth_eligible = tuple(
            path_id
            for path_id in candidate_path_ids
            if _path_depth(evidence[path_id]) <= policy.max_depth
        )
        selected_path_ids = depth_eligible[: policy.max_path_identities]
        selected_path_id_set = set(selected_path_ids)
        deferred_path_ids = tuple(
            path_id
            for path_id in candidate_path_ids
            if path_id not in selected_path_id_set
        )

        review_ids = {
            review_id
            for seed_id in seed_ids
            if (review_id := review_symbol_id(evidence[seed_id])) is not None
        }
        for path_id in selected_path_ids:
            review_ids.update(path_review_ids(evidence[path_id], evidence))

        selected_relations = tuple(
            item
            for item in relation_changes
            if set(_relation_path_ids(item)) & selected_path_id_set
        )
        for item in selected_relations:
            identity = item.structural_relation_change
            assert identity is not None
            review_ids.update(
                (
                    identity.source_review_symbol_id,
                    identity.target_review_symbol_id,
                )
            )

        selected_ownership: dict[str, EvidenceItem] = {}
        for _ in range(policy.max_ownership_depth):
            newly_selected = tuple(
                item
                for item in ownership_changes
                if item.id not in selected_ownership
                and item.structural_ownership_change is not None
                and item.structural_ownership_change.child_review_symbol_id
                in review_ids
            )
            if not newly_selected:
                break
            for item in newly_selected:
                selected_ownership[item.id] = item
                identity = item.structural_ownership_change
                assert identity is not None
                review_ids.add(identity.parent_review_symbol_id)

        group = TransformationStructuralClosureGroup(
            claim_id=claim.id,
            subject_match_ids=tuple(item.id for item in matches),
            seed_evidence_ids=seed_ids,
            path_evidence_ids=selected_path_ids,
            deferred_path_evidence_ids=deferred_path_ids,
            review_symbol_ids=tuple(sorted(review_ids)),
            relation_change_evidence_ids=tuple(
                item.id for item in selected_relations
            ),
            ownership_change_evidence_ids=tuple(selected_ownership),
        )
        groups.append(group)
        if deferred_path_ids:
            diagnostics.append(
                TransformationStructuralClosureDiagnostic(
                    id=f"TSCD:{claim.id}:budget_truncated",
                    claim_id=claim.id,
                    state="budget_truncated",
                    message=(
                        f"Transformation closure retained {len(selected_path_ids)} "
                        f"collected structural paths within depth "
                        f"{policy.max_depth} and identity "
                        f"{policy.max_path_identities} safety limits; "
                        f"{len(deferred_path_ids)} were deferred."
                    ),
                    affected_evidence_ids=deferred_path_ids,
                )
            )

    result = TransformationStructuralClosure(
        groups=tuple(groups),
        diagnostics=tuple(diagnostics),
    )
    result.validate_consistency(contract, selection, evidence_catalog)
    return result


def _path_depth(path: EvidenceItem) -> int:
    return int(path.metadata.get("depth", 0))


def _relation_path_ids(item: EvidenceItem) -> tuple[str, ...]:
    identity = item.structural_relation_change
    if identity is None:
        return ()
    return tuple(
        dict.fromkeys(
            (
                *item.structural_path_ids,
                *identity.base_path_evidence_ids,
                *identity.head_path_evidence_ids,
            )
        )
    )
