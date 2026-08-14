from __future__ import annotations

import argparse
import os
import subprocess
import sys
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlparse

from repodelta.pipeline import DeterministicAnalyzer
from repodelta.providers.codegraph import CodegraphProvider
from repodelta.closure.scanning import RepositoryClosureScanner
from repodelta.model.contracts import AnalysisInput
from repodelta.evaluation.core import (
    evaluate_suite,
    load_evaluation_suite,
    write_evaluation_json,
    write_evaluation_markdown,
)
from repodelta.evaluation.comparison import write_shadow_comparison_html
from repodelta.evaluation.structural_correctness import (
    observe_structural_correctness,
    prepare_structural_correctness_label_template,
    prepare_structural_correctness_packet,
    write_comparison_html as write_structural_correctness_comparison_html,
    write_json_artifact as write_structural_correctness_artifact,
)
from repodelta.evaluation.shadow import load_human_shadow_labels_from_packet
from repodelta.intake.fixture import load_fixture
from repodelta.intake.github import GitHubApiError, GitHubClient, GitHubPullRequestAdapter
from repodelta.presentation.html import write_html
from repodelta.providers.mapping import (
    map_packet_changed_symbols,
)
from repodelta.providers.workspace import (
    ReviewRevisionRoots,
    isolated_review_roots,
    remote_review_roots,
)
from repodelta.presentation.status import format_structural_coverage
from repodelta.changes.hunks import parse_changed_files
from repodelta.llm import (
    OpenAIShadowConfig,
    OpenAIShadowProvider,
    execute_shadow_review,
    execute_shadow_admissions,
    load_shadow_labeling_packet,
    load_shadow_replay_provider,
    unavailable_shadow_execution,
    prepare_shadow_labeling_packet,
    write_shadow_labeling_packet,
    write_shadow_execution,
)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _github_cli_hostname(api_url: str) -> str | None:
    hostname = urlparse(api_url).hostname
    if not hostname:
        return None
    return "github.com" if hostname.casefold() == "api.github.com" else hostname


