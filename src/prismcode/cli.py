from __future__ import annotations

import argparse
import os
import sys

from .analysis import DeterministicAnalyzer
from .fixture import load_fixture
from .github import GitHubApiError, GitHubClient, GitHubPullRequestAdapter
from .rendering import write_html


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prismcode", description="Generate evidence-linked review briefs")
    subparsers = parser.add_subparsers(dest="command", required=True)
    review = subparsers.add_parser("review", help="Generate a review brief")
    source = review.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixture", help="Path to a PrismCode review fixture")
    source.add_argument("--repo", help="GitHub repository in owner/name form")
    review.add_argument("--pr", type=_positive_int, help="GitHub pull request number; required with --repo")
    review.add_argument(
        "--github-token-env",
        default="GITHUB_TOKEN",
        help="Environment variable containing a GitHub token (default: GITHUB_TOKEN)",
    )
    review.add_argument(
        "--github-api-url",
        default="https://api.github.com",
        help="GitHub API base URL, including GitHub Enterprise Server API URLs",
    )
    review.add_argument("--max-files", type=_positive_int, default=300, help="Maximum changed files to collect")
    review.add_argument("--output", required=True, help="Destination HTML file")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command != "review":
        return 2

    try:
        if args.fixture:
            if args.pr is not None:
                parser.error("--pr can only be used with --repo")
            review = load_fixture(args.fixture)
        else:
            if args.pr is None:
                parser.error("--pr is required with --repo")
            token = os.environ.get(args.github_token_env) if args.github_token_env else None
            client = GitHubClient(token=token, api_url=args.github_api_url)
            review = GitHubPullRequestAdapter(client=client, max_files=args.max_files).load(args.repo, args.pr)
        brief = DeterministicAnalyzer().analyze(review)
        output = write_html(brief, args.output)
    except (GitHubApiError, OSError, ValueError) as exc:
        print(f"prismcode: error: {exc}", file=sys.stderr)
        return 2

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
