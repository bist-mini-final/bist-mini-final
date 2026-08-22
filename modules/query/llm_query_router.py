"""Zero-shot and structured LLM Query Router for extracting target companies, topics, and sheet categories."""

from __future__ import annotations

# ==============================================================================
# 1. Imports
# ==============================================================================
import logging
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, Field

from modules.common.base_llm import (
    BaseLLMModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleInputDTO,
    QueryContextDTO,
)
from modules.common.config import DEFAULT_ROUTER_MODEL
from .semantic_query_matcher import QueryExample, SemanticQueryMatchOutput, load_examples

logger = logging.getLogger(__name__)


# ==============================================================================
# 2. Prompts & Catalog Formatting
# ==============================================================================
def _build_catalog_prompt(examples: Sequence[QueryExample]) -> str:
    """Build a structured catalog prompt grouping financial sheet categories and sample queries."""
    grouped: Dict[str, Dict[str, Any]] = {}
    for example in examples:
        entry = grouped.setdefault(
            example.target,
            {"sheets": set(), "questions": []},
        )
        entry["sheets"].update(example.sheets)
        entry["questions"].append(example.question)

    catalog_lines: List[str] = []
    for target, payload in sorted(grouped.items()):
        sheets = ", ".join(sorted(payload["sheets"]))
        catalog_lines.append(f"Target category: {target}")
        catalog_lines.append(f"Relevant sheets: {sheets}")
        catalog_lines.append("Representative questions:")
        catalog_lines.extend(
            f"  - {question}" for question in payload["questions"][:8]
        )
        catalog_lines.append("")

    return (
        "You are an expert spreadsheet query router.\n"
        "Analyze the user's natural language question and extract:\n"
        "1. Any target companies/entities mentioned (e.g. 'Samsung Electronics', 'SK Hynix').\n"
        "2. The target financial report category matching the catalog.\n\n"
        "Respond ONLY with a JSON object:\n"
        "{\n"
        '  "target": "<category_or_null>",\n'
        '  "confidence": <number_between_0_and_1>,\n'
        '  "company_name": "<primary_company_or_null>",\n'
        '  "company_scopes": [\n'
        '    {"raw_mention": "...", "canonical_name": "...", "matched_score": 0.0, '
        '"target_topics": ["..."], "suggested_sheets": ["..."]}\n'
        "  ],\n"
        '  "reason": "..."\n'
        "}\n\n"
        f"{chr(10).join(catalog_lines)}"
    )


# ==============================================================================
# 3. DTOs & Schema Definitions
# ==============================================================================
class LlmCompanyScopeDocument(BaseModel):
    """Pydantic schema for individual company entity parsed by the LLM."""

    raw_mention: Optional[str] = Field(default=None, description="질문 내 원본 언급 텍스트")
    canonical_name: str = Field(description="정규화된 공식 기업명")
    matched_score: float = Field(default=1.0, ge=0.0, le=1.0, description="엔티티 매칭 점수")
    target_topics: List[str] = Field(default_factory=list, description="추출된 질문 지표/토픽")
    suggested_sheets: List[str] = Field(default_factory=list, description="매핑 추천 시트 목록")


class LlmRouterDocument(BaseModel):
    """Pydantic response schema for LLM structured output parsing."""

    target: Optional[str] = Field(default=None, description="재무제표 카테고리 (BS, IS, CF 등)")
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="라우팅 신뢰도 (제공되지 않으면 중립값 0.5)",
    )
    company_name: Optional[str] = Field(default=None, description="주요 기업명")
    company_scopes: List[LlmCompanyScopeDocument] = Field(
        default_factory=list,
        description="식별된 개별 기업 스코프 목록",
    )
    reason: Optional[str] = Field(default=None, description="라우팅 판단 근거")


class LlmQueryRouterInputDTO(ModuleInputDTO):
    """Input contract containing user query context."""

    query_context: QueryContextDTO = Field(description="원본 사용자 질문 컨텍스트")


class LlmQueryRouterConfigDTO(ModuleConfigDTO):
    """Configuration contract for LLM Query Router."""

    model: str = Field(default=DEFAULT_ROUTER_MODEL, description="질의 라우팅에 사용할 LLM 모델 ID")


class LlmQueryRouterOutputDTO(ModuleDTO):
    """Output contract containing structured semantic matching results."""

    semantic_match: SemanticQueryMatchOutput = Field(description="정형화된 시맨틱 매치 및 스코프 결과")


# Backward compatibility aliases
LlmQueryRouterInput = LlmQueryRouterInputDTO
LlmQueryRouterConfig = LlmQueryRouterConfigDTO
LlmQueryRouterOutput = LlmQueryRouterOutputDTO
LlmQueryRouterExecution = LlmQueryRouterInputDTO


