from __future__ import annotations

from repodelta.model.contracts import (
    EvidenceCatalog,
    ObservedTopology,
    ObservedTransformation,
)


def reconstruct_observed_transformation(
    evidence_catalog: EvidenceCatalog,
) -> ObservedTransformation:
    """Reference canonical facts without consulting authored claims or R/G."""

    structural_changes = tuple(
        item
        for item in evidence_catalog.items
        if item.kind == "structural_change"
    )
    relation_changes = tuple(
        item
        for item in evidence_catalog.items
        if item.kind == "structural_relation_change"
    )
    ownership_changes = tuple(
        item
        for item in evidence_catalog.items
        if item.kind == "structural_ownership_change"
    )
    observation = ObservedTransformation(
        structural_change_evidence_ids=tuple(
            item.id for item in structural_changes
        ),
        fallback_change_evidence_ids=tuple(
            item.id
            for item in evidence_catalog.items
            if item.changed
            and item.role == "changed_anchor"
            and item.kind != "structural_change"
        ),
        relation_change_evidence_ids=tuple(
            item.id for item in relation_changes
        ),
        ownership_change_evidence_ids=tuple(
            item.id for item in ownership_changes
        ),
        replacement_candidate_ids=tuple(
            item.id
            for item in evidence_catalog.structural_replacement_candidates
        ),
        structural_path_evidence_ids=tuple(
            item.id
            for item in evidence_catalog.items
            if item.kind == "structural_path"
        ),
        verification_evidence_ids=tuple(
            item.id
            for item in evidence_catalog.items
            if item.role == "verification"
        ),
        topology=ObservedTopology(
            base_symbol_change_evidence_ids=tuple(
                item.id
                for item in structural_changes
                if item.structural_change is not None
                and item.structural_change.base_symbol_evidence_id is not None
            ),
            head_symbol_change_evidence_ids=tuple(
                item.id
                for item in structural_changes
                if item.structural_change is not None
                and item.structural_change.head_symbol_evidence_id is not None
            ),
            base_relation_change_evidence_ids=tuple(
                item.id
                for item in relation_changes
                if item.structural_relation_change is not None
                and item.structural_relation_change.base_path_evidence_ids
            ),
            head_relation_change_evidence_ids=tuple(
                item.id
                for item in relation_changes
                if item.structural_relation_change is not None
                and item.structural_relation_change.head_path_evidence_ids
            ),
            base_ownership_change_evidence_ids=tuple(
                item.id
                for item in ownership_changes
                if item.structural_ownership_change is not None
                and (
                    item.structural_ownership_change.base_ownership_evidence_id
                    is not None
                )
            ),
            head_ownership_change_evidence_ids=tuple(
                item.id
                for item in ownership_changes
                if item.structural_ownership_change is not None
                and (
                    item.structural_ownership_change.head_ownership_evidence_id
                    is not None
                )
            ),
        ),
    )
    observation.validate_consistency(evidence_catalog)
    return observation