def _github_token_from_cli(api_url: str) -> str | None:
    hostname = _github_cli_hostname(api_url)
    if not hostname:
        return None
    try:
        completed = subprocess.run(
            ["gh", "auth", "token", "--hostname", hostname],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    token = completed.stdout.strip()
    return token or None


def _resolve_github_token(env_name: str | None, api_url: str) -> str | None:
    if not env_name:
        return None
    token = os.environ.get(env_name)
    if token and token.strip():
        return token.strip()
    return _github_token_from_cli(api_url)


def _openai_shadow_provider_from_env() -> OpenAIShadowProvider | None:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    model = os.environ.get("REPODELTA_LLM_MODEL", "").strip()
    if not api_key or not model:
        return None
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip()
    return OpenAIShadowProvider(
        OpenAIShadowConfig(
            api_key=api_key,
            model=model,
            base_url=base_url or "https://api.openai.com/v1",
            timeout_seconds=_float_env(
                "REPODELTA_LLM_TIMEOUT_SECONDS",
                180.0,
            ),
            max_output_tokens=_int_env(
                "REPODELTA_LLM_MAX_OUTPUT_TOKENS",
                1_200,
            ),
            api_profile=_choice_env(
                "REPODELTA_LLM_API_PROFILE",
                "openai",
                {"openai", "siliconflow", "deepseek"},
            ),
            thinking_mode=_choice_env(
                "REPODELTA_LLM_THINKING_MODE",
                "default",
                {"default", "enabled", "disabled"},
            ),
            reasoning_effort=_choice_env(
                "REPODELTA_LLM_REASONING_EFFORT",
                "default",
                {"default", "high", "max"},
            ),
            thinking_budget=_optional_int_env(
                "REPODELTA_LLM_THINKING_BUDGET"
            ),
        )
    )


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc


def _int_env(name: str, default: int) -> int:
    value = _optional_int_env(name)
    return default if value is None else value


def _optional_int_env(name: str) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _choice_env(name: str, default: str, choices: set[str]) -> str:
    value = os.environ.get(name, "").strip().casefold() or default
    if value not in choices:
        raise ValueError(
            f"{name} must be one of: {', '.join(sorted(choices))}"
        )
    return value


def _enrich_github_auth_error(
    error: GitHubApiError,
    *,
    token: str | None,
    token_env: str | None,
    api_url: str,
) -> GitHubApiError:
    if error.status_code not in {401, 403, 404}:
        return error
    hostname = _github_cli_hostname(api_url) or "the configured GitHub host"
    if token:
        detail = (
            "The selected GitHub credentials may not have access to the private "
            "repository or pull request"
        )
    else:
        source = token_env or "the configured token environment variable"
        detail = (
            f"No GitHub token was available from {source} or "
            f"gh auth token --hostname {hostname}"
        )
    return GitHubApiError(
        f"{error}. {detail}",
        status_code=error.status_code,
        url=error.url,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="repodelta", description="Generate evidence-linked review briefs")
    subparsers = parser.add_subparsers(dest="command", required=True)
    review = subparsers.add_parser("review", help="Generate a review brief")
    source = review.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixture", help="Path to a RepoDelta review fixture")
    source.add_argument("--repo", help="GitHub repository in owner/name form")
    review.add_argument("--pr", type=_positive_int, help="GitHub pull request number; required with --repo")
    review.add_argument(
        "--github-token-env",
        default="GITHUB_TOKEN",
        help=(
            "Environment variable containing a GitHub token; when unset, "
            "RepoDelta tries gh auth token for the API host "
            "(default: GITHUB_TOKEN)"
        ),
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
        help=(
            "Optional local Git repository used instead of fetching exact PR "
            "revisions from GitHub"
        ),
    )
    review.add_argument(
        "--no-structural-graph",
        action="store_true",
        help="Skip Codegraph structural mapping and use changed-hunk/file anchors",
    )
    review.add_argument(
        "--verbose",
        action="store_true",
        help="Print individual collection and structural diagnostics",
    )
    review.add_argument("--output", required=True, help="Destination HTML file")
    review.add_argument(
        "--llm-shadow",
        action="store_true",
        help="Run bounded LLM shadow selection without changing review conclusions",
    )
    review.add_argument(
        "--llm-shadow-replay",
        help="Exact recorded shadow response used as the provider transport",
    )
    review.add_argument(
        "--llm-shadow-output",
        help="Destination JSON artifact (default: <output>.llm-shadow.json)",
    )
    review.add_argument(
        "--llm-shadow-labeling-output",
        help=(
            "Prepare a pre-execution labeling packet without invoking a model"
        ),
    )
    review.add_argument(
        "--llm-shadow-labeling-input",
        help="Frozen pre-execution packet required for a blinded shadow run",
    )
    review.add_argument(
        "--llm-shadow-human-labels",
        help="Complete human labels frozen against the labeling packet",
    )
    review.add_argument(
        "--structural-correctness-packet-output",
        help=(
            "Write a blind structural labeling packet and a separate canonical "
            "observation artifact without changing the review"
        ),
    )
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
    compare_shadow = subparsers.add_parser(
        "compare-shadow",
        help="Render a non-authoritative offline LLM shadow comparison",
    )
    compare_shadow.add_argument(
        "--labeling-packet", required=True, help="Frozen labeling packet JSON"
    )
    compare_shadow.add_argument(
        "--execution", required=True, help="Validated shadow execution JSON"
    )
    compare_shadow.add_argument(
        "--human-labels", required=True, help="Complete human labels JSON"
    )
    compare_shadow.add_argument(
        "--output", required=True, help="Destination comparison HTML"
    )
    compare_structural = subparsers.add_parser(
        "compare-structural-correctness",
        help="Render a non-authoritative structural correctness comparison",
    )
    compare_structural.add_argument("--labeling-packet", required=True)
    compare_structural.add_argument("--observation", required=True)
    compare_structural.add_argument(
        "--reference-labels",
        "--human-labels",
        dest="reference_labels",
        required=True,
        help=(
            "Proposed or adjudicated reference labels JSON; "
            "--human-labels remains a compatibility alias"
        ),
    )
    compare_structural.add_argument("--output", required=True)
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
            print(f"repodelta: error: {exc}", file=sys.stderr)
            return 2
        print(json_output)
        print(markdown_output)
        return 0 if result.passed else 1
    if args.command == "compare-shadow":
        try:
            output = write_shadow_comparison_html(
                args.labeling_packet,
                args.execution,
                args.human_labels,
                args.output,
            )
        except (OSError, ValueError) as exc:
            print(f"repodelta: error: {exc}", file=sys.stderr)
            return 2
        print(output)
        return 0
    if args.command == "compare-structural-correctness":
        try:
            output = write_structural_correctness_comparison_html(
                args.labeling_packet,
                args.observation,
                args.reference_labels,
                args.output,
            )
        except (OSError, ValueError) as exc:
            print(f"repodelta: error: {exc}", file=sys.stderr)
            return 2
        print(output)
        return 0
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
            token = _resolve_github_token(args.github_token_env, args.github_api_url)
            client = GitHubClient(
                token=token,
                api_url=args.github_api_url,
                trusted_api_hosts=("api.github.com", *args.trusted_github_api_host),
            )
            try:
                packet = GitHubPullRequestAdapter(
                    client=client,
                    max_files=args.max_files,
                ).load(args.repo, args.pr)
            except GitHubApiError as exc:
                raise _enrich_github_auth_error(
                    exc,
                    token=token,
                    token_env=args.github_token_env,
                    api_url=args.github_api_url,
                ) from exc
            analysis_input = AnalysisInput(packet=packet)
        if args.fixture:
            workspace = nullcontext(
                ReviewRevisionRoots(head=Path(args.repo_root or "."))
            )
        elif args.repo_root:
            workspace = isolated_review_roots(
                repo_root=args.repo_root,
                head_revision=analysis_input.packet.head_sha or "",
                base_revision=analysis_input.packet.base_sha or "",
                structural_graph_enabled=not args.no_structural_graph,
            )
        else:
            workspace = remote_review_roots(
                repository=args.repo,
                pull_request=args.pr,
                api_url=args.github_api_url,
                token=token,
                head_revision=analysis_input.packet.head_sha or "",
                base_revision=analysis_input.packet.base_sha or "",
                structural_graph_enabled=not args.no_structural_graph,
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
                closure_scanner=RepositoryClosureScanner(
                    roots.head,
                    expected_head_revision=(
                        analysis_input.packet.head_sha if not args.fixture else None
                    ),
                    base_root=roots.base,
                    expected_base_revision=(
                        analysis_input.packet.base_sha if not args.fixture else None
                    ),
                )
            ).analyze(analysis_input)
            structural_correctness_outputs: tuple[Path, Path, Path] | None = None
            if args.structural_correctness_packet_output:
                correctness_packet = prepare_structural_correctness_packet(brief)
                packet_output = write_structural_correctness_artifact(
                    correctness_packet,
                    args.structural_correctness_packet_output,
                )
                observation = observe_structural_correctness(
                    brief, correctness_packet
                )
                observation_output = write_structural_correctness_artifact(
                    observation,
                    f"{args.structural_correctness_packet_output}.observation.json",
                )
                label_template_output = write_structural_correctness_artifact(
                    prepare_structural_correctness_label_template(
                        correctness_packet
                    ),
                    f"{args.structural_correctness_packet_output}.labels.template.json",
                )
                structural_correctness_outputs = (
                    packet_output,
                    observation_output,
                    label_template_output,
                )
            if args.llm_shadow_replay and not args.llm_shadow:
                parser.error("--llm-shadow-replay requires --llm-shadow")
            if args.llm_shadow_output and not args.llm_shadow:
                parser.error("--llm-shadow-output requires --llm-shadow")
            if args.llm_shadow_labeling_output and args.llm_shadow:
                parser.error(
                    "--llm-shadow-labeling-output must run before --llm-shadow"
                )
            if (
                args.llm_shadow_labeling_output
                and args.llm_shadow_labeling_input
            ):
                parser.error(
                    "--llm-shadow-labeling-output and input are mutually exclusive"
                )
            if args.llm_shadow_labeling_input and not args.llm_shadow:
                parser.error("--llm-shadow-labeling-input requires --llm-shadow")
            if args.llm_shadow_labeling_input and not args.llm_shadow_human_labels:
                parser.error(
                    "--llm-shadow-labeling-input requires --llm-shadow-human-labels"
                )
            if (
                args.llm_shadow_human_labels
                and not args.llm_shadow_labeling_input
            ):
                parser.error(
                    "--llm-shadow-human-labels requires --llm-shadow-labeling-input"
                )
            labeling_packet = None
            labeling_output = None
            if args.llm_shadow_labeling_output:
                labeling_packet = prepare_shadow_labeling_packet(brief)
                labeling_output = write_shadow_labeling_packet(
                    labeling_packet,
                    args.llm_shadow_labeling_output,
                )
            elif args.llm_shadow_labeling_input:
                current_packet = prepare_shadow_labeling_packet(brief)
                labeling_packet = load_shadow_labeling_packet(
                    args.llm_shadow_labeling_input
                )
                if labeling_packet != current_packet:
                    raise ValueError(
                        "shadow labeling packet does not match current review admissions"
                    )
                load_human_shadow_labels_from_packet(
                    args.llm_shadow_human_labels,
                    labeling_packet,
                )
            if args.llm_shadow:
                provider = (
                    load_shadow_replay_provider(args.llm_shadow_replay)
                    if args.llm_shadow_replay
                    else _openai_shadow_provider_from_env()
                )
                shadow = (
                    (
                        execute_shadow_admissions(
                            labeling_packet.admission_set,
                            provider,
                        )
                        if labeling_packet is not None
                        else execute_shadow_review(brief, provider)
                    )
                    if provider is not None
                    else unavailable_shadow_execution()
                )
                shadow_output = args.llm_shadow_output or f"{args.output}.llm-shadow.json"
                shadow = replace(
                    shadow,
                    summary=replace(shadow.summary, artifact_written=True),
                )
                write_shadow_execution(shadow, shadow_output)
                brief = replace(
                    brief,
                    overview=replace(brief.overview, llm_shadow=shadow.summary),
                )
            output = write_html(brief, args.output)
    except (GitHubApiError, OSError, ValueError) as exc:
        print(f"repodelta: error: {exc}", file=sys.stderr)
        return 2

    print(output)
    if labeling_output is not None:
        print(labeling_output)
    if structural_correctness_outputs is not None:
        for item in structural_correctness_outputs:
            print(item)
    print(
        format_structural_coverage(brief.overview.structural_coverage),
        file=sys.stderr,
    )
    print(f"LLM shadow: {brief.overview.llm_shadow.state}", file=sys.stderr)
    if args.verbose:
        for diagnostic in brief.overview.attention:
            print(
                f"  - {diagnostic.label}: {diagnostic.message}",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
