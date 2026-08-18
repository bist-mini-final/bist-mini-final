from typing import Any, Dict, cast

from pydantic import BaseModel, Field

from ..storage.embedding_artifacts import EmbeddingArtifactStore
from ..storage.vector_index import VectorIndexStore
from .base import EmptyModuleConfigDTO, ExecutableModule, ModuleDefinition, ModuleDTO
from .cell_text_embedder import CellTextEmbeddingsDTO


class VectorIndexWriterInputDTO(CellTextEmbeddingsDTO):
    """Cell embedding artifact received from the upstream embedder."""


class VectorIndexDTO(ModuleDTO):
    index_id: str = Field(
        pattern=r"^[a-f0-9]{64}$",
        description="영속 벡터 인덱스의 콘텐츠 주소",
    )
    file_name: str = Field(description="인덱싱한 원본 Excel 파일명")
    workbook_hash: str = Field(description="인덱싱한 Excel 파일 해시")
    model: str = Field(description="문서 임베딩 모델 ID")
    dimension: int = Field(gt=0, description="벡터 차원")
    document_count: int = Field(gt=0, description="저장된 검색 문서 개수")


class VectorIndexWriterModule(ExecutableModule):
    definition = ModuleDefinition(
        type="vector_index_writer",
        label="Vector Index Writer",
        category="Transform",
        description="셀 임베딩과 메타데이터를 영속 벡터 인덱스로 저장합니다.",
        inputs=["input"],
        outputs=["index_output"],
        config_fields=[],
        raw_output=True,
        cacheable=False,
        version="3",
    )
    input_model = VectorIndexWriterInputDTO
    config_model = EmptyModuleConfigDTO
    execution_model = VectorIndexWriterInputDTO
    output_model = VectorIndexDTO

    def __init__(
        self,
        artifact_store: EmbeddingArtifactStore,
        index_store: VectorIndexStore,
    ) -> None:
        self.artifact_store = artifact_store
        self.index_store = index_store

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(VectorIndexWriterInputDTO, payload)
        vectors = self.artifact_store.get(
            input_data.artifact_id,
            len(input_data.items),
            input_data.dimension,
        )
        index_id = self.index_store.index_id(input_data.artifact_id)
        metadata = {
            "file_name": input_data.file_name,
            "workbook_hash": input_data.workbook_hash,
            "model": input_data.model,
            "dimension": input_data.dimension,
            "document_count": len(input_data.items),
            "artifact_id": input_data.artifact_id,
            "items": [item.model_dump(mode="json") for item in input_data.items],
        }
        self.index_store.put(index_id, vectors, metadata)
        return {
            "index_id": index_id,
            "file_name": input_data.file_name,
            "workbook_hash": input_data.workbook_hash,
            "model": input_data.model,
            "dimension": input_data.dimension,
            "document_count": len(input_data.items),
        }