# ==============================================================================
# 4. Module Implementation
# ==============================================================================
class LlmQueryRouterModule(BaseLLMModule):
    """Zero-shot structured LLM Query Router that identifies target companies and financial sheet categories."""

    definition = ModuleDefinition(
        type="llm_query_router",
        label="LLM Query Router",
        category="Logic",
        description="LLM을 활용하여 질문에서 대상 기업 및 관련 시트 카테고리를 추론하고 라우팅합니다.",
        inputs=["query_context"],
        outputs=["semantic_match"],
        config_fields=["model"],
        version="4",
    )
    input_model = LlmQueryRouterInputDTO
    config_model = LlmQueryRouterConfigDTO
    output_model = LlmQueryRouterOutputDTO

    def __init__(
        self,
        completion_client: Optional[Any] = None,
        examples: Optional[List[QueryExample]] = None,
    ) -> None:
        super().__init__(completion_client=completion_client)
        self.examples = examples

    def execute(
        self,
        input_data: LlmQueryRouterInputDTO,
        config: Optional[LlmQueryRouterConfigDTO] = None,
    ) -> Dict[str, Any]:
        """Execute LLM query routing against standard sheet catalog."""
        cfg = config or LlmQueryRouterConfigDTO()
        examples = self.examples if self.examples is not None else load_examples()
        if not examples:
            return {
                "semantic_match": {
                    "matched": False,
                    "target": None,
                    "confidence": 0.0,
                    "sheets": [],
                    "company_name": None,
                    "company_scopes": [],
                    "reason": "No catalog examples available",
                    "matches": [],
                    "metrics": {
                        "kind": "llm",
                        "model": cfg.model,
                        "latency_seconds": 0.0,
                        "api_usage": {},
                        "estimated_cost_usd": 0.0,
                    },
                }
            }

        # Build catalog sheet map
        valid_sheets: Dict[str, List[str]] = {}
        for example in examples:
            valid_sheets.setdefault(example.target, [])
            valid_sheets[example.target] = sorted(
                set(valid_sheets[example.target]) | set(example.sheets)
            )

        # 1-Line Structured Completion via BaseLLMModule
        prompt = input_data.query_context.question_text
        doc, usage, cost, latency = self.complete_structured(
            messages_or_prompt=prompt,
            response_model=LlmRouterDocument,
            model=cfg.model,
            system_prompt=_build_catalog_prompt(examples),
        )

        target = doc.target if doc.target in valid_sheets else None
        company_name = (
            doc.company_name.strip()
            if doc.company_name and doc.company_name.strip()
            else None
        )

        # Normalize and enrich parsed company scopes
        parsed_scopes: List[Dict[str, Any]] = [
            {
                "raw_mention": (scope.raw_mention or scope.canonical_name).strip(),
                "canonical_name": scope.canonical_name.strip(),
                "matched_score": float(scope.matched_score),
                "target_topics": [t.strip() for t in scope.target_topics if t.strip()],
                "suggested_sheets": (
                    [s.strip() for s in scope.suggested_sheets if s.strip()]
                    or (valid_sheets.get(target, []) if target else [])
                ),
            }
            for scope in doc.company_scopes
            if scope.canonical_name and scope.canonical_name.strip()
        ]

        if not parsed_scopes and company_name:
            parsed_scopes.append(
                {
                    "raw_mention": company_name,
                    "canonical_name": company_name,
                    "matched_score": float(doc.confidence),
                    "target_topics": [],
                    "suggested_sheets": valid_sheets.get(target, []) if target else [],
                }
            )

        if not company_name and parsed_scopes:
            company_name = parsed_scopes[0]["canonical_name"]

        return {
            "semantic_match": {
                "matched": bool(
                    (target is not None or parsed_scopes) and doc.confidence > 0
                ),
                "target": target,
                "confidence": float(doc.confidence),
                "sheets": valid_sheets.get(target, []) if target is not None else [],
                "company_name": company_name,
                "company_scopes": parsed_scopes,
                "reason": doc.reason or "LLM route decision",
                "matches": [],
                "metrics": {
                    "kind": "llm",
                    "model": cfg.model,
                    "latency_seconds": round(latency, 3),
                    "api_usage": usage.model_dump(mode="json"),
                    "estimated_cost_usd": round(cost, 6),
                },
            }
        }


__all__ = [
    "LlmCompanyScopeDocument",
    "LlmQueryRouterConfig",
    "LlmQueryRouterConfigDTO",
    "LlmQueryRouterExecution",
    "LlmQueryRouterInput",
    "LlmQueryRouterInputDTO",
    "LlmQueryRouterModule",
    "LlmQueryRouterOutput",
    "LlmQueryRouterOutputDTO",
    "LlmRouterDocument",
]
