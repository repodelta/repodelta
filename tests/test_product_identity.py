from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CURRENT_TEXT_ROOTS = (
    ROOT / "src",
    ROOT / "tests",
    ROOT / ".github",
    ROOT / "docs",
    ROOT / "fixtures",
)
CURRENT_TEXT_FILES = (
    ROOT / "README.md",
    ROOT / "LICENSE",
    ROOT / "pyproject.toml",
)
HISTORICAL_TEXT_FILES = {ROOT / "docs" / "provenance.md", ROOT / "fixtures" / "pr574.json"}
HISTORICAL_TEXT_ROOTS = (
    ROOT / "fixtures" / "llm-shadow" / "campaign-v1",
    ROOT / "fixtures" / "llm-shadow" / "campaign-v2",
)
TEXT_SUFFIXES = {".json", ".md", ".py", ".toml", ".yml", ".yaml", ".txt"}


def test_supported_tree_has_one_repodelta_product_identity() -> None:
    stale_identity = "prism" + "code"
    stale_paths = []
    for path in _current_text_paths():
        if stale_identity in path.read_text(encoding="utf-8").casefold():
            stale_paths.append(path.relative_to(ROOT).as_posix())

    assert stale_paths == []
    assert (ROOT / "src" / "repodelta" / "cli.py").is_file()
    assert not (ROOT / "src" / stale_identity).exists()


def _current_text_paths() -> tuple[Path, ...]:
    discovered = set(CURRENT_TEXT_FILES)
    for root in CURRENT_TEXT_ROOTS:
        discovered.update(
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix in TEXT_SUFFIXES
            and not _is_historical(path)
        )
    return tuple(sorted(discovered))


def _is_historical(path: Path) -> bool:
    return path in HISTORICAL_TEXT_FILES or any(
        path.is_relative_to(root) for root in HISTORICAL_TEXT_ROOTS
    )
