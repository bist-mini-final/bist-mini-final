"""Module for expanding retrieved cell contexts into continuous time-series rows."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, DefaultDict, Dict, List, Optional, Set, Tuple, cast

from pydantic import BaseModel, Field

from .base import (
    ExecutableModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleExecutionError,
    ModuleInputDTO,
)
from .cell_text_serializer import CellTextDocumentDTO, CellTextSerializerOutput
from .context_expander import ContextDTO, coordinate_to_tuple
from .retrieval_models import RetrievalDTO

logger = logging.getLogger(__name__)


class TimeseriesContextExpanderInputDTO(ModuleInputDTO):
    retrieval_json: RetrievalDTO = Field(
        description="RRF 융합 검색 결과 DTO"
    )
    document_input: CellTextSerializerOutput = Field(
        description="Excel 구조화 셀 문서 입력 포트"
    )


class TimeseriesContextExpanderConfigDTO(ModuleConfigDTO):
    top_k: int = Field(
        default=100,
        gt=0,
        le=500,
        description="확장할 상위 RRF 후보 수",
    )
    expand_full_row: bool = Field(
        default=True,
        description="Row Header 매칭 시 해당 행의 전체 연도 컬럼 셀을 연속 시계열로 확장할지 여부",
    )
    adjacent_radius: int = Field(
        default=2,
        ge=0,
        le=5,
        description="인접 행 추가 확장 반경",
    )
    max_blocks: int = Field(
        default=500,
        gt=0,
        le=2000,
        description="생성할 최대 컨텍스트 블록 수",
    )


class TimeseriesContextExpanderExecutionDTO(
    TimeseriesContextExpanderInputDTO, TimeseriesContextExpanderConfigDTO
):
    """Execution DTO for TimeseriesContextExpanderModule."""


class TimeseriesContextExpanderModule(ExecutableModule):
    definition = ModuleDefinition(
        type="timeseries_context_expander",
        label="Time-Series Full-Row Context Expander",
        category="Logic",
        description="검색된 셀의 행(Row)을 감지하여 전체 연도 컬럼을 연속 시계열 테이블로 자동 확장합니다.",
        inputs=["retrieval_json", "document_input"],
        outputs=["context_json"],
        config_fields=["top_k", "expand_full_row", "adjacent_radius", "max_blocks"],
        raw_output=True,
        version="1",
    )
    input_model = TimeseriesContextExpanderInputDTO
    config_model = TimeseriesContextExpanderConfigDTO
    execution_model = TimeseriesContextExpanderExecutionDTO
    output_model = ContextDTO

    def _safe_coord(self, coord: str, fallback_row: int) -> Tuple[int, int]:
        try:
            return coordinate_to_tuple(coord)
        except Exception:
            return fallback_row, 1

    def _format_time_series_row(
        self, sheet_name: str, row_headers: List[str], docs: List[CellTextDocumentDTO]
    ) -> str:
        row_title = " > ".join(row_headers) if row_headers else "Row Data"
        sorted_docs = sorted(
            docs,
            key=lambda d: (" > ".join(d.column_header) if d.column_header else d.cell_coord),
        )
        time_series_entries = [
            f"[{' > '.join(d.column_header) if d.column_header else d.cell_coord}: {d.cell_value or d.text}] (Cell {d.cell_coord})"
            for d in sorted_docs
        ]
        return (
            f"[Sheet: {sheet_name}]\n"
            f"Row Header: {row_title}\n"
            f"Time Series Cells: " + ", ".join(time_series_entries)
        )

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(TimeseriesContextExpanderExecutionDTO, payload)
        documents = input_data.document_input.items
        candidates = input_data.retrieval_json.items[: input_data.top_k]

        q_context = input_data.retrieval_json.query_context
        doc_context = input_data.retrieval_json.document_context

        if not candidates or not documents:
            raise ModuleExecutionError("컨텍스트를 확장할 문서 또는 RRF 후보가 없습니다")

        # Prefer header_with_value over header_only for duplicate cell_ids
        doc_by_cell_id: Dict[str, CellTextDocumentDTO] = {}
        for doc in documents:
            existing = doc_by_cell_id.get(doc.cell_id)
            if existing is None:
                doc_by_cell_id[doc.cell_id] = doc
            elif existing.variant == "header_only" and doc.variant == "header_with_value":
                doc_by_cell_id[doc.cell_id] = doc

        rows: DefaultDict[Tuple[str, int], List[CellTextDocumentDTO]] = defaultdict(list)
        row_headers: Dict[Tuple[str, int], List[str]] = {}

        for index, document in enumerate(documents):
            row, _ = self._safe_coord(document.cell_coord, index + 1)
            row_key = (document.sheet_name, row)
            rows[row_key].append(document)
            row_headers.setdefault(row_key, document.row_header)

        matched_count = 0

        if input_data.expand_full_row:
            expanded_rows: List[Tuple[str, int]] = []
            seen_rows: Set[Tuple[str, int]] = set()

            for index, candidate in enumerate(candidates):
                document = doc_by_cell_id.get(candidate.cell_id)
                if document is None:
                    continue
                matched_count += 1
                candidate_row, _ = self._safe_coord(document.cell_coord, index + 1)

                for offset in range(-input_data.adjacent_radius, input_data.adjacent_radius + 1):
                    row_key = (document.sheet_name, candidate_row + offset)
                    if row_key in rows and row_key not in seen_rows:
                        seen_rows.add(row_key)
                        expanded_rows.append(row_key)

            if matched_count == 0:
                raise ModuleExecutionError("RRF 후보 Cell ID가 Structured Cell Text에 존재하지 않습니다")

            context_blocks = [
                self._format_time_series_row(
                    sheet_name,
                    row_headers.get((sheet_name, row), []),
                    rows[(sheet_name, row)],
                )
                for sheet_name, row in expanded_rows[: input_data.max_blocks]
            ]
        else:
            # Expand only candidate individual cells (or adjacent cells within radius)
            seen_cells: Set[str] = set()
            context_blocks = []
            for index, candidate in enumerate(candidates):
                document = doc_by_cell_id.get(candidate.cell_id)
                if document is None:
                    continue
                matched_count += 1
                candidate_row, _ = self._safe_coord(document.cell_coord, index + 1)
                for offset in range(-input_data.adjacent_radius, input_data.adjacent_radius + 1):
                    row_key = (document.sheet_name, candidate_row + offset)
                    for d in rows.get(row_key, []):
                        if d.cell_id not in seen_cells:
                            seen_cells.add(d.cell_id)
                            context_blocks.append(
                                f"[Sheet: {d.sheet_name}] {' > '.join(d.row_header)} | "
                                f"{' > '.join(d.column_header)}: {d.cell_value or d.text} (Cell {d.cell_coord})"
                            )
                if len(context_blocks) >= input_data.max_blocks:
                    break

            if matched_count == 0:
                raise ModuleExecutionError("RRF 후보 Cell ID가 Structured Cell Text에 존재하지 않습니다")

        if not context_blocks:
            raise ModuleExecutionError("인접 행 확장 결과가 비어 있습니다")

        context_text = "\n\n".join(context_blocks)

        return {
            "context_json": {
                "query_context": q_context.model_dump(mode="json"),
                "document_context": doc_context.model_dump(mode="json"),
                "top_k_used": matched_count,
                "adjacent_radius": input_data.adjacent_radius,
                "context_characters": len(context_text),
                "context_blocks": context_blocks,
                "block_count": len(context_blocks),
            }
        }
