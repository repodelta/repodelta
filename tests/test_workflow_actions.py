from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NODE24_MINIMUM_MAJOR = {
    "actions/checkout": 5,
    "actions/setup-python": 6,
    "actions/upload-artifact": 6,
    "actions/download-artifact": 8,
}
ACTION_REFERENCE = re.compile(r"uses:\s+([^@\s]+)@v(\d+)\b")


def test_github_managed_actions_do_not_reintroduce_node20_majors() -> None:
    stale_references = []
    for workflow in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        for action, raw_major in ACTION_REFERENCE.findall(
            workflow.read_text(encoding="utf-8")
        ):
            minimum_major = NODE24_MINIMUM_MAJOR.get(action)
            if minimum_major is not None and int(raw_major) < minimum_major:
                stale_references.append(
                    f"{workflow.relative_to(ROOT)}: {action}@v{raw_major}"
                )

    assert stale_references == []
