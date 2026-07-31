from __future__ import annotations

from pathlib import Path

from prismcode.model.contracts import EvidenceClassification, FactProfile

_DOCUMENT_SUFFIXES = {".md", ".mdx", ".rst", ".txt", ".pdf", ".doc", ".docx"}
_WORKFLOW_PREFIXES = (".github/workflows/", ".circleci/")
_CONFIG_NAMES = {
    "pyproject.toml", "setup.cfg", "tox.ini", "package.json",
    "tsconfig.json", "dockerfile",
}
_DEPENDENCY_NAMES = {
    "requirements.txt", "poetry.lock", "uv.lock", "package-lock.json",
    "pnpm-lock.yaml", "yarn.lock", "cargo.lock", "go.sum",
}


def path_classification(path: str) -> EvidenceClassification:
    normalized = path.casefold().replace("\\", "/")
    name = Path(normalized).name
    if (
        normalized.startswith(("test/", "tests/"))
        or "/test/" in normalized
        or "/tests/" in normalized
        or name.startswith("test_")
        or name.endswith(("_test.py", ".test.js", ".test.ts", ".spec.js", ".spec.ts"))
    ):
        return "test"
    if Path(normalized).suffix in _DOCUMENT_SUFFIXES:
        return "document"
    return "code"


def fact_profile(path: str) -> FactProfile:
    normalized = path.casefold().replace("\\", "/")
    name = Path(normalized).name
    suffix = Path(normalized).suffix
    if path_classification(path) == "test":
        return "test"
    if suffix in _DOCUMENT_SUFFIXES:
        return "document"
    if normalized.startswith(_WORKFLOW_PREFIXES):
        return "workflow"
    if name in _DEPENDENCY_NAMES:
        return "dependency"
    if name in _CONFIG_NAMES or suffix in {".ini", ".toml", ".yaml", ".yml", ".json"}:
        return "configuration"
    if "migration" in normalized or "schema" in normalized:
        return "schema"
    if any(part in normalized.split("/") for part in ("vendor", "generated", "dist")):
        return "generated"
    return "production"
