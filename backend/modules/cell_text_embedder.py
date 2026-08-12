import hashlib
import json
from typing import Any, Dict, List, Optional, cast

from pydantic import BaseModel, Field

from ..bge_encoder import DEFAULT_BGE_MODEL
from ..embedding_artifacts import EmbeddingArtifactStore
from ..embedding_factory import EmbeddingEncoder, get_embedding_encoder
from .base import ExecutableModule, ModuleDefinition, ModuleDTO, ModuleExecutionError
from .cell_text_serializer import CellTextDocumentDTO, CellTextSerializerOutput
from .embedder import EMBEDDING_MODEL_OPTIONS


class CellTextEmbedderInput(CellTextSerializerOutput):
    model: str = Field(
        default="text-embedding-3-large",
        min_length=1,
        description="Excel 셀 문서 임베딩에 사용할 Hugging Face 또는 OpenAI 모델 ID",
        json_schema_extra={
            "enum": EMBEDDING_MODEL_OPTIONS,
            "options": EMBEDDING_MODEL_OPTIONS,
        },
    )
    batch_size: int = Field(
        default=64,
        ge=1,
        le=512,
        description="Excel 셀 문서를 한 번에 임베딩할 배치 크기",
    )


class EmbeddedCellTextDocumentDTO(CellTextDocumentDTO):
    embedding_index: int = Field(
        ge=0,
        description="외부 임베딩 아티팩트에서 이 셀 문서 벡터의 행 번호",
    )


class CellTextEmbeddingsDTO(ModuleDTO):
    file_name: str
    workbook_hash: str
    model: str = Field(description="문서 임베딩에 사용된 모델 ID")
    artifact_id: str = Field(
        pattern=r"^[a-f0-9]{64}$",
        description="float32 문서 벡터 아티팩트의 콘텐츠 주소",
    )
    dimension: int = Field(gt=0, description="각 문서 임베딩 벡터 차원")
    items: List[EmbeddedCellTextDocumentDTO]


class CellTextEmbedderModule(ExecutableModule):
    definition = ModuleDefinition(
        type="cell_text_embedder",
        label="Cell Text Embedder",
        category="Logic",
        description="직렬화된 Excel 셀 문서를 배치 임베딩하고 원본 메타데이터와 함께 반환합니다.",
        inputs=["input"],
        outputs=["output"],
        config_fields=["model", "batch_size"],
        raw_output=True,
        version="3",
    )
    input_model = CellTextEmbedderInput
    output_model = CellTextEmbeddingsDTO

    def __init__(
        self,
        encoder: Optional[EmbeddingEncoder] = None,
        artifact_store: Optional[EmbeddingArtifactStore] = None,
    ) -> None:
        self.encoder = encoder
        self.artifact_store = artifact_store or EmbeddingArtifactStore()
        self._encoders: Dict[str, EmbeddingEncoder] = {}

    def _encoder_for(self, model_name: str) -> EmbeddingEncoder:
        return get_embedding_encoder(
            model_name,
            override_encoder=self.encoder,
            cache=self._encoders,
        )

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(CellTextEmbedderInput, payload)
        encoder = self._encoder_for(input_data.model)
        vectors: List[List[float]] = []
        if not input_data.items:
            raise ModuleExecutionError("임베딩할 Excel 셀 문서가 없습니다")

        for start in range(0, len(input_data.items), input_data.batch_size):
            batch = input_data.items[start : start + input_data.batch_size]
            batch_vectors = encoder.encode([document.text for document in batch])
            if len(batch_vectors) != len(batch):
                raise ModuleExecutionError(
                    "Excel 셀 문서 개수와 생성된 임베딩 개수가 일치하지 않습니다"
                )
            vectors.extend(batch_vectors)

        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1 or not dimensions or 0 in dimensions:
            raise ModuleExecutionError("Excel 셀 문서 임베딩 차원이 일정하지 않습니다")
        dimension = dimensions.pop()
        artifact_payload = json.dumps(
            {
                "workbook_hash": input_data.workbook_hash,
                "model": input_data.model,
                "texts": [document.text for document in input_data.items],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        artifact_id = hashlib.sha256(artifact_payload.encode("utf-8")).hexdigest()
        self.artifact_store.put(artifact_id, vectors)

        return {
            "file_name": input_data.file_name,
            "workbook_hash": input_data.workbook_hash,
            "model": input_data.model,
            "artifact_id": artifact_id,
            "dimension": dimension,
            "items": [
                {
                    **document.model_dump(),
                    "embedding_index": index,
                }
                for index, document in enumerate(input_data.items)
            ],
        }
