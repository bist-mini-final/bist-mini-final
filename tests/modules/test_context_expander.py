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
        config=PgContextExpanderConfigDTO(top_k=5),
    )

    assert "items" in result
    assert len(result["items"]) == 2
    assert mock_store.fetch_rows_cells.called


def test_context_expander_preserves_raw_document_texts():
    mock_store = MagicMock()
    mock_store.fetch_rows_cells.return_value = {
        5: [
            {
                "col_index": 1,
                "column_header": ["2022"],
                "cell_value": "433766",
                "cell_coord": "B5",
                "row_header": ["영업이익"],
                "source_text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2022 | Cell Value: 433766",
            },
            {
                "col_index": 2,
                "column_header": ["2023"],
                "cell_value": "65670",
                "cell_coord": "C5",
                "row_header": ["영업이익"],
                "source_text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65670",
            },
        ]
    }

    expander = PgContextExpanderModule(pgvector_store=mock_store)

    retrieval_dto = RetrievalDTO(
        query_context=QueryContextDTO(question_id="q1", question_text="2023년 삼성전자 영업이익"),
        document_context=DocumentContextDTO(
            file_name="samsung.xlsx",
            workbook_hash="h1",
            index_id="samsung_idx",
            company_name="삼성전자",
            sheet_names=["손익계산서"],
        ),
        items=[
            RrfCandidateDTO(
                rank=1,
                cell_id="삼성전자:손익계산서:C5",
                rrf_score=0.95,
                text="Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65670",
                matched_subquery="영업이익",
            )
        ],
    )

    result = expander.execute(
        PgContextExpanderInputDTO(retrieval_json=retrieval_dto),
        config=PgContextExpanderConfigDTO(top_k=10, max_blocks=100),
    )

    items = result["items"]
    # Candidate text is identical to row 5 col 2, so deduplication keeps 2 unique raw documents
    assert len(items) == 2
    assert "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2022 | Cell Value: 433766" in items
    assert "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65670" in items


