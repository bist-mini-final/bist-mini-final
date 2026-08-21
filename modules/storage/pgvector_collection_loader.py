from __future__ import annotations

import logging
from typing import Optional, Any, Dict, List, Optional, Tuple, cast

from pydantic import BaseModel, Field

from backend.storage.db_manager import DatabaseManager
from backend.storage.pgvector_store import PgVectorStore
from modules.common.base_module import (
    EmptyModuleConfigDTO,
    BaseModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleInputDTO,
    QueryContextDTO,
)
from modules.query.financial_thesaurus import resolve_company_names
from modules.structure.cell_text_serializer import CellTextDocumentDTO, CellTextSerializerOutput

logger = logging.getLogger(__name__)


class DocumentOutputDTO(ModuleDTO):
    file_name: str
    workbook_hash: str
    items: List[Dict[str, Any]]


class IndexOutputDTO(ModuleDTO):
    index_id: str
    file_name: str
    workbook_hash: str
    model: str
    dimension: int
    document_count: int


class PgVectorCollectionLoaderOutput(ModuleDTO):
    document_output: DocumentOutputDTO
    index_output: IndexOutputDTO


class PgVectorCollectionLoaderInputDTO(ModuleInputDTO):
    collection_name: Optional[str] = Field(
        default=None,
        description="단일 컬렉션 선택 시 컬렉션 이름 또는 파일명",
    )
    collection_names: List[str] = Field(
        default_factory=list,
        description="다중 선택 시 로드할 PostgreSQL pgvector 컬렉션 ID 또는 파일명 목록",
    )


class PgVectorCollectionLoaderModule(BaseModule):
    """Loads registered vector collections directly from PostgreSQL pgvector."""

    definition = ModuleDefinition(
        type="pgvector_collection_loader",
        label="PostgreSQL pgvector Collection Loader",
        category="Source",
        description="PostgreSQL 16 pgvector DB에 적재된 다중 벡터 컬렉션을 로드하여 통합 document_output과 index_output을 파이프라인에 공급합니다.",
        inputs=[],
        outputs=["document_output", "index_output"],
        config_fields=[],
        raw_output=False,
        version="1",
    )
    input_model = PgVectorCollectionLoaderInputDTO
    config_model = EmptyModuleConfigDTO
    execution_model = PgVectorCollectionLoaderInputDTO
    output_model = PgVectorCollectionLoaderOutput

    def __init__(
        self,
        pgvector_store: Optional[PgVectorStore] = None,
        db_manager: Optional[DatabaseManager] = None,
    ) -> None:
        self.pgvector_store = pgvector_store or PgVectorStore()
        self.db_manager = db_manager or DatabaseManager()

    def execute(
        self,
        input_data: PgVectorCollectionLoaderInputDTO,
        config: Optional[EmptyModuleConfigDTO] = None,
    ) -> Dict[str, Any]:
        """
        Load selected pgvector collections and combine their documents and index metadata.
        
        Parameters:
        	payload (BaseModel): Input specifying collection IDs, file names, or workbook hashes.
        
        Returns:
        	Dict[str, Any]: Combined document and index outputs for the selected collections.
        
        Raises:
        	ModuleExecutionError: If no collections are available, a requested collection is missing, selected collections have inconsistent embedding models or dimensions, or collection documents cannot be loaded.
        """
        if config is None and isinstance(input_data, PgVectorCollectionLoaderInputDTO):
            cfg = input_data
        else:
            cfg = config or EmptyModuleConfigDTO()
        
        # 1. Resolve target collection list (support multi-select and single-select)
        targets: List[str] = []
        if input_data.collection_names:
            targets = [t.strip() for t in input_data.collection_names if t.strip()]
        elif input_data.collection_name:
            targets = [t.strip() for t in input_data.collection_name.split(",") if t.strip()]

        indexes = self.pgvector_store.list_indexes()
        if not indexes:
            raise ModuleExecutionError("PostgreSQL pgvector에 등록된 컬렉션이 없습니다. 데이터 소스 탭에서 먼저 엑셀 파일을 인덱싱하세요.")

        if not targets:
            # Default to the first available index
            targets = [indexes[0]["index_id"]]

        all_items: List[Dict[str, Any]] = []
        matched_collection_ids: List[str] = []
        matched_file_names: List[str] = []
        matched_hashes: List[str] = []
        matched_dimensions: set = set()
        matched_models: set = set()
        model_name = "text-embedding-3-large"
        dimension = 3072

        targets_meta: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []

        for target in targets:
            matched = None
            for idx in indexes:
                if idx.get("index_id") == target or idx.get("file_name") == target or idx.get("workbook_hash") == target:
                    matched = idx
                    break

            if not matched:
                raise ModuleExecutionError(
                    f"요청한 pgvector 컬렉션을 찾을 수 없습니다: {target}"
                )

            cid = matched["index_id"]
            if cid in matched_collection_ids:
                continue
            matched_collection_ids.append(cid)
            matched_file_names.append(matched.get("file_name", cid))
            matched_hashes.append(matched.get("workbook_hash", cid))

            meta = self.pgvector_store.get_index_metadata(cid) or matched
            col_model = meta.get("model")
            if col_model:
                if matched_models and col_model not in matched_models:
                    prev_model = next(iter(matched_models))
                    raise ModuleExecutionError(
                        f"선택된 pgvector 컬렉션들의 임베딩 모델이 일치하지 않습니다: {cid} (모델: {col_model}, 기존 모델: {prev_model})"
                    )
                matched_models.add(col_model)
                model_name = col_model

            col_dim = meta.get("dimension")
            if col_dim is not None:
                if matched_dimensions and col_dim not in matched_dimensions:
                    prev_dim = next(iter(matched_dimensions))
                    raise ModuleExecutionError(
                        f"선택된 pgvector 컬렉션들의 임베딩 차원이 일치하지 않습니다: {cid} (차원: {col_dim}, 기존 차원: {prev_dim})"
                    )
                matched_dimensions.add(col_dim)
                dimension = col_dim

            targets_meta.append((matched, meta))

        for matched, meta in targets_meta:
            cid = matched["index_id"]
            items = meta.get("items") or []
            if not items:
                # Load chunks directly from langchain_pg_embedding table
                try:
                    conn = self.db_manager._raw_connection()
                    try:
                        with conn.cursor() as cur:
                            cur.execute(
                                """
                                SELECT e.id, e.document, e.cmetadata
                                FROM langchain_pg_embedding e
                                JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                                WHERE c.name = %s;
                                """,
                                (cid,),
                            )
                            rows = cur.fetchall()
                            for row in rows:
                                chunk_id = row[0]
                                text = row[1] or ""
                                cmeta = row[2] or {}
                                if isinstance(cmeta, str):
                                    import json
                                    try:
                                        cmeta = json.loads(cmeta)
                                    except Exception:
                                        cmeta = {}
                                items.append({
                                    "cell_id": cmeta.get("cell_id") or chunk_id,
                                    "sheet_name": cmeta.get("sheet_name", ""),
                                    "cell_coord": cmeta.get("cell_coord", ""),
                                    "variant": cmeta.get("variant") or "header_only",
                                    "row_header": cmeta.get("row_header", []),
                                    "column_header": cmeta.get("column_header", []),
                                    "cell_value": str(cmeta.get("cell_value", "")),
                                    "text": text,
                                    "metadata": cmeta,
                                })
                    finally:
                        conn.close()
                except Exception as error:
                    raise ModuleExecutionError(
                        f"pgvector 컬렉션 문서를 읽지 못했습니다: {cid}"
                    ) from error

            clean_items = []
            for item in items:
                clean_items.append({
                    "cell_id": item.get("cell_id") or item.get("chunk_id", ""),
                    "sheet_name": item.get("sheet_name", ""),
                    "cell_coord": item.get("cell_coord", ""),
                    "row_header": item.get("row_header", []) if isinstance(item.get("row_header"), list) else [],
                    "column_header": item.get("column_header", []) if isinstance(item.get("column_header"), list) else [],
                    "cell_value": str(item.get("cell_value", "") if item.get("cell_value") is not None else ""),
                    "variant": item.get("variant") or "header_only",
                    "text": str(item.get("text", "")),
                })

            all_items.extend(clean_items)

        return {
            "document_output": {
                "file_name": ", ".join(matched_file_names),
                "workbook_hash": ",".join(matched_hashes),
                "items": all_items,
            },
            "index_output": {
                "index_id": ",".join(matched_collection_ids),
                "file_name": ", ".join(matched_file_names),
                "workbook_hash": ",".join(matched_hashes),
                "model": model_name,
                "dimension": dimension,
                "document_count": len(all_items),
            },
        }


