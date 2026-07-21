from __future__ import annotations

import argparse

from .analysis import DeterministicAnalyzer
from .fixture import load_fixture
from .rendering import write_html


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prismcode", description="Generate evidence-linked review briefs")
    subparsers = parser.add_subparsers(dest="command", required=True)
    review = subparsers.add_parser("review", help="Generate a review brief")
    review.add_argument("--fixture", required=True, help="Path to a PrismCode review fixture")
    review.add_argument("--output", required=True, help="Destination HTML file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "review":
        brief = DeterministicAnalyzer().analyze(load_fixture(args.fixture))
        output = write_html(brief, args.output)
        print(output)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
