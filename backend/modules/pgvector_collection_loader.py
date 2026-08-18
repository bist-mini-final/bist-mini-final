from typing import Any, Dict, List, Optional, cast

from pydantic import BaseModel, Field

from ..storage.db_manager import DatabaseManager
from ..storage.pgvector_store import PgVectorStore
from .base import (
    EmptyModuleConfigDTO,
    ExecutableModule,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleInputDTO,
)
from .prebuilt_index_loader import DocumentOutputDTO, IndexOutputDTO, PrebuiltIndexLoaderOutput


class PgVectorCollectionLoaderInputDTO(ModuleInputDTO):
    collection_name: Optional[str] = Field(
        default="SPG_Company_KeyStats_v4.xlsm",
        description="단일 컬렉션 선택 시 컬렉션 이름 또는 파일명",
    )
    collection_names: List[str] = Field(
        default_factory=list,
        description="다중 선택 시 로드할 PostgreSQL pgvector 컬렉션 ID 또는 파일명 목록",
    )


class PgVectorCollectionLoaderModule(ExecutableModule):
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
    output_model = PrebuiltIndexLoaderOutput

    def __init__(
        self,
        pgvector_store: Optional[PgVectorStore] = None,
        db_manager: Optional[DatabaseManager] = None,
    ) -> None:
        self.pgvector_store = pgvector_store or PgVectorStore()
        self.db_manager = db_manager or DatabaseManager()

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(PgVectorCollectionLoaderInputDTO, payload)
        
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
        model_name = "text-embedding-3-large"
        dimension = 3072

        for target in targets:
            matched = None
            for idx in indexes:
                if idx.get("index_id") == target or idx.get("file_name") == target or idx.get("workbook_hash") == target:
                    matched = idx
                    break

            if not matched:
                continue

            cid = matched["index_id"]
            if cid in matched_collection_ids:
                continue
            matched_collection_ids.append(cid)
            matched_file_names.append(matched.get("file_name", cid))
            matched_hashes.append(matched.get("workbook_hash", cid))

            meta = self.pgvector_store.get_index_metadata(cid) or matched
            if meta.get("model"):
                model_name = meta["model"]
            if meta.get("dimension"):
                dimension = meta["dimension"]

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
                                    "row_header": cmeta.get("row_header", []),
                                    "column_header": cmeta.get("column_header", []),
                                    "cell_value": str(cmeta.get("cell_value", "")),
                                    "text": text,
                                    "metadata": cmeta,
                                })
                    finally:
                        conn.close()
                except Exception:
                    pass

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

        if not matched_collection_ids:
            # Fallback to first available index if none matched
            matched = indexes[0]
            matched_collection_ids.append(matched["index_id"])
            matched_file_names.append(matched.get("file_name", matched["index_id"]))
            matched_hashes.append(matched.get("workbook_hash", matched["index_id"]))

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
