from __future__ import annotations

from unittest.mock import MagicMock

from modules.common.base_module import DocumentContextDTO, QueryContextDTO
from modules.retrieval.context_expander import (
    PgContextExpanderConfigDTO,
    PgContextExpanderInputDTO,
    PgContextExpanderModule,
)
from modules.retrieval.rrf_fusion import RetrievalDTO, RrfCandidateDTO


def test_context_expander_batches_rows_per_sheet():
    mock_store = MagicMock()
    mock_store.fetch_rows_cells.return_value = {
        10: [
            {
                "col_index": 1,
                "column_header": ["2023"],
                "cell_value": "65670억",
                "cell_coord": "B10",
                "row_header": ["영업이익"],
            }
        ]
    }

    expander = PgContextExpanderModule(pgvector_store=mock_store)

    retrieval_dto = RetrievalDTO(
        query_context=QueryContextDTO(question_id="q1", question_text="영업이익"),
        document_context=DocumentContextDTO(
            file_name="samsung.xlsx",
            workbook_hash="h1",
            index_id="idx_1",
            sheet_names=["손익계산서"],
        ),
        items=[
            RrfCandidateDTO(
                rank=1,
                cell_id="samsung:IS:B10",
                rrf_score=0.9,
                text="영업이익: 65670억",
                matched_subquery="q",
            )
        ],
    )

    result = expander.execute(
        PgContextExpanderInputDTO(retrieval_json=retrieval_dto),
        config=PgContextExpanderConfigDTO(top_k=5, adjacent_radius=2),
    )

    assert "items" in result
    assert len(result["items"]) > 0
    assert result["metrics"]["top_k_used"] > 0
    assert mock_store.fetch_rows_cells.called
