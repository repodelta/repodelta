from __future__ import annotations

import subprocess
from pathlib import Path


def checkout_revision(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()


def tracked_checkout_clean(root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
            check=True, capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return not result.stdout.strip()


def is_symlinked(root: Path, path: str) -> bool:
    """Fail closed on any symlinked input, inside or outside the checkout.

    A symlink's target -- even one that resolves inside the checkout -- can be
    an untracked or generated file that the checkout cleanliness check does not
    see, so it is never provably bound to the reviewed git revision. The
    invariant is evidence-to-revision binding, not target provenance, so every
    symlinked input fails closed rather than having its target's location
    inspected.
    """

    current = root
    for part in Path(path).parts:
        current = current / part
        if current.is_symlink():
            return True
    return False
