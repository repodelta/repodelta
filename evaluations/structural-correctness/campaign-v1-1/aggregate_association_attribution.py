"""Aggregate committed per-PR association attribution comparisons."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from repodelta.evaluation.association_attribution import (
    aggregate_association_comparisons,
    write_association_comparison,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    comparisons = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(args.results_dir.glob("pr-*.json"))
    }
    write_association_comparison(
        aggregate_association_comparisons(comparisons), args.output
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
