from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from prismcode.llm import (
    ShadowEvidenceCandidate,
    ShadowEvidenceRequest,
    load_shadow_replay,
    parse_shadow_selection,
    serialize_shadow_replay,
)
from prismcode.llm.contracts import MAX_SELECTIONS, MAX_UNRESOLVED_SURFACES


FIXTURE = "fixtures/llm-shadow/evidence-selection.json"


def test_shadow_replay_is_valid_and_byte_stable() -> None:
    request, validation = load_shadow_replay(FIXTURE)

    assert validation.accepted
    assert validation.selection is not None
    raw_response = validation.selection.to_dict()
    serialized = serialize_shadow_replay(request, raw_response)
    assert serialized == serialize_shadow_replay(request, raw_response)
    assert json.loads(serialized)["response"] == raw_response


def test_shadow_output_cannot_invent_evidence_identity() -> None:
    request, raw = _fixture_pair()
    raw["selections"][0]["evidence_id"] = "invented:model-fact"

    validation = parse_shadow_selection(raw, request)

    assert not validation.accepted
    assert {item.code for item in validation.diagnostics} == {"unknown_evidence_id"}


def test_shadow_output_fails_closed_on_duplicate_or_conflicting_selection() -> None:
    request, raw = _fixture_pair()
    duplicate = dict(raw["selections"][0])
    duplicate["role"] = "contradicting"
    raw["selections"].append(duplicate)

    validation = parse_shadow_selection(raw, request)

    assert not validation.accepted
    assert "duplicate_evidence_id" in {item.code for item in validation.diagnostics}


def test_shadow_output_is_bound_to_request_and_subject() -> None:
    request, raw = _fixture_pair()
    raw["request_id"] = "shadow:other"
    raw["subject_id"] = "T2"

    validation = parse_shadow_selection(raw, request)

    assert not validation.accepted
    assert {item.code for item in validation.diagnostics} == {
        "request_mismatch",
        "subject_mismatch",
    }


def test_shadow_output_rejects_invalid_roles_and_selection_budget() -> None:
    request = ShadowEvidenceRequest(
        request_id="shadow:T1",
        subject_id="T1",
        subject_kind="transformation_claim",
        authored_statement="Assess a bounded claim.",
        candidates=tuple(
            ShadowEvidenceCandidate(
                evidence_id=f"fact:{index}", summary="Observed fact", kind="symbol"
            )
            for index in range(MAX_SELECTIONS + 1)
        ),
    )
    raw = {
        "schema_version": "1",
        "request_id": request.request_id,
        "subject_id": request.subject_id,
        "selections": [
            {
                "evidence_id": f"fact:{index}",
                "role": "maybe" if index == 0 else "context",
                "semantic_role": "unknown",
                "rationale": "Bounded context.",
            }
            for index in range(MAX_SELECTIONS + 1)
        ],
    }

    validation = parse_shadow_selection(raw, request)

    assert not validation.accepted
    assert {item.code for item in validation.diagnostics} >= {
        "invalid_evidence_role",
        "selection_budget_exceeded",
    }


def test_shadow_contract_rejects_formal_assessment_output() -> None:
    request, raw = _fixture_pair()
    raw["status"] = "demonstrated"

    validation = parse_shadow_selection(raw, request)

    assert not validation.accepted
    assert {item.code for item in validation.diagnostics} == {
        "unexpected_response_fields"
    }


def test_shadow_output_bounds_unresolved_surfaces() -> None:
    request, raw = _fixture_pair()
    raw["unresolved_surfaces"] = [
        f"Unresolved surface {index}."
        for index in range(MAX_UNRESOLVED_SURFACES + 1)
    ]

    validation = parse_shadow_selection(raw, request)

    assert not validation.accepted
    assert {item.code for item in validation.diagnostics} == {
        "unresolved_surface_budget_exceeded"
    }


def test_candidate_membership_is_upstream_owned_and_bounded() -> None:
    request, _ = _fixture_pair()

    duplicate = replace(request.candidates[0])
    try:
        replace(request, candidates=request.candidates + (duplicate,))
    except ValueError as error:
        assert "unique" in str(error)
    else:
        raise AssertionError("duplicate canonical evidence identity was accepted")


def test_shadow_contract_has_only_cli_execution_authority() -> None:
    execution_callers = []
    for path in Path("src/prismcode").glob("**/*.py"):
        if "llm" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        if "execute_shadow_review(" in source:
            execution_callers.append(str(path))

    assert execution_callers == ["src/prismcode/cli.py"]


def _fixture_pair() -> tuple[ShadowEvidenceRequest, dict]:
    request, validation = load_shadow_replay(FIXTURE)
    assert validation.selection is not None
    return request, validation.selection.to_dict()
