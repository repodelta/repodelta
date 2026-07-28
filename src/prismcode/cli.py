from __future__ import annotations

import argparse
import os
import sys
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path

from prismcode.pipeline import DeterministicAnalyzer
from prismcode.providers.codegraph import CodegraphProvider
from prismcode.guardrails.scanning import RepositoryGuardrailScanner
from prismcode.model.contracts import AnalysisInput
from prismcode.evaluation.core import (
    evaluate_suite,
    load_evaluation_suite,
    write_evaluation_json,
    write_evaluation_markdown,
)
from prismcode.intake.fixture import load_fixture
from prismcode.intake.github import GitHubApiError, GitHubClient, GitHubPullRequestAdapter
from prismcode.presentation.html import write_html
from prismcode.providers.mapping import (
    map_packet_changed_symbols,
)
from prismcode.providers.workspace import (
    ReviewRevisionRoots,
    isolated_review_roots,
)
from prismcode.presentation.status import format_structural_coverage
from prismcode.changes.hunks import parse_changed_files


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
            "Local Git repository used to create exact temporary PR revision "
            "worktrees (default: current directory)"
        ),
    )
    review.add_argument(
        "--no-structural-graph",
        action="store_true",
        help="Skip repository-local structural mapping and use changed-hunk/file anchors",
    )
    review.add_argument(
        "--verbose",
        action="store_true",
        help="Print individual collection and structural diagnostics",
    )
    review.add_argument("--output", required=True, help="Destination HTML file")
    evaluate = subparsers.add_parser(
        "evaluate",
        help="Evaluate deterministic bindings against an offline golden suite",
    )
    evaluate.add_argument("--suite", required=True, help="Evaluation suite JSON")
    evaluate.add_argument(
        "--json-output",
        required=True,
        help="Destination machine-readable evaluation result",
    )
    evaluate.add_argument(
        "--markdown-output",
        required=True,
        help="Destination Markdown evaluation summary",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "evaluate":
        try:
            suite = load_evaluation_suite(args.suite)
            result = evaluate_suite(suite, suite_path=args.suite)
            json_output = write_evaluation_json(result, args.json_output)
            markdown_output = write_evaluation_markdown(
                result, args.markdown_output
            )
        except (OSError, ValueError) as exc:
            print(f"prismcode: error: {exc}", file=sys.stderr)
            return 2
        print(json_output)
        print(markdown_output)
        return 0 if result.passed else 1
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
        workspace = (
            nullcontext(
                ReviewRevisionRoots(
                    head=Path(args.repo_root),
                )
            )
            if args.fixture
            else isolated_review_roots(
                repo_root=args.repo_root,
                head_revision=analysis_input.packet.head_sha or "",
                base_revision=analysis_input.packet.base_sha or "",
                structural_graph_enabled=not args.no_structural_graph,
            )
        )
        with workspace as roots:
            structural_graph = None
            changes = analysis_input.changes or parse_changed_files(
                analysis_input.packet.changed_files
            )
            analysis_input = replace(
                analysis_input,
                changes=changes,
                structural_graph_disabled=args.no_structural_graph,
            )
            if not args.no_structural_graph:
                structural_graph = map_packet_changed_symbols(
                    analysis_input.packet,
                    changes,
                    CodegraphProvider(
                        roots.head,
                        expected_revision=(
                            analysis_input.packet.head_sha
                            if not args.fixture
                            else None
                        ),
                        revision_side="head",
                    ),
                    base_provider=(
                        CodegraphProvider(
                            roots.base,
                            expected_revision=(
                                analysis_input.packet.base_sha
                                if not args.fixture
                                else None
                            ),
                            revision_side="base",
                        )
                        if roots.base
                        else None
                    ),
                )
                analysis_input = replace(
                    analysis_input,
                    structural_graph=structural_graph,
                )
            brief = DeterministicAnalyzer(
                guardrail_scanner=RepositoryGuardrailScanner(
                    roots.head,
                    expected_revision=(
                        analysis_input.packet.head_sha if not args.fixture else None
                    ),
                )
            ).analyze(analysis_input)
            output = write_html(brief, args.output)
    except (GitHubApiError, OSError, ValueError) as exc:
        print(f"prismcode: error: {exc}", file=sys.stderr)
        return 2

    print(output)
    print(
        format_structural_coverage(brief.overview.structural_coverage),
        file=sys.stderr,
    )
    if args.verbose:
        for diagnostic in brief.overview.attention:
            print(
                f"  - {diagnostic.label}: {diagnostic.message}",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
