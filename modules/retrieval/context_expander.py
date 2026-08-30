"""검색된 핵심 셀 좌표를 기반으로 PostgreSQL DB에서 해당 행(Row)의 전체 열(Column) 셀 다큐먼트를 확장 복원하는 모듈.

단일 셀 검색 결과에 대해 해당 셀이 속한 전체 행(Row)의 모든 열(과거 연도별 시계열 수치, 헤더 등)을
PostgreSQL에서 온디맨드로 일괄 조회하여 Reader LLM이 원본 행의 전체 맥락을 완벽히 이해할 수 있도록 셀 단위 원본 다큐먼트 텍스트 리스트로 확장합니다.

Example:
    Input DTO (입력 예시):
    ```json
    {
      "retrieval_input": {
        "query_context": {"question_id": "q-001", "question_text": "삼성전자 영업이익"},
        "document_context": {"file_name": "samsung_2023.xlsx", "workbook_hash": "a1b2c3d4..."},
        "items": [
          {"rank": 1, "cell_id": "삼성전자:손익계산서:C5", "score": 0.032, "text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65670", "matched_subquery": "..."}
        ]
      }
    }
    ```

    Output DTO (출력 예시):
    ```json
    {
      "query_context": {"question_id": "q-001", "question_text": "삼성전자 영업이익"},
      "document_context": {"file_name": "samsung_2023.xlsx", "workbook_hash": "a1b2c3d4..."},
      "items": [
        "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2021 | Cell Value: 516339",
        "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2022 | Cell Value: 433766",
        "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65670"
      ]
    }
    ```
"""

from __future__ import annotations

# ==============================================================================
# 1. Imports & Logger Setup
# ==============================================================================
import asyncio
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from openpyxl.utils.cell import coordinate_to_tuple
from pydantic import Field

from backend.storage.spreadsheets.structured_cell_text import (
    normalize_row_headers,
    resolved_cell_value,
    serialize_structured_cell,
)
from modules.common.base_module import (
    BaseModule,
    DocumentContextDTO,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleInputDTO,
    QueryContextDTO,
)
from modules.common.config import (
    DEFAULT_PG_CONTEXT_TOP_K,
    DEFAULT_PG_MAX_BLOCKS,
)
from modules.retrieval.ports import ContextExpansionStorePort
from modules.retrieval.rrf_fusion import RetrievalDTO

logger = logging.getLogger(__name__)

_STRUCTURED_FIELD_PATTERN = re.compile(
    r"(?:^|\|)\s*(Company|Sheet|Row Header|Column Header|Cell Value):\s*([^|]*)",
    re.IGNORECASE,
)


def _header_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [part.strip() for part in text.split(" > ") if part.strip()]


def _real_cell_value(value: Any) -> str:
    return resolved_cell_value(value) or ""


def _structured_fields(text: str) -> Dict[str, str]:
    return {key.casefold(): value.strip() for key, value in _STRUCTURED_FIELD_PATTERN.findall(text)}


def _canonical_source_text(
    cell: Dict[str, Any],
    *,
    fallback_company: str = "",
    fallback_sheet: str = "",
) -> str:
    """Render current and legacy cell records through the canonical five-field contract."""

    fields = _structured_fields(str(cell.get("source_text") or ""))
    value = _real_cell_value(cell.get("cell_value")) or _real_cell_value(fields.get("cell value"))
    if not value:
        return ""

    company = str(cell.get("company_name") or fields.get("company") or fallback_company).strip()
    sheet = str(cell.get("sheet_name") or fields.get("sheet") or fallback_sheet).strip()
    row_headers = _header_list(cell.get("row_header") or fields.get("row header"))
    row_headers = normalize_row_headers(row_headers, company_name=company)
    column_headers = _header_list(cell.get("column_header") or fields.get("column header"))
    return serialize_structured_cell(
        sheet,
        row_headers,
        column_headers,
        value,
        company_name=company,
    )


# ==============================================================================
# 2. DTOs & Item Models
# ==============================================================================
class ContextDTO(ModuleDTO):
    """Structured context output carrying full-row timeseries documents."""

    query_context: QueryContextDTO = Field(description="Reader까지 보존되는 원본 질문 컨텍스트")
    document_context: DocumentContextDTO = Field(
        description="컨텍스트 블록이 추출된 원본 문서 컨텍스트"
    )
    items: List[str] = Field(
        default_factory=list,
        description="Reader가 그대로 사용할 시트·행 단위 실제 셀 컨텍스트 블록 목록",
    )
    cells: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Reader 및 다운스트림에서 증거로 사용할 수 있는 확장 셀들의 메타데이터 목록",
    )


