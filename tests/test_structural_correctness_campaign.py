from __future__ import annotations

import json
from pathlib import Path


MANIFEST = Path(
    "evaluations/structural-correctness/campaign-v1/manifest.json"
)


def test_campaign_v1_manifest_freezes_diverse_real_pr_sample() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    samples = manifest["samples"]

    assert manifest["schema_version"] == (
        "structural_correctness_campaign_manifest.v1"
    )
    assert manifest["repository"] == "repodelta/repodelta"
    assert manifest["requirements"] == {
        "human_exclusion_required": True,
        "human_unresolved_required": True,
        "real_pull_request_count": 8,
        "synthetic_counterexample_policy": "complement_only",
    }
    assert [item["pull_request"] for item in samples] == [
        208,
        238,
        245,
        250,
        235,
        262,
        267,
        240,
    ]
    assert len({item["pull_request"] for item in samples}) == 8
    assert len({item["change_shape"] for item in samples}) == 8
    assert all(item["purpose"].strip() for item in samples)


def test_campaign_material_is_separate_from_product_documentation() -> None:
    assert Path("evaluations/structural-correctness/README.md").is_file()
    assert not Path("docs/structural-correctness.md").exists()
