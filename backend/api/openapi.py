"""OpenAPI and ReDoc schema composition."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from backend.api.versioning import API_VERSION
from backend.bootstrap.application import ApplicationContainer

logger = logging.getLogger("backend.api.openapi")

OPENAPI_TAGS = [
    {"name": "Authentication", "description": "서명 세션 로그인과 현재 사용자 확인"},
    {"name": "시스템 헬스 & 프로브", "description": "Kubernetes 프로브 및 상태 진단"},
    {"name": "Kubernetes 작업 관제", "description": "ScaledJob, Job, Pod 읽기 전용 상태"},
    {"name": "데이터 소스 관리", "description": "스프레드시트와 pgvector 인덱스 관리"},
    {"name": "스프레드시트 렌더 아티팩트", "description": "시트 렌더 이미지 서빙"},
    {"name": "모듈 카탈로그 및 스키마", "description": "파이프라인 입출력 계약"},
    {"name": "워크플로 정의 관리", "description": "DAG 정의 관리"},
    {"name": "워크플로 실행 및 실시간 스트림", "description": "DAG 실행과 SSE 텔레메트리"},
    {"name": "BI 기업 목록 및 개요", "description": "기업과 BI 상태"},
    {"name": "BI 대시보드 스냅샷", "description": "재무 지표와 근거"},
    {"name": "BI 머티리얼라이제이션 작업", "description": "BI 백그라운드 작업"},
    {"name": "BI 지표 질문 및 배치 계산", "description": "지표 질문과 진행률"},
    {"name": "기업 비교", "description": "BI 원천 기반 버전형 기업 비교 스냅샷"},
    {"name": "벤치마크 실행 및 채점", "description": "정확도, 비용, 지연 평가"},
]


def custom_openapi_schema(
    application: FastAPI,
    container: ApplicationContainer,
) -> dict[str, Any]:
    """Build one versioned schema and inject the external module DTO contracts."""

    if application.openapi_schema:
        return application.openapi_schema

    schema = get_openapi(
        title="BIST 엔터프라이즈 RAG 파이프라인 & BI 엔진 API",
        version=API_VERSION,
        description=(
            "재무 스프레드시트 구조 분석, pgvector 하이브리드 검색, "
            "근거 기반 BI 및 Kubernetes 비동기 실행을 위한 REST API입니다."
        ),
        routes=application.routes,
    )
    schema["x-tagGroups"] = [
        {
            "name": "1. 시스템 및 인프라",
            "tags": [
                "시스템 헬스 & 프로브",
                "Kubernetes 작업 관제",
                "데이터 소스 관리",
                "스프레드시트 렌더 아티팩트",
            ],
        },
        {"name": "2. RAG 파이프라인 모듈", "tags": ["모듈 카탈로그 및 스키마"]},
        {
            "name": "3. DAG 워크플로 엔진",
            "tags": ["워크플로 정의 관리", "워크플로 실행 및 실시간 스트림"],
        },
        {
            "name": "4. BI 대시보드 및 분석 엔진",
            "tags": [
                "BI 기업 목록 및 개요",
                "BI 대시보드 스냅샷",
                "BI 머티리얼라이제이션 작업",
                "BI 지표 질문 및 배치 계산",
            ],
        },
        {"name": "5. 기업 비교 분석", "tags": ["기업 비교"]},
        {"name": "6. RAG 벤치마크 평가", "tags": ["벤치마크 실행 및 채점"]},
    ]

    schemas = schema.setdefault("components", {}).setdefault("schemas", {})
    security_schemes = schema["components"].setdefault("securitySchemes", {})
    security_schemes["sessionCookie"] = {
        "type": "apiKey",
        "in": "cookie",
        "name": "bist_session",
        "description": "로그인 API가 발급하는 HttpOnly 서명 세션 쿠키",
    }
    schema["security"] = [{"sessionCookie": []}]
    for public_path in (
        "/healthz",
        "/livez",
        "/readyz",
        "/api/v1/auth/login",
        "/api/v1/auth/session",
    ):
        for operation in schema.get("paths", {}).get(public_path, {}).values():
            if isinstance(operation, dict):
                operation["security"] = []
    try:
        modules = container.runtime.services.module_registry.list_modules()
        for module in modules:
            for model_attr in ("input_model", "config_model", "output_model"):
                model_cls = getattr(module, model_attr, None)
                if model_cls is None or not hasattr(model_cls, "model_json_schema"):
                    continue
                model_schema = model_cls.model_json_schema(
                    mode="serialization",
                    ref_template="#/components/schemas/{model}",
                )
                schemas.setdefault(model_cls.__name__, model_schema)
                for name, definition in model_schema.pop("$defs", {}).items():
                    schemas.setdefault(name, definition)
    except Exception:
        logger.warning("모듈 DTO OpenAPI 스키마 주입 실패", exc_info=True)

    application.openapi_schema = schema
    return schema


__all__ = ["OPENAPI_TAGS", "custom_openapi_schema"]