class PgContextExpanderInputDTO(ModuleInputDTO):
    """Input contract containing retrieved search results."""

    retrieval_json: RetrievalDTO = Field(
        description="RRF Fusion에서 전달되는 상위 결합 검색 후보 결과"
    )


class PgContextExpanderConfigDTO(ModuleConfigDTO):
    """Configuration contract for DB-level full-row column expansion."""

    top_k: int = Field(
        default=DEFAULT_PG_CONTEXT_TOP_K,
        gt=0,
        le=500,
        description="행 확장에 사용할 RRF 상위 후보 개수",
    )
    adjacent_radius: Optional[int] = Field(
        default=None,
        ge=0,
        le=20,
        description="선택적 인접 행 반경 (기본 단일 행 확장)",
    )
    max_blocks: int = Field(
        default=DEFAULT_PG_MAX_BLOCKS,
        gt=0,
        le=5000,
        description="LLM Reader로 전달할 최대 확장 셀 다큐먼트 개수",
    )


# ==============================================================================
# 3. Coordinate Helper Functions
# ==============================================================================
def _cell_identity_parts(cell_id: str) -> Tuple[str, str, str]:
    parts = cell_id.split(":")
    if len(parts) >= 3:
        return parts[0].strip(), parts[1].strip(), parts[2].strip()
    if len(parts) == 2:
        return "", parts[0].strip(), parts[1].strip()
    return "", "", parts[0].strip()


def _infer_sheet(cell_id: str, text: str) -> str:
    match = re.search(r"Sheet:\s*([^|]+)", text)
    if match:
        return match.group(1).strip()
    sheet_markers = {
        "Income_Statement": ("IS ", "Income_Statement"),
        "Balance_Sheet": ("BS ", "Balance_Sheet"),
        "Cash_Flow": ("CF ", "Cash_Flow"),
        "Key_Stats": ("KS ", "Key_Stats"),
    }
    return next(
        (
            sheet
            for sheet, markers in sheet_markers.items()
            if cell_id.startswith(markers[0]) or markers[1] in cell_id
        ),
        "",
    )


def _coordinate_indexes(coord: str) -> Tuple[Optional[int], Optional[int]]:
    match = re.search(r"([A-Za-z]+)(\d+)", coord)
    if match is None:
        return None, None
    try:
        return coordinate_to_tuple(match.group(0))
    except Exception:
        return int(match.group(2)), None


def _parse_cell_id_coords(
    cell_id: str, text: str = ""
) -> Tuple[str, str, Optional[int], Optional[int]]:
    """Parse candidate identity into company, sheet, row, and column."""
    company, sheet, coord = _cell_identity_parts(cell_id)

    if not sheet:
        sheet = _infer_sheet(cell_id, text)
    row_index, column_index = _coordinate_indexes(coord)
    return company, sheet, row_index, column_index


@dataclass
class _ContextAccumulator:
    blocks: List[str] = field(default_factory=list)
    seen_blocks: Set[str] = field(default_factory=set)
    cells: List[Dict[str, Any]] = field(default_factory=list)
    seen_coordinates: Set[Tuple[str, str]] = field(default_factory=set)
    fallbacks: List[Dict[str, Any]] = field(default_factory=list)

    def add_block(self, text: str) -> None:
        if text and text not in self.seen_blocks:
            self.seen_blocks.add(text)
            self.blocks.append(text)

    def add_cell(self, cell: Dict[str, Any]) -> None:
        key = (str(cell["sheet_name"]), str(cell["cell_coord"]))
        if key not in self.seen_coordinates:
            self.seen_coordinates.add(key)
            self.cells.append(cell)

    def add_fallbacks(self) -> None:
        for cell in self.fallbacks:
            self.add_cell(cell)


