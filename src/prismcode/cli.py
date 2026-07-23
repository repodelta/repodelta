from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace

from .analysis import DeterministicAnalyzer
from .codegraph import CodegraphProvider
from .contracts import AnalysisInput
from .fixture import load_fixture
from .github import GitHubApiError, GitHubClient, GitHubPullRequestAdapter
from .rendering import write_html
from .structural_mapping import (
    format_structural_graph_status,
    map_packet_changed_symbols,
)


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
    review.add_argument(
        "--trusted-github-api-host",
        action="append",
        default=[],
        help="Additional HTTPS host allowed to receive the GitHub token; repeat as needed",
    )
    review.add_argument("--max-files", type=_positive_int, default=300, help="Maximum changed files to collect")
    review.add_argument(
        "--repo-root",
        default=".",
        help=(
            "Target repository checkout containing .codegraph/codegraph.db "
            "(default: current directory)"
        ),
    )
    review.add_argument(
        "--no-structural-graph",
        action="store_true",
        help="Skip repository-local structural mapping and use lexical binding only",
    )
    review.add_argument(
        "--verbose",
        action="store_true",
        help="Print individual collection and structural diagnostics",
    )
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
            analysis_input = load_fixture(args.fixture)
        else:
            if args.pr is None:
                parser.error("--pr is required with --repo")
            token = os.environ.get(args.github_token_env) if args.github_token_env else None
            client = GitHubClient(
                token=token,
                api_url=args.github_api_url,
                trusted_api_hosts=("api.github.com", *args.trusted_github_api_host),
            )
            packet = GitHubPullRequestAdapter(client=client, max_files=args.max_files).load(args.repo, args.pr)
            analysis_input = AnalysisInput(packet=packet)
        structural_graph = None
        if not args.no_structural_graph:
            structural_graph = map_packet_changed_symbols(
                analysis_input.packet,
                CodegraphProvider(
                    args.repo_root,
                    expected_revision=(
                        analysis_input.packet.head_sha
                        if not args.fixture
                        else None
                    ),
                ),
            )
            analysis_input = replace(
                analysis_input,
                structural_graph=structural_graph,
            )
        brief = DeterministicAnalyzer().analyze(analysis_input)
        output = write_html(brief, args.output)
    except (GitHubApiError, OSError, ValueError) as exc:
        print(f"prismcode: error: {exc}", file=sys.stderr)
        return 2

    print(output)
    print(
        format_structural_graph_status(
            structural_graph,
            disabled=args.no_structural_graph,
        ),
        file=sys.stderr,
    )
    if args.verbose and structural_graph is not None:
        for diagnostic in structural_graph.diagnostics:
            print(
                f"  - {diagnostic.code}: {diagnostic.message}",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