# ==============================================================================
# 2. Multi-Company Collection Loader Module
# ==============================================================================

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


class MultiCompanyCollectionLoaderModule(BaseModule):
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

    def execute(
        self,
        input_data: MultiCompanyCollectionLoaderInputDTO,
        config: Optional[MultiCompanyCollectionLoaderConfigDTO] = None,
    ) -> Dict[str, Any]:
        if config is None and isinstance(input_data, MultiCompanyCollectionLoaderExecutionDTO):
            cfg = input_data
        else:
            cfg = config or MultiCompanyCollectionLoaderConfigDTO()

        target_cols: List[str] = list(input_data.collection_names or [])
        target_companies: List[str] = list(input_data.target_companies or [])

        # 1. If explicit companies provided, resolve their collections first
        for comp in list(target_companies):
            col_id = KNOWN_COMPANY_COLLECTIONS.get(comp)
            if col_id and col_id not in target_cols:
                target_cols.append(col_id)

        # 2. Only auto-resolve from query when no explicit company or collection was specified
        if not target_cols and not target_companies and cfg.auto_resolve_from_query and input_data.query_context:
            q_text = input_data.query_context.question_text
            default_list = [cfg.fallback_company] if cfg.fallback_company else None
            resolved_companies = resolve_company_names(
                q_text, default=default_list
            )
            for comp in resolved_companies:
                if comp not in target_companies:
                    target_companies.append(comp)
                col_id = KNOWN_COMPANY_COLLECTIONS.get(comp)
                if col_id and col_id not in target_cols:
                    target_cols.append(col_id)

        # 3. Fallback if still empty
        if not target_cols and cfg.fallback_company:
            fallback_col = KNOWN_COMPANY_COLLECTIONS.get(cfg.fallback_company)
            if fallback_col:
                target_cols.append(fallback_col)
                if cfg.fallback_company not in target_companies:
                    target_companies.append(cfg.fallback_company)

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

__all__ = [
    "DocumentOutputDTO",
    "IndexOutputDTO",
    "MultiCompanyCollectionLoaderConfigDTO",
    "MultiCompanyCollectionLoaderExecutionDTO",
    "MultiCompanyCollectionLoaderInputDTO",
    "MultiCompanyCollectionLoaderModule",
    "MultiCompanyCollectionLoaderOutputDTO",
    "PgVectorCollectionLoaderInputDTO",
    "PgVectorCollectionLoaderModule",
    "PgVectorCollectionLoaderOutput",
]
