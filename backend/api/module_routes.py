"""HTTP API endpoints for discovering and inspecting registered RAG pipeline modules.

Exposes metadata, execution contracts, input/config/output Pydantic DTO schemas,
and rendered Markdown usage guides for all 19 pipeline modules managed in `modules/`.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from backend.cli.documentation.module_docs import render_module_markdown
from backend.engine.runtime.registry import ModuleRegistry


# ==============================================================================
# Pydantic Response DTOs for OpenAPI & ReDoc Schema Documentation
# ==============================================================================
class ModuleContractSummary(BaseModel):
    """RAG 파이프라인 모듈 메타데이터 및 입출력 포트 정의 DTO."""

    type: str = Field(..., description="고유 모듈 식별자 (예: 'decomposer', 'reader')")
    label: str = Field(..., description="UI 팔레트 표시용 사람이 읽을 수 있는 이름")
    category: str = Field(..., description="모듈 분류 (Query, Embedding, Retrieval, Structure, Storage, Reader)")
    description: str = Field(..., description="모듈의 기능 및 역할 설명")
    inputs: List[str] = Field(default_factory=list, description="필수 입력 포트 목록")
    outputs: List[str] = Field(default_factory=list, description="출력 포트 목록")
    config_fields: List[str] = Field(default_factory=list, description="설정 가능한 필드 키 목록")
    raw_output: bool = Field(default=False, description="원시 출력 직렬화 여부")
    version: str = Field(default="1.0", description="모듈 버전")


class ModuleListResponse(BaseModel):
    """등록된 전체 파이프라인 모듈 계약 목록 응답 DTO."""

    modules: List[Dict[str, Any]] = Field(
        ...,
        description="등록된 모든 19개 RAG 파이프라인 모듈의 정의 및 스키마 메타데이터 목록",
    )


class ModuleCategoryGroup(BaseModel):
    """아키텍처 계층별 모듈 분류 그룹 DTO."""

    category: str = Field(..., description="카테고리명 (Query, Embedding, Retrieval 등)")
    count: int = Field(..., description="해당 카테고리에 속한 모듈 수")
    module_types: List[str] = Field(..., description="모듈 타입 식별자 목록")
    modules: List[Dict[str, Any]] = Field(..., description="카테고리 내 모듈 상세 메타데이터")


class ModuleCategoriesResponse(BaseModel):
    """아키텍처 카테고리별 모듈 그룹 목록 응답 DTO."""

    categories: List[ModuleCategoryGroup] = Field(
        ...,
        description="아키텍처 계층별(Query, Embedding, Retrieval, Reader, Structure, Storage) 모듈 그룹",
    )


class ModuleDetailResponse(BaseModel):
    """단일 파이프라인 모듈의 상세 포트 계약 및 전체 JSON 스키마 응답 DTO."""

    type: str = Field(..., description="모듈 식별자")
    label: str = Field(..., description="모듈 레이블")
    category: str = Field(..., description="모듈 카테고리")
    description: str = Field(..., description="상세 설명")
    inputs: List[str] = Field(..., description="입력 포트 목록")
    outputs: List[str] = Field(..., description="출력 포트 목록")
    config_fields: List[str] = Field(..., description="설정 필드 목록")
    input_schema: Dict[str, Any] = Field(..., description="Input Pydantic DTO의 JSON Schema")
    config_schema: Dict[str, Any] = Field(..., description="Config Pydantic DTO의 JSON Schema")
    output_schema: Dict[str, Any] = Field(..., description="Output Pydantic DTO의 JSON Schema")


class AllModuleSchemasResponse(BaseModel):
    """전체 등록 모듈의 입력/설정/출력 JSON 스키마 응답 DTO."""

    schemas: Dict[str, Dict[str, Any]] = Field(
        ...,
        description="모듈 타입별 input_schema, config_schema, output_schema JSON Schema 매핑",
    )


# ==============================================================================
# Router Factory
# ==============================================================================
def create_module_router(module_registry: ModuleRegistry) -> APIRouter:
    """파이프라인 모듈 탐색 및 스키마 조회를 위한 FastAPI 라우터 생성."""
    router = APIRouter(tags=["모듈 카탈로그 및 스키마"])

    @router.get(
        "/modules",
        response_model=ModuleListResponse,
        summary="전체 파이프라인 모듈 계약 목록 조회",
        description=(
            "`modules/` 디렉토리에 등록된 19개 RAG 파이프라인 모듈의 "
            "포트 계약, Input/Config/Output DTO 스키마, UI 팔레트 메타데이터를 일괄 조회합니다."
        ),
    )
    def get_modules() -> Dict[str, Any]:
        """등록된 모든 모듈의 팔레트 메타데이터 및 정형 DTO 스키마를 반환합니다."""
        return {"modules": module_registry.definitions()}

    @router.get(
        "/modules/categories",
        response_model=ModuleCategoriesResponse,
        summary="카테고리별 모듈 분류 목록 조회",
        description=(
            "19개 파이프라인 모듈을 아키텍처 계층별"
            "(Query, Embedding, Retrieval, Reader, Structure, Storage)로 그룹화하여 조회합니다."
        ),
    )
    def get_module_categories() -> Dict[str, Any]:
        """파이프라인 모듈을 기능별 카테고리로 그룹화하여 반환합니다."""
        all_defs = module_registry.definitions()
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for definition in all_defs:
            cat = definition.get("category", "General")
            grouped.setdefault(cat, []).append(definition)

        categories_list = [
            ModuleCategoryGroup(
                category=cat,
                count=len(mods),
                module_types=[m["type"] for m in mods],
                modules=mods,
            )
            for cat, mods in sorted(grouped.items())
        ]
        return {"categories": [cg.model_dump(mode="json") for cg in categories_list]}

    @router.get(
        "/modules/schemas",
        response_model=AllModuleSchemasResponse,
        summary="모든 모듈의 Input/Config/Output JSON 스키마 조회",
        description=(
            "DAG 워크플로 캔버스 및 노드 검증에 사용되는 모든 모듈의 "
            "Pydantic DTO (입력, 설정, 출력) JSON Schema를 일괄 반환합니다."
        ),
    )
    def get_all_module_schemas() -> Dict[str, Any]:
        """모든 등록된 모듈의 JSON 스키마 사전을 일괄 반환합니다."""
        schemas_map: Dict[str, Dict[str, Any]] = {}
        for definition in module_registry.definitions():
            m_type = definition["type"]
            schemas_map[m_type] = {
                "input_schema": definition.get("input_schema", {}),
                "config_schema": definition.get("config_schema", {}),
                "output_schema": definition.get("output_schema", {}),
                "label": definition.get("label", m_type),
                "category": definition.get("category", "General"),
            }
        return {"schemas": schemas_map}

    @router.get(
        "/modules/{module_type}",
        response_model=ModuleDetailResponse,
        summary="개별 모듈 계약 및 DTO 스키마 상세 조회",
        description=(
            "지정된 `module_type` 모듈의 상세 입출력 포트 정의와 "
            "Input, Config, Output Pydantic DTO의 엄격한 JSON Schema를 반환합니다."
        ),
    )
    def get_module(
        module_type: str = Path(..., description="모듈 식별자 (예: 'decomposer', 'reader')"),
    ) -> Dict[str, Any]:
        """단일 모듈의 입력, 설정, 출력 및 실행 스키마를 반환합니다."""
        try:
            return module_registry.definition(module_type)
        except KeyError as error:
            raise HTTPException(
                status_code=404,
                detail=f"모듈 '{module_type}'을 찾을 수 없습니다.",
            ) from error

    @router.get(
        "/modules/{module_type}/docs",
        response_class=PlainTextResponse,
        summary="모듈 Markdown 사용 가이드 렌더링",
        description=(
            "해당 모듈의 Pydantic 모델과 Definition 메타데이터를 기반으로 "
            "동적으로 생성된 마크다운(Markdown) 사용 설명서를 반환합니다."
        ),
    )
    def get_module_docs(
        module_type: str = Path(..., description="모듈 식별자 (예: 'decomposer', 'reader')"),
    ) -> str:
        """모듈의 Pydantic DTO 구조로부터 마크다운 사용 가이드를 동적 렌더링합니다."""
        try:
            return render_module_markdown(module_registry.get(module_type))
        except KeyError as error:
            raise HTTPException(
                status_code=404,
                detail=f"모듈 '{module_type}'을 찾을 수 없습니다.",
            ) from error

    return router
