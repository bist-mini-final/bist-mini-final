"""Generate human-readable module guides from the canonical Pydantic contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .modules.base import ExecutableModule


MODULE_DOCS_DIR = Path(__file__).resolve().parent / "modules" / "docs"


def _inline(value: Any) -> str:
    if value is None:
        return "`null`"
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(rendered) > 120:
        return "`<long default; see contract>`"
    escaped = rendered.replace("|", "\\|")
    return f"`{escaped}`"


def _schema_type(schema: Mapping[str, Any]) -> str:
    if "$ref" in schema:
        return str(schema["$ref"]).rsplit("/", 1)[-1]
    if "anyOf" in schema:
        return " | ".join(
            _schema_type(candidate)
            for candidate in schema["anyOf"]
            if isinstance(candidate, Mapping)
        )
    kind = schema.get("type", "any")
    if kind == "array":
        items = schema.get("items", {})
        return f"array<{_schema_type(items) if isinstance(items, Mapping) else 'any'}>"
    if kind == "object" and isinstance(schema.get("additionalProperties"), Mapping):
        return f"object<string, {_schema_type(schema['additionalProperties'])}>"
    return str(kind)


def _dto_table(schema: Mapping[str, Any]) -> str:
    properties = schema.get("properties")
    if not isinstance(properties, Mapping) or not properties:
        return "원본 JSON 값 전체를 DTO로 사용합니다."
    required = set(schema.get("required", []))
    rows = [
        "| Field | Type | Required | Default | Description |",
        "|---|---|---:|---|---|",
    ]
    for name, raw_field in properties.items():
        field = raw_field if isinstance(raw_field, Mapping) else {}
        default = _inline(field["default"]) if "default" in field else "-"
        description = str(field.get("description", "-")).replace("|", "\\|")
        rows.append(
            f"| `{name}` | `{_schema_type(field)}` | "
            f"{'yes' if name in required else 'no'} | {default} | {description} |"
        )
    return "\n".join(rows)


def _placeholder(name: str, schema: Mapping[str, Any]) -> Any:
    if "default" in schema:
        default = schema["default"]
        if isinstance(default, str) and len(default) > 200:
            return f"<use {name} default from ConfigDTO>"
        return default
    if name == "query_context":
        return {
            "question_id": "QUERY-EXAMPLE",
            "question_text": "사용자 질문",
        }
    if name == "document_context":
        return {
            "file_name": "example.xlsx",
            "workbook_hash": "sha256:example",
        }
    if "$ref" in schema:
        return {"replace_with": str(schema["$ref"]).rsplit("/", 1)[-1]}
    candidates = schema.get("anyOf")
    if isinstance(candidates, list):
        concrete = next(
            (
                item
                for item in candidates
                if isinstance(item, Mapping) and item.get("type") != "null"
            ),
            {},
        )
        return _placeholder(name, concrete)
    kind = schema.get("type")
    if kind == "string":
        if name == "file_name":
            return "example.xlsx"
        if name in {"question_text", "query"}:
            return "사용자 질문"
        return f"<{name}>"
    if kind in {"integer", "number"}:
        return schema.get("minimum", 1)
    if kind == "boolean":
        return False
    if kind == "array":
        return []
    return {}


def _request_example(module: ExecutableModule) -> dict[str, Any]:
    input_schema = module.input_model.model_json_schema()
    config_schema = module.config_model.model_json_schema()
    if module.definition.raw_input:
        input_example: Any = {"replace_with": "raw JSON"}
    else:
        properties = input_schema.get("properties", {})
        input_example = {
            name: _placeholder(name, field)
            for name, field in properties.items()
            if name in set(input_schema.get("required", []))
        }
    config_example = {
        name: _placeholder(name, field)
        for name, field in config_schema.get("properties", {}).items()
    }
    return {"input": input_example, "config": config_example}


def _referenced_dto_sections(*schemas: Mapping[str, Any]) -> str:
    definitions: dict[str, Mapping[str, Any]] = {}
    for schema in schemas:
        raw_definitions = schema.get("$defs", {})
        if isinstance(raw_definitions, Mapping):
            definitions.update(
                (name, definition)
                for name, definition in raw_definitions.items()
                if isinstance(definition, Mapping)
            )
    if not definitions:
        return "참조 DTO가 없습니다."
    return "\n\n".join(
        f"### `{name}`\n\n{_dto_table(definition)}"
        for name, definition in sorted(definitions.items())
    )


def render_module_markdown(module: ExecutableModule) -> str:
    """Render one module guide directly from its executable contract."""

    definition = module.definition
    input_ports = ", ".join(f"`{port}`" for port in definition.inputs) or "없음(Source)"
    output_ports = ", ".join(f"`{port}`" for port in definition.outputs) or "없음"
    request_example = json.dumps(
        _request_example(module),
        ensure_ascii=False,
        indent=2,
    )
    input_schema = module.input_model.model_json_schema()
    config_schema = module.config_model.model_json_schema()
    output_schema = module.output_model.model_json_schema()
    referenced_dtos = _referenced_dto_sections(
        input_schema,
        config_schema,
        output_schema,
    )
    return f"""# {definition.label}

