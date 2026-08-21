import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional, cast

from pydantic import BaseModel, ConfigDict, Field

from backend.core.cost_tracker import calculate_embedding_cost
from backend.providers.embeddings.bge import DEFAULT_BGE_MODEL
from backend.providers.embeddings.factory import EmbeddingEncoder, get_embedding_encoder
from backend.storage.embedding_artifacts import EmbeddingArtifactStore

logger = logging.getLogger(__name__)
from modules.common.base_module import (
    ExecutableModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleTaskPolicy,
)
from modules.common.config import (
    DEFAULT_CELL_EMBEDDING_BATCH_SIZE,
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_MODEL_OPTIONS,
)
from modules.structure.cell_text_serializer import CellTextDocumentDTO, CellTextSerializerOutput


class CellTextEmbedderInputDTO(CellTextSerializerOutput):
    """Structured cell documents produced by a serializer."""


class CellTextEmbedderConfigDTO(ModuleConfigDTO):
    model: str = Field(
        default=DEFAULT_EMBEDDING_MODEL,
        min_length=1,
        description="Excel 셀 문서 임베딩에 사용할 OpenAI 3072차원 모델 ID",
        json_schema_extra={
            "enum": EMBEDDING_MODEL_OPTIONS,
            "options": EMBEDDING_MODEL_OPTIONS,
        },
    )
    batch_size: int = Field(
        default=DEFAULT_CELL_EMBEDDING_BATCH_SIZE,
        ge=1,
        le=2048,
        description="Excel 셀 문서를 한 번에 임베딩할 배치 크기",
    )


class CellTextEmbedderExecutionDTO(
    CellTextEmbedderInputDTO,
    CellTextEmbedderConfigDTO,
):
    """Internal union of document data and embedding settings."""


class EmbeddedCellTextDocumentDTO(CellTextDocumentDTO):
    embedding_index: int = Field(
        ge=0,
        description="외부 임베딩 아티팩트에서 이 셀 문서 벡터의 행 번호",
    )


class CellTextEmbeddingsDTO(ModuleDTO):
    model_config = ConfigDict(extra="forbid")
    file_name: str
    workbook_hash: str
    model: str = Field(description="문서 임베딩에 사용된 모델 ID")
    artifact_id: str = Field(
        pattern=r"^[a-f0-9]{64}$",
        description="float32 문서 벡터 아티팩트의 콘텐츠 주소",
    )
    dimension: int = Field(gt=0, description="각 문서 임베딩 벡터 차원")
    items: List[EmbeddedCellTextDocumentDTO]
    duration_seconds: Optional[float] = None
    total_tokens: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    estimated_cost_krw: Optional[float] = None
    batch_size: Optional[int] = None


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
        task=ModuleTaskPolicy(
            retries=2,
            retry_delay_seconds=5,
            timeout_seconds=3600,
            tags=["embedding"],
            resource_profile="high-memory",
        ),
    )
    input_model = CellTextEmbedderInputDTO
    config_model = CellTextEmbedderConfigDTO
    execution_model = CellTextEmbedderExecutionDTO
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
        """
        Embed cell documents and store their vectors as a content-addressed artifact.
        
        Parameters:
            payload (BaseModel): Execution data containing the documents, workbook metadata,
                embedding model, and batch size.
        
        Returns:
            Dict[str, Any]: Embedding metadata, artifact information, usage and cost
                estimates, and the input documents with embedding row indices.
        
        Raises:
            ModuleExecutionError: If no documents are provided, the encoder returns an
                incorrect number of vectors, or the vectors have inconsistent or zero
                dimensions.
        """
        input_data = cast(CellTextEmbedderExecutionDTO, payload)
        encoder = self._encoder_for(input_data.model)
        vectors: List[List[float]] = []
        if not input_data.items:
            raise ModuleExecutionError("임베딩할 Excel 셀 문서가 없습니다")

        start_perf = time.perf_counter()
        total_tokens = 0
        total_items = len(input_data.items)
        total_batches = max(1, (total_items + input_data.batch_size - 1) // input_data.batch_size)
        self.report_progress(
            {
                "phase": "embedding_batches",
                "completed_batches": 0,
                "total_batches": total_batches,
                "completed_items": 0,
                "total_items": total_items,
            }
        )

        for batch_idx, start in enumerate(range(0, total_items, input_data.batch_size), start=1):
            batch = input_data.items[start : start + input_data.batch_size]
            print(f"[CellTextEmbedder] 배치 {batch_idx}/{total_batches} ({len(batch)}개 문서) 임베딩 중...", flush=True)
            logger.info("임베딩 배치 %d/%d 실행 중 (%d개 문서, 모델: %s)...", batch_idx, total_batches, len(batch), input_data.model)
            batch_vectors = encoder.encode([document.text for document in batch])
            if len(batch_vectors) != len(batch):
                raise ModuleExecutionError(
                    "Excel 셀 문서 개수와 생성된 임베딩 개수가 일치하지 않습니다"
                )
            vectors.extend(batch_vectors)

            # Accumulate token usage
            if hasattr(encoder, "last_usage") and getattr(encoder, "last_usage", None):
                usage = getattr(encoder, "last_usage")
                total_tokens += usage.get("total_tokens", 0)
            else:
                # Estimate ~15 tokens per cell text for local models
                total_tokens += sum(max(1, len(doc.text.split()) * 2) for doc in batch)
            self.report_progress(
                {
                    "phase": "embedding_batches",
                    "completed_batches": batch_idx,
                    "total_batches": total_batches,
                    "completed_items": min(start + len(batch), total_items),
                    "total_items": total_items,
                }
            )

        duration_seconds = round(time.perf_counter() - start_perf, 3)
        cost_info = calculate_embedding_cost(input_data.model, total_tokens)

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
            "duration_seconds": duration_seconds,
            "total_tokens": total_tokens,
            "estimated_cost_usd": cost_info["cost_usd"],
            "estimated_cost_krw": cost_info["cost_krw"],
            "batch_size": input_data.batch_size,
            "items": [
                {
                    **document.model_dump(),
                    "embedding_index": index,
                }
                for index, document in enumerate(input_data.items)
            ],
        }
