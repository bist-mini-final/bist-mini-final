"""Documentation contracts that must stay synchronized with executable code."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

from backend.entrypoints.asgi import app

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS_ROOT = PROJECT_ROOT / "docs"
BLUEPRINT_ROOT = DOCS_ROOT / "blueprints"
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def _blueprints() -> list[Path]:
    return sorted(BLUEPRINT_ROOT.glob("**/BP-*.md"))


def _product_documentation() -> list[Path]:
    return [
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "migrations/README.md",
        *sorted(DOCS_ROOT.rglob("*.md")),
    ]


def test_blueprint_catalog_has_complete_and_consistent_metadata() -> None:
    blueprints = _blueprints()
    assert len(blueprints) == 20

    catalog = (PROJECT_ROOT / "docs/README.md").read_text(encoding="utf-8")
    for blueprint in blueprints:
        text = blueprint.read_text(encoding="utf-8")
        code = blueprint.name.split("_", 1)[0]
        assert f"**Document Code:** `{code}`" in text
        assert "**Contract State:** Target Architecture" in text
        assert "**Structure State:** Complete" in text
        assert f"[`{code}`]" in catalog


def test_documentation_uses_portable_valid_local_links() -> None:
    absolute_workspace_link = re.compile(
        r"file:///|[A-Za-z]:[/\\]Repos[/\\]bist-mini-final",
        re.IGNORECASE,
    )
    excluded_feature_reference = re.compile(
        r"local\s+vlm|로컬\s*vlm|reranker|re-ranker|bge-reranker|cross-encoder",
        re.IGNORECASE,
    )
    link_pattern = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
    failures: list[str] = []

    for document in _product_documentation():
        text = document.read_text(encoding="utf-8")
        relative_document = document.relative_to(PROJECT_ROOT)
        if absolute_workspace_link.search(text):
            failures.append(f"{relative_document}: absolute workspace link")
        if excluded_feature_reference.search(text):
            failures.append(f"{relative_document}: excluded feature reference")

        for target in link_pattern.findall(text):
            clean_target = target.strip("<>").split("#", 1)[0]
            if not clean_target or re.match(r"^[a-z]+://", clean_target, re.IGNORECASE):
                continue
            resolved = (document.parent / unquote(clean_target)).resolve()
            if not resolved.exists():
                failures.append(
                    f"{relative_document}: broken link {target} -> {resolved}"
                )

    assert not failures, "documentation consistency failures:\n" + "\n".join(failures)


def test_rest_blueprint_matches_public_openapi_operations() -> None:
    blueprint = (
        BLUEPRINT_ROOT
        / "05_interface_blueprints/BP-501_rest_api_specification.md"
    ).read_text(encoding="utf-8")
    documented: set[tuple[str, str]] = set()
    row_pattern = re.compile(r"\|\s*([^|]+?)\s*\|\s*`([^`]+)`")
    for line in blueprint.splitlines():
        matched = row_pattern.match(line)
        if matched is None:
            continue
        path = matched.group(2)
        if not path.startswith("/api/v1"):
            continue
        for method in matched.group(1).replace("`", "").split("/"):
            normalized = method.strip().upper()
            if normalized in HTTP_METHODS:
                documented.add((normalized, path))

    schema = app.openapi()
    actual = {
        (method.upper(), path)
        for path, operations in schema["paths"].items()
        if path.startswith("/api/v1")
        for method in operations
        if method.upper() in HTTP_METHODS
    }
    assert documented == actual

    baseline = (DOCS_ROOT / "CURRENT_IMPLEMENTATION_BASELINE.md").read_text(
        encoding="utf-8"
    )
    operation_count = sum(
        1
        for operations in schema["paths"].values()
        for method in operations
        if method.upper() in HTTP_METHODS
    )
    assert f"{len(schema['paths'])}개 path" in baseline
    assert f"{operation_count}개 HTTP operation" in baseline
