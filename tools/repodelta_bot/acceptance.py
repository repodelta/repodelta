from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class AcceptanceResult:
    owner: str
    head_sha: str
    approved: bool
    reason: str


def evaluate_acceptance(
    *,
    owner: str,
    head_sha: str,
    maintainers: Iterable[str],
    reviews: Iterable[dict[str, Any]],
) -> AcceptanceResult:
    maintainer_set = {login.casefold() for login in maintainers}

    if owner.casefold() not in maintainer_set:
        return AcceptanceResult(
            owner=owner,
            head_sha=head_sha,
            approved=False,
            reason="designated acceptance owner is not a maintainer",
        )

    latest_state: str | None = None

    for review in reviews:
        user = review.get("user") or {}
        login = user.get("login")

        if not isinstance(login, str):
            continue

        if login.casefold() != owner.casefold():
            continue

        if review.get("commit_id") != head_sha:
            continue

        state = str(review.get("state", "")).casefold()

        if state in {"approved", "changes_requested", "dismissed"}:
            latest_state = state

    if latest_state == "approved":
        return AcceptanceResult(
            owner=owner,
            head_sha=head_sha,
            approved=True,
            reason="designated acceptance owner approved the current head",
        )

    return AcceptanceResult(
        owner=owner,
        head_sha=head_sha,
        approved=False,
        reason="designated acceptance owner has not approved the current head",
    )


ACCEPTANCE_OWNER_MARKER = "RepoDelta-Acceptance-Owner:"


def add_acceptance_owner_to_body(body: str, owner: str) -> str:
    marker = f"<!-- {ACCEPTANCE_OWNER_MARKER} {owner} -->"

    if body.endswith("\n"):
        return f"{body}\n{marker}\n"

    return f"{body}\n\n{marker}\n"



def get_acceptance_owner_from_timeline(
    timeline: Iterable[dict[str, Any]],
    *,
    bot_login: str,
) -> str | None:
    owner: str | None = None

    for event in timeline:
        event_type = event.get("event")

        if event_type not in {"review_requested", "review_request_removed"}:
            continue

        actor = event.get("actor") or {}
        actor_login = actor.get("login") if isinstance(actor, dict) else None

        if not isinstance(actor_login, str):
            continue

        if actor_login.casefold() != bot_login.casefold():
            continue

        requested = event.get("requested_reviewer") or {}
        requested_login = (
            requested.get("login")
            if isinstance(requested, dict)
            else None
        )

        if not isinstance(requested_login, str) or not requested_login:
            continue

        if event_type == "review_requested":
            owner = requested_login
        elif (
            owner is not None
            and owner.casefold() == requested_login.casefold()
        ):
            owner = None

    return owner
