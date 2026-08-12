from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from repodelta_bot.submit import SubmissionConfig, SubmissionError, submit_change


def _configured_value(value: str | None, environment_name: str) -> str:
    configured = (value or os.environ.get(environment_name, "")).strip()
    if not configured:
        raise SubmissionError(
            f"provide --{environment_name.removeprefix('REPODELTA_BOT_').lower().replace('_', '-')} "
            f"or set {environment_name}"
        )
    return configured


def _current_branch(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SubmissionError("unable to determine the current Git branch") from exc
    branch = completed.stdout.strip()
    if not branch:
        raise SubmissionError("submit requires a named local Git branch")
    return branch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repodelta-bot",
        description="Submit a local change through a GitHub App for human review",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    submit = subparsers.add_parser("submit", help="Push HEAD and create a pull request")
    submit.add_argument(
        "--app-id",
        help="GitHub App ID; or set REPODELTA_BOT_APP_ID",
    )
    submit.add_argument(
        "--installation-id",
        help="GitHub App installation ID; or set REPODELTA_BOT_INSTALLATION_ID",
    )
    submit.add_argument(
        "--private-key",
        type=Path,
        help="owner-only App private key; or set REPODELTA_BOT_PRIVATE_KEY",
    )
    submit.add_argument("--repo", required=True, help="GitHub repository in owner/name form")
    submit.add_argument("--repo-root", type=Path, default=Path.cwd())
    submit.add_argument("--head", help="Remote head branch; defaults to the current branch")
    submit.add_argument("--base", default="main")
    submit.add_argument("--title", required=True)
    submit.add_argument("--body-file", type=Path, required=True)
    submit.add_argument("--reviewer", action="append", default=[])
    submit.add_argument("--draft", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        app_id = _configured_value(args.app_id, "REPODELTA_BOT_APP_ID")
        installation_id = _configured_value(
            args.installation_id,
            "REPODELTA_BOT_INSTALLATION_ID",
        )
        key_value = args.private_key or os.environ.get("REPODELTA_BOT_PRIVATE_KEY")
        if not key_value:
            raise SubmissionError(
                "provide --private-key or set REPODELTA_BOT_PRIVATE_KEY"
            )
        body = args.body_file.read_text()
        head = args.head or _current_branch(args.repo_root)
        result = submit_change(
            SubmissionConfig(
                app_id=app_id,
                installation_id=installation_id,
                private_key=Path(key_value),
                repo=args.repo,
                head=head,
                base=args.base,
                title=args.title,
                body=body,
                reviewers=tuple(args.reviewer),
                draft=args.draft,
                repo_root=args.repo_root,
            )
        )
    except (OSError, SubmissionError) as exc:
        parser.exit(2, f"repodelta-bot: error: {exc}\n")
    print(f"Created {result.url} as {result.author}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