> Module type: `{definition.type}` · Category: `{definition.category}` · Version: `{definition.version}`

{definition.description}

이 문서는 Pydantic DTO와 `ModuleDefinition`에서 자동 생성됩니다. 정확한 중첩 스키마는 Swagger 또는 `--contract` 명령으로 확인합니다.

## Ports

- Input ports: {input_ports}
- Output ports: {output_ports}
- Cacheable: `{str(definition.cacheable).lower()}`

## Input DTO

{_dto_table(input_schema)}

## Config DTO

{_dto_table(config_schema)}

## Output DTO

{_dto_table(output_schema)}

## Referenced DTOs

{referenced_dtos}

## Independent execution

`request.json` 예시 골격:

```json
{request_example}
```

```bash
python -m backend.tools.run_module {definition.type} --contract
python -m backend.tools.run_module {definition.type} --request request.json
```

HTTP에서는 `POST /api/modules/{definition.type}/execute`를 사용합니다. 응답은 별도 envelope 없이 Output DTO JSON입니다.
"""


def write_module_guides(modules: Iterable[ExecutableModule]) -> list[Path]:
    """Write deterministic per-module Markdown files and their index."""

    MODULE_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    rendered_modules = sorted(modules, key=lambda item: item.definition.type)
    written: list[Path] = []
    for module in rendered_modules:
        path = MODULE_DOCS_DIR / f"{module.definition.type}.md"
        path.write_text(render_module_markdown(module), encoding="utf-8")
        written.append(path)
    index_lines = [
        "# Backend module guides",
        "",
        "> 이 디렉터리의 문서는 등록된 `ModuleDefinition`과 Pydantic DTO에서 자동 생성됩니다. 개별 파일을 직접 수정하지 마세요.",
        "",
        "## 확인 방법",
        "",
        "- 읽기 중심 API 문서: [ReDoc](/redoc)",
        "- 브라우저에서 직접 실행: [Swagger UI](/docs)",
        "- 원본 OpenAPI 계약: [OpenAPI JSON](/openapi.json)",
        "- 모듈별 실시간 Markdown: `/api/modules/{module_type}/docs`",
        "",
        "## 문서 재생성",
        "",
        "DTO, 포트 또는 `ModuleDefinition`을 변경한 뒤 프로젝트 루트에서 실행합니다.",
        "",
        "```bash",
        "python -m backend.tools.generate_module_docs",
        "```",
        "",
        "테스트는 체크인된 문서가 현재 코드 계약과 동일한지 검사합니다.",
        "",
        "| Module | Category | Guide |",
        "|---|---|---|",
    ]
    index_lines.extend(
        f"| `{module.definition.type}` | {module.definition.category} | "
        f"[{module.definition.label}](./{module.definition.type}.md) |"
        for module in rendered_modules
    )
    index_path = MODULE_DOCS_DIR / "README.md"
    index_path.write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    return [index_path, *written]
