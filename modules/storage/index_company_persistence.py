"""Attach extracted company metadata to a persisted pgvector index."""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Optional

from pydantic import Field

from backend.storage.pgvector_store import PgVectorStore
from modules.common.base_module import (
    EmptyModuleConfigDTO,
    BaseModule,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
)
from modules.storage.company_entity_extractor import CompanyEntityExtractorOutputDTO
from modules.storage.pgvector_index_writer import VectorIndexDTO


class IndexCompanyPersistenceInputDTO(ModuleDTO):
    index_input: VectorIndexDTO = Field(description="pgvector 인덱스 저장 결과")
    company_input: CompanyEntityExtractorOutputDTO = Field(
        description="기업 엔티티 추출 결과",
    )


class IndexCompanyPersistenceOutputDTO(ModuleDTO):
    index_id: str = Field(description="기업 메타데이터가 반영된 pgvector 인덱스 ID")
    company_name: str = Field(description="인덱스와 셀 메타데이터에 저장된 기업 표시명")
    ticker: str = Field(default="", description="추출된 티커 심볼 (없으면 빈 문자열)")


_INDEX_COMPANY_DEFINITION = ModuleDefinition(
    type="index_company_persistence",
    label="Index Company Persistence",
    category="Storage / DB",
    description="추출한 기업명을 pgvector 컬렉션과 청크 메타데이터에 반영합니다.",
    inputs=["index_input", "company_input"],
    outputs=["output"],
    config_fields=[],
    raw_output=True,
    cacheable=False,
    version="2",
)


class IndexCompanyPersistenceModule(BaseModule):
    """Persist company metadata only after both upstream branches complete."""

    definition: ClassVar[ModuleDefinition] = _INDEX_COMPANY_DEFINITION
    input_model = IndexCompanyPersistenceInputDTO
    config_model = EmptyModuleConfigDTO
    execution_model = IndexCompanyPersistenceInputDTO
    output_model = IndexCompanyPersistenceOutputDTO

    def __init__(self, pgvector_store: Optional[PgVectorStore] = None) -> None:
        """Initialize the module with the provided pgvector store or a default store."""
        self.pgvector_store = pgvector_store or PgVectorStore()

    def execute(self, payload: IndexCompanyPersistenceInputDTO) -> Dict[str, Any]:
        """
        Persist the company name for an index and return the resulting company metadata.
        
        Parameters:
            payload (IndexCompanyPersistenceInputDTO): Index persistence result and extracted company information.
        
        Returns:
            Dict[str, Any]: The index ID, stored company name, and ticker.
        
        Raises:
            ModuleExecutionError: If no company name is available or the index update fails.
        """
        company = payload.company_input
        company_name = company.display_name or company.company_name
        if not company_name:
            raise ModuleExecutionError("저장할 기업명이 없습니다")
        try:
            self.pgvector_store.update_index_company(
                payload.index_input.index_id,
                company_name,
            )
        except Exception as error:
            raise ModuleExecutionError(f"인덱스 기업명 저장 실패: {error}") from error
        return {
            "index_id": payload.index_input.index_id,
            "company_name": company_name,
            "ticker": company.ticker,
        }