# ==============================================================================
# 4. Module Implementation
# ==============================================================================
class PgContextExpanderModule(BaseModule):
    """Directly queries PostgreSQL on-demand for full-row timeseries and header context."""

    definition = ModuleDefinition(
        type="pg_context_expander",
        label="PostgreSQL On-Demand Context Expander",
        category="Logic",
        description="RRF 상위 후보 셀에 대해 PostgreSQL DB에서 해당 행의 시계열 셀 및 헤더를 On-Demand로 직접 쿼리하여 제로카피 고속 컨텍스트를 생성합니다.",
        inputs=["retrieval_json"],
        outputs=["context_json"],
        config_fields=["top_k", "max_blocks"],
        raw_output=True,
        version="3",
    )
    input_model = PgContextExpanderInputDTO
    config_model = PgContextExpanderConfigDTO
    output_model = ContextDTO

    def __init__(self, pgvector_store: ContextExpansionStorePort) -> None:
        super().__init__()
        self.pgvector_store = pgvector_store

    @staticmethod
    def _target_rows(
        retrieval_items: List[Any],
        cfg: PgContextExpanderConfigDTO,
    ) -> Dict[Tuple[str, str], Set[int]]:
        target_rows_by_scope: Dict[Tuple[str, str], Set[int]] = defaultdict(set)
        for candidate in retrieval_items:
            _, sheet, row_index, _ = _parse_cell_id_coords(
                candidate.cell_id,
                candidate.text,
            )
            if candidate.index_id and sheet and row_index is not None:
                scope_key = (candidate.index_id, sheet)
                if cfg.adjacent_radius and cfg.adjacent_radius > 0:
                    for row in range(
                        max(1, row_index - cfg.adjacent_radius),
                        row_index + cfg.adjacent_radius + 1,
                    ):
                        target_rows_by_scope[scope_key].add(row)
                else:
                    target_rows_by_scope[scope_key].add(row_index)
        return target_rows_by_scope

    @staticmethod
    def _seed_context(
        retrieval_items: List[Any],
        fallback_company: str,
    ) -> _ContextAccumulator:
        accumulator = _ContextAccumulator()
        for candidate in retrieval_items:
            text = candidate.text.strip()
            _, sheet, _, _ = _parse_cell_id_coords(candidate.cell_id, candidate.text)
            coordinate_match = re.search(r"([A-Za-z]+)(\d+)", candidate.cell_id)
            coordinate = coordinate_match.group(0) if coordinate_match else ""
            canonical = _canonical_source_text(
                {"source_text": text},
                fallback_company=fallback_company,
                fallback_sheet=sheet,
            )
            if canonical:
                accumulator.add_block(canonical)
            elif text and not _structured_fields(text):
                accumulator.add_block(text)
            if canonical and sheet and coordinate:
                accumulator.fallbacks.append(
                    {
                        "cell_id": candidate.cell_id,
                        "sheet_name": sheet,
                        "cell_coord": coordinate,
                        "source_text": canonical,
                    }
                )
        return accumulator

    @staticmethod
    def _evidence_cell(
        cell: Dict[str, Any],
        *,
        raw_text: str,
        actual_value: str,
        fallback_sheet: str,
    ) -> Optional[Dict[str, Any]]:
        coordinate = str(cell.get("cell_coord") or "")
        sheet_name = str(cell.get("sheet_name") or fallback_sheet)
        if not (raw_text and actual_value and coordinate and sheet_name):
            return None
        return {
            "cell_id": cell.get("cell_id") or f"{sheet_name} Cell {coordinate}",
            "sheet_name": sheet_name,
            "cell_coord": coordinate,
            "source_text": raw_text,
            "cell_value": actual_value,
        }

    @classmethod
    def _consume_rows(
        cls,
        accumulator: _ContextAccumulator,
        rows: List[Dict[str, Any]],
        *,
        fallback_company: str,
        fallback_sheet: str,
        max_blocks: int,
    ) -> bool:
        ordered = sorted(
            rows,
            key=lambda value: (
                value.get("col_index") is None,
                value.get("col_index") or 0,
            ),
        )
        for cell in ordered:
            actual_value = _real_cell_value(cell.get("cell_value"))
            raw_text = _canonical_source_text(
                cell,
                fallback_company=fallback_company,
                fallback_sheet=fallback_sheet,
            )
            accumulator.add_block(raw_text)
            evidence = cls._evidence_cell(
                cell,
                raw_text=raw_text,
                actual_value=actual_value,
                fallback_sheet=fallback_sheet,
            )
            if evidence is not None:
                accumulator.add_cell(evidence)
            if len(accumulator.blocks) >= max_blocks:
                return True
        return False

    def _expand_targets(
        self,
        accumulator: _ContextAccumulator,
        targets: Dict[Tuple[str, str], Set[int]],
        *,
        prefetched_rows: Optional[Dict[Tuple[str, str], Dict[int, List[Dict[str, Any]]]]],
        fallback_company: str,
        max_blocks: int,
    ) -> None:
        for (collection_name, sheet), row_indices in targets.items():
            rows_by_index = (
                prefetched_rows.get((collection_name, sheet), {})
                if prefetched_rows is not None
                else self.pgvector_store.fetch_rows_cells(
                    collection_name=collection_name,
                    workbook_hash=None,
                    sheet_name=sheet,
                    row_indices=sorted(row_indices),
                    limit_per_row=100,
                )
            )
            for row_index in sorted(row_indices):
                if self._consume_rows(
                    accumulator,
                    rows_by_index.get(row_index, []),
                    fallback_company=fallback_company,
                    fallback_sheet=sheet,
                    max_blocks=max_blocks,
                ):
                    break

    def execute(
        self,
        input_data: PgContextExpanderInputDTO,
        config: Optional[PgContextExpanderConfigDTO] = None,
    ) -> Dict[str, Any]:
        return self._render(input_data, config, None)

    def _render(
        self,
        input_data: PgContextExpanderInputDTO,
        config: Optional[PgContextExpanderConfigDTO],
        prefetched_rows: Optional[Dict[Tuple[str, str], Dict[int, List[Dict[str, Any]]]]],
    ) -> Dict[str, Any]:
        cfg = config or PgContextExpanderConfigDTO()
        retrieval_items = input_data.retrieval_json.items[: cfg.top_k]
        query_context_dict = input_data.retrieval_json.query_context.model_dump(mode="json")
        doc_context_dict = input_data.retrieval_json.document_context.model_dump(mode="json")

        if not retrieval_items:
            return {
                "query_context": query_context_dict,
                "document_context": doc_context_dict,
                "items": ["[No context blocks available]"],
            }

        fallback_company = str(doc_context_dict.get("company_name") or "")
        accumulator = self._seed_context(retrieval_items, fallback_company)
        self._expand_targets(
            accumulator,
            self._target_rows(retrieval_items, cfg),
            prefetched_rows=prefetched_rows,
            fallback_company=fallback_company,
            max_blocks=cfg.max_blocks,
        )
        # Header-only retrieval candidates never enter fallbacks because their
        # canonical source text has no concrete cell value.
        accumulator.add_fallbacks()
        context_blocks = accumulator.blocks[: cfg.max_blocks] or ["[No context blocks available]"]

        return {
            "query_context": query_context_dict,
            "document_context": doc_context_dict,
            "items": context_blocks,
            "cells": accumulator.cells,
        }

    async def execute_async(
        self,
        input_data: PgContextExpanderInputDTO,
        config: Optional[PgContextExpanderConfigDTO] = None,
    ) -> Dict[str, Any]:
        cfg = config or PgContextExpanderConfigDTO()
        retrieval_items = input_data.retrieval_json.items[: cfg.top_k]
        targets = self._target_rows(retrieval_items, cfg)
        tasks: Dict[
            Tuple[str, str],
            asyncio.Task[Dict[int, List[Dict[str, Any]]]],
        ] = {}
        async with asyncio.TaskGroup() as task_group:
            tasks = {
                (collection_name, sheet): task_group.create_task(
                    self.pgvector_store.fetch_rows_cells_async(
                        collection_name=collection_name,
                        workbook_hash=None,
                        sheet_name=sheet,
                        row_indices=sorted(row_indices),
                        limit_per_row=100,
                    ),
                    name=f"context-rows:{collection_name}:{sheet}",
                )
                for (collection_name, sheet), row_indices in targets.items()
            }
        prefetched_rows = {scope: task.result() for scope, task in tasks.items()}
        return self._render(input_data, cfg, prefetched_rows)


# ==============================================================================
# 5. Exports
# ==============================================================================
__all__ = [
    "ContextDTO",
    "DocumentContextDTO",
    "PgContextExpanderConfigDTO",
    "PgContextExpanderInputDTO",
    "PgContextExpanderModule",
    "QueryContextDTO",
]
