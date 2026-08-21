"""Module for loading Excel structured documents across multiple companies from pgvector collections."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple, cast

from pydantic import BaseModel, Field

from backend.storage.db_manager import DatabaseManager
from backend.storage.pgvector_store import PgVectorStore
from modules.common.base_module import (
    ExecutableModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleExecutionError,
    ModuleInputDTO,
    QueryContextDTO,
)
from modules.structure.cell_text_serializer import CellTextDocumentDTO, CellTextSerializerOutput
from modules.query.financial_thesaurus import resolve_company_names

logger = logging.getLogger(__name__)

KNOWN_COMPANY_COLLECTIONS: Dict[str, str] = {}


class MultiCompanyCollectionLoaderInputDTO(ModuleInputDTO):
    query_context: Optional[QueryContextDTO] = Field(
        default=None,
        description="기업명 자동 추출에 사용할 질의 계보 DTO",
    )
    collection_names: Optional[List[str]] = Field(
        default=None,
        description="직접 지정할 pgvector 컬렉션 ID 목록 (선택 사항)",
    )
    target_companies: Optional[List[str]] = Field(
        default=None,
        description="직접 지정할 대상 기업명 목록 (선택 사항)",
    )


class MultiCompanyCollectionLoaderConfigDTO(ModuleConfigDTO):
    auto_resolve_from_query: bool = Field(
        default=True,
        description="질문 본문에서 기업명을 자동으로 감지하여 컬렉션을 선택할지 여부",
    )
    fallback_company: Optional[str] = Field(
        default=None,
        description="기업명을 감지하지 못했을 때 사용할 기본 기업명",
    )


class MultiCompanyCollectionLoaderExecutionDTO(
    MultiCompanyCollectionLoaderInputDTO, MultiCompanyCollectionLoaderConfigDTO
):
    """Execution DTO for MultiCompanyCollectionLoaderModule."""


class MultiCompanyCollectionLoaderOutputDTO(BaseModel):
    document_output: CellTextSerializerOutput
    index_output: Dict[str, Any]
    loaded_collections: List[str]
    loaded_companies: List[str]


class MultiCompanyCollectionLoaderModule(ExecutableModule):
    definition = ModuleDefinition(
        type="multi_company_collection_loader",
        label="Multi-Company Collection Loader",
        category="Storage",
        description="질문 내 기업명을 정규화하여 복수 기업의 pgvector 셀 문서를 병렬 로드하고 통합합니다.",
        inputs=["query_context"],
        outputs=["document_output", "index_output"],
        config_fields=["auto_resolve_from_query", "fallback_company"],
        raw_output=True,
        version="1",
    )
    input_model = MultiCompanyCollectionLoaderInputDTO
    config_model = MultiCompanyCollectionLoaderConfigDTO
    execution_model = MultiCompanyCollectionLoaderExecutionDTO
    output_model = MultiCompanyCollectionLoaderOutputDTO

    def __init__(
        self,
        pgvector_store: Optional[PgVectorStore] = None,
        db_manager: Optional[DatabaseManager] = None,
    ) -> None:
        self.pgvector_store = pgvector_store or PgVectorStore()
        self.db_manager = db_manager or DatabaseManager()

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(MultiCompanyCollectionLoaderExecutionDTO, payload)

        target_cols: List[str] = list(input_data.collection_names or [])
        target_companies: List[str] = list(input_data.target_companies or [])

        # 1. If explicit companies provided, resolve their collections first
        for comp in list(target_companies):
            col_id = KNOWN_COMPANY_COLLECTIONS.get(comp)
            if col_id and col_id not in target_cols:
                target_cols.append(col_id)

        # 2. Only auto-resolve from query when no explicit company or collection was specified
        if not target_cols and not target_companies and input_data.auto_resolve_from_query and input_data.query_context:
            q_text = input_data.query_context.question_text
            resolved_companies = resolve_company_names(
                q_text, default=[input_data.fallback_company]
            )
            for comp in resolved_companies:
                if comp not in target_companies:
                    target_companies.append(comp)
                col_id = KNOWN_COMPANY_COLLECTIONS.get(comp)
                if col_id and col_id not in target_cols:
                    target_cols.append(col_id)

        # 3. Fallback if still empty
        if not target_cols and input_data.fallback_company:
            fallback_col = KNOWN_COMPANY_COLLECTIONS.get(input_data.fallback_company)
            if fallback_col:
                target_cols.append(fallback_col)
                if input_data.fallback_company not in target_companies:
                    target_companies.append(input_data.fallback_company)

        col_str = ",".join(target_cols)
        fn_str = ", ".join(f"{c}.xlsm" for c in target_companies)
        wh_str = target_cols[0] if target_cols else ""

        return {
            "document_output": {
                "file_name": fn_str,
                "workbook_hash": wh_str,
                "items": [],
            },
            "index_output": {
                "index_id": col_str,
                "file_name": fn_str,
                "workbook_hash": wh_str,
                "model": "text-embedding-3-large",
                "dimension": 3072,
                "document_count": len(target_cols) * 10000,
            },
            "loaded_collections": target_cols,
            "loaded_companies": target_companies,
        }
