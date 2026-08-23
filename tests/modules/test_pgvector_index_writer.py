from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.storage.embedding_artifacts import EmbeddingArtifactStore
from modules.storage.pgvector_index_writer import PgVectorIndexWriterModule


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


def test_pgvector_writer_execution(tmp_path: Path) -> None:
    artifact_store = EmbeddingArtifactStore(tmp_path / "vectors")
    artifact_id = "a" * 64
    artifact_store.put(artifact_id, [[0.1, 0.2], [0.3, 0.4]])
    db_manager = MagicMock()
    pgvector_store = MagicMock()
    module = PgVectorIndexWriterModule(
        artifact_store=artifact_store,
        db_manager=db_manager,
        pgvector_store=pgvector_store,
        processed_dir=tmp_path,
    )

    result = module.run(
        {
            "file_name": "sample.xlsx",
            "workbook_hash": "b" * 64,
            "model": "custom-2d",
            "artifact_id": artifact_id,
            "dimension": 2,
            "items": [
                {**item, "embedding_index": index}
                for index, item in enumerate(_serialized_items())
            ],
        }
    )

    assert result["index_id"] == f"idx_{artifact_id}"
    vectors = pgvector_store.put_documents.call_args.kwargs["vectors"]
    assert vectors[0] == pytest.approx([0.1, 0.2])
    assert len(vectors) == 2
    db_manager.save_source_file.assert_called_once()
