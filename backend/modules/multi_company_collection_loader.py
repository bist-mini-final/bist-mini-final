"""Module for loading Excel structured documents across multiple companies from pgvector collections."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple, cast

from pydantic import BaseModel, Field

from ..storage.db_manager import DatabaseManager
from ..storage.pgvector_store import PgVectorStore
from .base import (
    ExecutableModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleExecutionError,
    ModuleInputDTO,
)
from .cell_text_serializer import CellTextDocumentDTO, CellTextSerializerOutput
from .data_lineage import QueryContextDTO
from .financial_thesaurus import resolve_company_names

logger = logging.getLogger(__name__)

KNOWN_COMPANY_COLLECTIONS: Dict[str, str] = {
    "IBM": "7aa04c203cb89bbf1461ed348b9d94ecf0bc09d6b81ce1c9806efa661e902e87",
    "Bistelligence": "27904fbd1eaa13b45618eae270f63d0d3c4a8cb7ee50111dee9eb9cf3b5d512c",
    "Coldplay": "1873056acbca34a7ed67328540923f55a4be017315cfdc133fa753ac2e157348",
    "DH Innovation": "3f755b47af8e86a98545e45a2ac8be5aeae9d4dc27c108c588f895aa013b7ab4",
}


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
    fallback_company: str = Field(
        default="IBM",
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

        # Auto-resolve from query if not explicitly passed
        if input_data.auto_resolve_from_query and input_data.query_context:
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

        if not target_cols:
            fallback_col = KNOWN_COMPANY_COLLECTIONS.get(input_data.fallback_company)
            if fallback_col:
                target_cols.append(fallback_col)
                target_companies.append(input_data.fallback_company)

        all_items: List[CellTextDocumentDTO] = []
        file_names: List[str] = []
        workbook_hashes: List[str] = []

        conn = self.db_manager._raw_connection()
        try:
            with conn.cursor() as cur:
                for col_id in target_cols:
                    cur.execute(
                        """
                        SELECT e.id, e.document, e.cmetadata
                        FROM langchain_pg_embedding e
                        JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                        WHERE c.name = %s;
                        """,
                        (col_id,),
                    )
                    rows = cur.fetchall()
                    for row in rows:
                        chunk_id = row[0]
                        text = row[1] or ""
                        meta = row[2] or {}
                        cell_id = (
                            meta.get("cell_id")
                            or meta.get("chunk_id")
                            or chunk_id
                            or "unknown_cell"
                        )
                        fn = meta.get("file_name", "unknown.xlsm")
                        wh = meta.get("workbook_hash", "")
                        if fn not in file_names:
                            file_names.append(fn)
                        if wh and wh not in workbook_hashes:
                            workbook_hashes.append(wh)

                        all_items.append(
                            CellTextDocumentDTO(
                                cell_id=cell_id,
                                text=text,
                                sheet_name=meta.get("sheet_name", ""),
                                cell_coord=meta.get("cell_coord", ""),
                                row_header=meta.get("row_header", []),
                                column_header=meta.get("column_header", []),
                                cell_value=str(meta.get("cell_value", "")),
                                variant=meta.get("variant", "header_with_value"),
                            )
                        )
        except Exception as e:
            logger.error("DB 로드 실패: %s", e)
            raise ModuleExecutionError(f"pgvector 컬렉션 로드 실패: {e}") from e

        merged_doc_output = CellTextSerializerOutput(
            file_name=", ".join(file_names) if file_names else "multi_companies.xlsm",
            workbook_hash=workbook_hashes[0] if workbook_hashes else "",
            items=all_items,
        )

        return {
            "document_output": merged_doc_output.model_dump(mode="json"),
            "index_output": {
                "index_id": target_cols[0] if target_cols else "",
                "file_name": merged_doc_output.file_name,
                "workbook_hash": merged_doc_output.workbook_hash,
                "model": "text-embedding-3-large",
                "dimension": 3072,
                "document_count": len(all_items),
            },
            "loaded_collections": target_cols,
            "loaded_companies": target_companies,
        }
