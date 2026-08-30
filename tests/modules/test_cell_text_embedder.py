from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from backend.storage.data_sources.shard_coordinator import DistributedEmbeddingResult
from backend.storage.embedding_artifacts import EmbeddingArtifactStore
from modules.common.base_embedder import calculate_embedding_cost
from modules.embedding.cell_text_embedder import (
    CellTextEmbedderConfigDTO,
    CellTextEmbedderInputDTO,
    CellTextEmbedderModule,
)


def _serialized_items() -> list[dict]:
    return [
        {
            "cell_id": "IS Cell B2",
            "sheet_name": "IS",
            "cell_coord": "B2",
            "row_header": ["Revenue"],
            "column_header": ["FY2024"],
            "cell_value": "100",
            "variant": "header_with_value",
            "text": "Company: ? | Sheet: IS | Row Header: Revenue | Column Header: FY2024 | Cell Value: 100",
        },
        {
            "cell_id": "IS Cell C2",
            "sheet_name": "IS",
            "cell_coord": "C2",
            "row_header": ["Revenue"],
            "column_header": ["FY2025"],
            "cell_value": "120",
            "variant": "header_with_value",
            "text": "Company: ? | Sheet: IS | Row Header: Revenue | Column Header: FY2025 | Cell Value: 120",
        },
    ]


def test_cell_embedder_streams_and_reuses_artifact(tmp_path: Path) -> None:
    encoder = MagicMock()
    encoder.encode.side_effect = [
        [[0.1, 0.2], [0.3, 0.4]],
        [[0.5, 0.6]],
    ]
    artifact_store = EmbeddingArtifactStore(tmp_path)
    module = CellTextEmbedderModule(encoder=encoder, artifact_store=artifact_store)
    input_data = CellTextEmbedderInputDTO.model_validate(
        {
            "file_name": "sample.xlsx",
            "workbook_hash": "w" * 64,
            "items": [*_serialized_items(), {**_serialized_items()[0], "cell_id": "IS Cell D2", "cell_coord": "D2"}],
        }
    )
    config = CellTextEmbedderConfigDTO(model="custom-2d", dimension=2, batch_size=2)

    first = module.run(input_data, config)
    second = module.run(input_data, config)

    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert encoder.encode.call_count == 2
    assert artifact_store.is_valid(first["artifact_id"], 3, 2)


def test_embedding_cost_uses_model_specific_rate() -> None:
    assert calculate_embedding_cost("text-embedding-3-small", 1_000_000)[
        "cost_usd"
    ] == 0.02
    assert calculate_embedding_cost("text-embedding-3-large", 1_000_000)[
        "cost_usd"
    ] == 0.13


def test_cell_embedder_delegates_to_kubernetes_shards(tmp_path: Path) -> None:
    encoder = MagicMock()
    coordinator = MagicMock()
    coordinator.enabled = True
    coordinator.embed.return_value = DistributedEmbeddingResult(
        duration_seconds=1.25,
        worker_seconds=3.5,
        total_tokens=42,
        shard_count=2,
    )
    artifact_store = EmbeddingArtifactStore(tmp_path)
    module = CellTextEmbedderModule(
        encoder=encoder,
        artifact_store=artifact_store,
        shard_coordinator=coordinator,
    )

    result = module.run(
        {
            "file_name": "sample.xlsx",
            "workbook_hash": "w" * 64,
            "items": _serialized_items(),
        },
        {"model": "custom-2d", "dimension": 2, "batch_size": 1},
    )

    assert result["total_tokens"] == 42
    assert result["duration_seconds"] == 1.25
    coordinator.embed.assert_called_once()
    encoder.encode.assert_not_called()
