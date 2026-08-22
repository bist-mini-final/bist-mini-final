from __future__ import annotations

# ==============================================================================
# 1. Imports
# ==============================================================================
import logging
from typing import Any, Dict, List, Optional

from pydantic import Field

from backend.storage.db_manager import DatabaseManager
from backend.storage.pgvector_store import PgVectorStore
from modules.common.base_module import (
    BaseModule,
    EmptyModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleInputDTO,
)
from modules.common.config import DEFAULT_EMBEDDING_DIMENSION, DEFAULT_EMBEDDING_MODEL

logger = logging.getLogger(__name__)


# ==============================================================================
# 2. DTOs & Item Models
# ==============================================================================
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


# ==============================================================================
# 3. Module Implementation
# ==============================================================================
class PgVectorCollectionLoaderModule(BaseModule):
    """Loads registered vector collections directly from PostgreSQL pgvector."""

    definition = ModuleDefinition(
        type="pgvector_collection_loader",
        label="PostgreSQL pgvector Collection Loader",
        category="Source",
        description="PostgreSQL 16 pgvector DB에 적재된 다중/단일 벡터 컬렉션을 로드하여 통합 document_output과 index_output을 파이프라인에 공급합니다.",
        inputs=[],
        outputs=["document_output", "index_output"],
        config_fields=[],
        raw_output=False,
        version="2",
    )
    input_model = PgVectorCollectionLoaderInputDTO
    config_model = EmptyModuleConfigDTO
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
        requested_names: List[str] = []
        if input_data.collection_name:
            requested_names.append(input_data.collection_name)
        if input_data.collection_names:
            requested_names.extend(input_data.collection_names)

        # Query all registered collections from PostgreSQL
        try:
            db_collections = self.pgvector_store.list_indexes()
        except Exception as error:
            raise ModuleExecutionError(
                f"PostgreSQL pgvector 컬렉션 목록 조회 실패: {error}"
            ) from error

        if not db_collections:
            raise ModuleExecutionError(
                "PostgreSQL pgvector에 등록된 컬렉션이 없습니다. 먼저 인덱스를 생성해 주세요."
            )

        matched_collections: List[Dict[str, Any]] = []
        if not requested_names:
            if len(db_collections) != 1:
                raise ModuleExecutionError(
                    "여러 pgvector 컬렉션이 등록되어 있습니다. 검색할 컬렉션을 명시해 주세요"
                )
            matched_collections = [db_collections[0]]
        else:
            missing_names: List[str] = []
            for req in requested_names:
                req_norm = req.strip()
                matched = next(
                    (
                        col
                        for col in db_collections
                        if col.get("index_id") == req_norm
                        or col.get("file_name") == req_norm
                        or col.get("workbook_hash") == req_norm
                    ),
                    None,
                )
                if matched:
                    if matched not in matched_collections:
                        matched_collections.append(matched)
                else:
                    missing_names.append(req)
            if missing_names:
                raise ModuleExecutionError(
                    "요청한 컬렉션을 찾을 수 없습니다: " + ", ".join(missing_names)
                )

        if not matched_collections:
            available_names = [col.get("index_id", "unknown") for col in db_collections]
            raise ModuleExecutionError(
                f"요청한 컬렉션을 찾을 수 없습니다: {requested_names}. 사용 가능: {available_names}"
            )

        # Merge metadata across collections
        matched_collection_ids = [str(col.get("index_id") or "") for col in matched_collections]
        matched_file_names = [
            str(col.get("file_name") or col.get("index_id") or "")
            for col in matched_collections
        ]
        matched_hashes = [
            str(col.get("workbook_hash") or col.get("index_id") or "")
            for col in matched_collections
        ]

        first_col = matched_collections[0]
        model_name = str(first_col.get("model") or DEFAULT_EMBEDDING_MODEL)
        dimension = int(first_col.get("dimension") or DEFAULT_EMBEDDING_DIMENSION)
        incompatible = [
            str(collection.get("index_id") or "unknown")
            for collection in matched_collections[1:]
            if str(collection.get("model") or DEFAULT_EMBEDDING_MODEL) != model_name
            or int(collection.get("dimension") or DEFAULT_EMBEDDING_DIMENSION)
            != dimension
        ]
        if incompatible:
            raise ModuleExecutionError(
                "서로 다른 임베딩 모델 또는 차원의 컬렉션은 한 번에 검색할 수 없습니다: "
                + ", ".join(incompatible)
            )

        return {
            "document_output": {
                "file_name": ", ".join(matched_file_names),
                "workbook_hash": ",".join(matched_hashes),
                "items": [],
            },
            "index_output": {
                "index_id": ",".join(matched_collection_ids),
                "file_name": ", ".join(matched_file_names),
                "workbook_hash": ",".join(matched_hashes),
                "model": model_name,
                "dimension": dimension,
                "document_count": sum(int(col.get("document_count", 0) or 0) for col in matched_collections),
            },
        }


# ==============================================================================
# 4. Exports
# ==============================================================================
__all__ = [
    "DocumentOutputDTO",
    "IndexOutputDTO",
    "PgVectorCollectionLoaderInputDTO",
    "PgVectorCollectionLoaderModule",
    "PgVectorCollectionLoaderOutput",
]
