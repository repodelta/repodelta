from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict

from repodelta.model.contracts import StructuralFocusMembership


def canonical_focus_membership_digest(
    memberships: Iterable[StructuralFocusMembership],
) -> str:
    """Return a stable digest for one complete canonical focus overlay."""

    records = [asdict(item) for item in memberships]
    records.sort(key=lambda item: (item["member_kind"], item["member_id"]))
    payload = json.dumps(
        records,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
