"""직렬화된 엑셀 셀 텍스트 목록을 배치 임베딩하여 바이너리 아티팩트로 저장하는 인덱싱 모듈.

CellTextSerializer로부터 생성된 직렬화 셀 텍스트들을 배치 단위로 OpenAI 또는 로컬 임베딩 모델에 전달하고,
고밀도 Float32 바이너리 아티팩트 파일(`data/artifacts/embeddings/`)로 안전하게 디스크에 직렬화 저장합니다.

Example:
    Input DTO (입력 예시):
    ```json
    {
      "file_name": "samsung_2023.xlsx",
      "workbook_hash": "a1b2c3d4...",
      "company_name": "삼성전자",
      "items": [
        {
          "cell_id": "C5",
          "sheet_name": "손익계산서",
          "cell_coord": "C5",
          "row_header": ["영업이익"],
          "column_header": ["2023"],
          "cell_value": "65670",
          "variant": "header_with_value",
          "text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65670"
        }
      ]
    }
    ```

    Output DTO (출력 예시):
    ```json
    {
      "file_name": "samsung_2023.xlsx",
      "workbook_hash": "a1b2c3d4...",
      "company_name": "삼성전자",
      "model": "text-embedding-3-large",
      "artifact_id": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      "dimension": 3072,
      "items": [
        {
          "cell_id": "C5",
          "sheet_name": "손익계산서",
          "cell_coord": "C5",
          "row_header": ["영업이익"],
          "column_header": ["2023"],
          "cell_value": "65670",
          "variant": "header_with_value",
          "text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65670",
          "embedding_index": 0
        }
      ],
      "duration_seconds": 0.15,
      "total_tokens": 45,
      "estimated_cost_usd": 0.00005,
      "cache_hit": false
    }
    ```
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field

from backend.domains.data_sources.application.shard_coordinator import IngestionShardCoordinator
from backend.domains.data_sources.infrastructure.filesystem.embedding_artifacts import (
    EmbeddingArtifactStore,
)
from backend.shared.application.embeddings import EmbeddingEncoder
from modules.common.base_embedder import (
    BaseEmbeddingModule,
    EmbeddingConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleTaskPolicy,
    calculate_embedding_cost,
)
from modules.common.config import DEFAULT_CELL_EMBEDDING_BATCH_SIZE
from modules.structure.cell_text_serializer import CellTextDocumentDTO, CellTextSerializerOutput

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. Excel Cell Text Document Embedder DTOs
# ==============================================================================

class CellTextEmbedderInputDTO(CellTextSerializerOutput):
    """Structured cell documents produced by a serializer."""


class CellTextEmbedderConfigDTO(EmbeddingConfigDTO):
    batch_size: int = Field(
        default=DEFAULT_CELL_EMBEDDING_BATCH_SIZE,
        ge=1,
        le=2048,
        description="Excel 셀 문서를 한 번에 임베딩할 배치 크기",
    )


class EmbeddedCellTextDocumentDTO(CellTextDocumentDTO):
    embedding_index: int = Field(
        ge=0,
        description="외부 임베딩 아티팩트에서 이 셀 문서 벡터의 행 번호",
    )


class CellTextEmbeddingsDTO(ModuleDTO):
    model_config = ConfigDict(extra="forbid")
    file_name: str
    workbook_hash: str
    company_name: Optional[str] = Field(
        default=None,
        description="알려진 경우 직렬화 문서에 포함할 공식 기업명",
    )
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
    cache_hit: bool = Field(
        default=False,
        description="동일 콘텐츠/모델 임베딩 아티팩트 재사용 여부",
    )


# ==============================================================================
# 2. Cell Text Embedder Module
# ==============================================================================

class CellTextEmbedderModule(BaseEmbeddingModule):
    """Embeds serialized Excel cell text documents in batches for data ingestion / indexing."""

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
            timeout_seconds=21600,
            tags=["embedding"],
            resource_profile="high-memory",
        ),
    )
    input_model = CellTextEmbedderInputDTO
    config_model = CellTextEmbedderConfigDTO
    output_model = CellTextEmbeddingsDTO

    def __init__(
        self,
        encoder: EmbeddingEncoder,
        artifact_store: EmbeddingArtifactStore,
        storage_sink: Optional[Any] = None,
        shard_coordinator: IngestionShardCoordinator | None = None,
    ) -> None:
        super().__init__(encoder=encoder)
        self.artifact_store = artifact_store
        self.storage_sink = storage_sink
        self.shard_coordinator = shard_coordinator

    def execute(
        self,
        input_data: CellTextEmbedderInputDTO,
        config: Optional[CellTextEmbedderConfigDTO] = None,
    ) -> Dict[str, Any]:
        """
        Embed cell documents and store their vectors as a content-addressed artifact.
        """
        cfg = config or CellTextEmbedderConfigDTO()

        if not input_data.items:
            raise ModuleExecutionError("임베딩할 Excel 셀 문서가 없습니다")

        model_name = self.resolve_model(cfg)
        expected_dimension = self.resolve_dimension(model_name=model_name, config=cfg)
        batch_size = self.resolve_batch_size(config=cfg, default=DEFAULT_CELL_EMBEDDING_BATCH_SIZE)

        texts = [document.text for document in input_data.items]
        artifact_hasher = hashlib.sha256()
        for identity_part in (
            input_data.workbook_hash,
            model_name,
            str(expected_dimension),
        ):
            encoded_part = identity_part.encode("utf-8")
            artifact_hasher.update(len(encoded_part).to_bytes(8, "big"))
            artifact_hasher.update(encoded_part)
        for text in texts:
            encoded_text = text.encode("utf-8")
            artifact_hasher.update(len(encoded_text).to_bytes(8, "big"))
            artifact_hasher.update(encoded_text)
        artifact_id = artifact_hasher.hexdigest()
        cache_hit = self.artifact_store.is_valid(
            artifact_id,
            len(texts),
            expected_dimension,
        )

        def _handle_batch_complete(batch_vecs: List[List[float]], start_idx: int, end_idx: int) -> None:
            if self.storage_sink is not None and callable(self.storage_sink):
                self.storage_sink(input_data.items[start_idx:end_idx], batch_vecs, start_idx, end_idx)

        if cache_hit:
            self.last_model = model_name
            self.last_dimension = expected_dimension
            self.last_duration_seconds = 0.0
            self.last_total_tokens = 0
            if self.storage_sink is not None and callable(self.storage_sink):
                start = 0
                for batch_vectors in self.artifact_store.iter_batches(
                    artifact_id,
                    len(texts),
                    expected_dimension,
                    batch_size,
                ):
                    end = start + len(batch_vectors)
                    _handle_batch_complete(batch_vectors, start, end)
                    start = end
        elif self.shard_coordinator is not None and self.shard_coordinator.enabled:
            distributed = self.shard_coordinator.embed(
                artifact_id=artifact_id,
                items=[document.model_dump(mode="json") for document in input_data.items],
                model_name=model_name,
                dimension=expected_dimension,
                batch_size=batch_size,
                progress_callback=self.report_progress,
            )
            self.last_model = model_name
            self.last_dimension = expected_dimension
            self.last_duration_seconds = distributed.duration_seconds
            self.last_total_tokens = distributed.total_tokens
            self.last_usage = {
                "total_tokens": distributed.total_tokens,
                "prompt_tokens": distributed.total_tokens,
                "worker_seconds": distributed.worker_seconds,
                "shard_count": distributed.shard_count,
            }
        else:
            vector_batches = (
                batch_vectors
                for _, _, batch_vectors in self.encode_batches_streaming(
                    texts=texts,
                    model_name=model_name,
                    expected_dimension=expected_dimension,
                    batch_size=batch_size,
                    on_batch_complete=_handle_batch_complete,
                    report_progress=True,
                )
            )
            self.artifact_store.put_streaming(
                artifact_id,
                vector_batches,
                expected_count=len(texts),
                dimension=expected_dimension,
            )

        cost_info = calculate_embedding_cost(model_name, self.last_total_tokens)
        dimension = self.last_dimension or expected_dimension

        return {
            "file_name": input_data.file_name,
            "workbook_hash": input_data.workbook_hash,
            "company_name": input_data.company_name,
            "model": model_name,
            "artifact_id": artifact_id,
            "dimension": dimension,
            "duration_seconds": self.last_duration_seconds,
            "total_tokens": self.last_total_tokens,
            "estimated_cost_usd": cost_info["cost_usd"],
            "estimated_cost_krw": cost_info["cost_krw"],
            "batch_size": batch_size,
            "cache_hit": cache_hit,
            "items": [
                {
                    **document.model_dump(),
                    "embedding_index": index,
                }
                for index, document in enumerate(input_data.items)
            ],
        }


__all__ = [
    "CellTextEmbedderConfigDTO",
    "CellTextEmbedderInputDTO",
    "CellTextEmbedderModule",
    "CellTextEmbeddingsDTO",
    "EmbeddedCellTextDocumentDTO",
]
