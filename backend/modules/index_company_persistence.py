"""Attach extracted company metadata to a persisted pgvector index."""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Optional

from pydantic import Field

from ..storage.pgvector_store import PgVectorStore
from .base import (
    EmptyModuleConfigDTO,
    ExecutableModule,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
)
from .company_entity_extractor import CompanyEntityExtractorOutputDTO
from .vector_index_writer import VectorIndexDTO


class IndexCompanyPersistenceInputDTO(ModuleDTO):
    index_input: VectorIndexDTO = Field(description="pgvector 인덱스 저장 결과")
    company_input: CompanyEntityExtractorOutputDTO = Field(
        description="기업 엔티티 추출 결과",
    )


class IndexCompanyPersistenceOutputDTO(ModuleDTO):
    index_id: str
    company_name: str
    ticker: str = ""


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
)


class IndexCompanyPersistenceModule(ExecutableModule):
    """Persist company metadata only after both upstream branches complete."""

    definition: ClassVar[ModuleDefinition] = _INDEX_COMPANY_DEFINITION
    input_model = IndexCompanyPersistenceInputDTO
    config_model = EmptyModuleConfigDTO
    execution_model = IndexCompanyPersistenceInputDTO
    output_model = IndexCompanyPersistenceOutputDTO

    def __init__(self, pgvector_store: Optional[PgVectorStore] = None) -> None:
        self.pgvector_store = pgvector_store or PgVectorStore()

    def execute(self, payload: IndexCompanyPersistenceInputDTO) -> Dict[str, Any]:
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
