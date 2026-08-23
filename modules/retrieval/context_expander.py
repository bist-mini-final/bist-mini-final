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
import logging
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from openpyxl.utils.cell import coordinate_to_tuple
from pydantic import Field

from backend.storage.pgvector_store import PgVectorStore
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
from modules.retrieval.rrf_fusion import RetrievalDTO

logger = logging.getLogger(__name__)


# ==============================================================================
# 2. DTOs & Item Models
# ==============================================================================
class ContextDTO(ModuleDTO):
    """Structured context output carrying full-row timeseries documents."""

    query_context: QueryContextDTO = Field(
        description="Reader까지 보존되는 원본 질문 컨텍스트"
    )
    document_context: DocumentContextDTO = Field(
        description="컨텍스트 블록이 추출된 원본 문서 컨텍스트"
    )
    items: List[str] = Field(
        default_factory=list,
        description="Reader가 그대로 사용할 시트·행 단위 실제 셀 컨텍스트 블록 목록",
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
def _parse_cell_id_coords(cell_id: str, text: str = "") -> Tuple[str, str, Optional[int], Optional[int]]:
    """Parses cell_id string and candidate text into (company, sheet_name, row_idx, col_idx)."""
    company = ""
    sheet = ""
    coord = ""

    parts = cell_id.split(":")
    if len(parts) >= 3:
        company = parts[0].strip()
        sheet = parts[1].strip()
        coord = parts[2].strip()
    elif len(parts) == 2:
        sheet = parts[0].strip()
        coord = parts[1].strip()
    else:
        coord = parts[0].strip()

    # If sheet is not in cell_id, extract from candidate text (e.g. "Sheet: Income_Statement | ...")
    if not sheet and text:
        match_sheet = re.search(r"Sheet:\s*([^|]+)", text)
        if match_sheet:
            sheet = match_sheet.group(1).strip()

    # Fallback to standard sheet prefixes if still empty
    if not sheet:
        if cell_id.startswith("IS ") or "Income_Statement" in cell_id:
            sheet = "Income_Statement"
        elif cell_id.startswith("BS ") or "Balance_Sheet" in cell_id:
            sheet = "Balance_Sheet"
        elif cell_id.startswith("CF ") or "Cash_Flow" in cell_id:
            sheet = "Cash_Flow"
        elif cell_id.startswith("KS ") or "Key_Stats" in cell_id:
            sheet = "Key_Stats"

    row_idx = None
    col_idx = None
    if coord:
        match = re.search(r"([A-Za-z]+)(\d+)", coord)
        if match:
            try:
                r_tuple, c_tuple = coordinate_to_tuple(match.group(0))
                row_idx = r_tuple
                col_idx = c_tuple
            except Exception:
                row_idx = int(match.group(2))

    return company, sheet, row_idx, col_idx


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
        version="2",
    )
    input_model = PgContextExpanderInputDTO
    config_model = PgContextExpanderConfigDTO
    output_model = ContextDTO

    def __init__(self, pgvector_store: PgVectorStore) -> None:
        super().__init__()
        self.pgvector_store = pgvector_store

    def execute(
        self,
        input_data: PgContextExpanderInputDTO,
        config: Optional[PgContextExpanderConfigDTO] = None,
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

        # Step 1: Collect candidate cell texts and extract sheet + row targets
        context_blocks: List[str] = []
        seen_blocks: Set[str] = set()

        for candidate in retrieval_items:
            t = candidate.text.strip()
            if t and t not in seen_blocks:
                seen_blocks.add(t)
                context_blocks.append(t)

        # Step 2: Target the exact rows for all candidate cells
        target_rows_by_scope: Dict[Tuple[str, str], Set[int]] = defaultdict(set)
        for candidate in retrieval_items:
            _, sheet, r_idx, _ = _parse_cell_id_coords(candidate.cell_id, candidate.text)
            if candidate.index_id and sheet and r_idx is not None:
                scope_key = (candidate.index_id, sheet)
                if cfg.adjacent_radius and cfg.adjacent_radius > 0:
                    radius = cfg.adjacent_radius
                    for r in range(max(1, r_idx - radius), r_idx + radius + 1):
                        target_rows_by_scope[scope_key].add(r)
                else:
                    target_rows_by_scope[scope_key].add(r_idx)

        if target_rows_by_scope:
            for (collection_name, sheet), row_indices in target_rows_by_scope.items():
                rows_by_index = self.pgvector_store.fetch_rows_cells(
                    collection_name=collection_name,
                    workbook_hash=None,
                    sheet_name=sheet,
                    row_indices=sorted(row_indices),
                    limit_per_row=100,
                )
                for r_idx in sorted(row_indices):
                    rows = rows_by_index.get(r_idx, [])
                    if not rows:
                        continue

                    for cell in sorted(
                        rows,
                        key=lambda value: (
                            value.get("col_index") is None,
                            value.get("col_index") or 0,
                        ),
                    ):
                        raw_text = (cell.get("source_text") or "").strip()
                        actual_value = str(cell.get("cell_value") or "").strip()
                        if raw_text and actual_value and actual_value != "?":
                            raw_text = re.sub(
                                r"Cell Value:\s*\?(?=\s*(?:\||$))",
                                f"Cell Value: {actual_value}",
                                raw_text,
                            )
                        if not raw_text:
                            c_name = cell.get("company_name") or doc_context_dict.get("company_name", "")
                            s_name = cell.get("sheet_name") or sheet
                            rh = (
                                " > ".join(cell["row_header"])
                                if isinstance(cell.get("row_header"), list)
                                else str(cell.get("row_header") or "")
                            )
                            ch = (
                                " > ".join(cell["column_header"])
                                if isinstance(cell.get("column_header"), list)
                                else str(cell.get("column_header") or "")
                            )
                            val = actual_value
                            parts = []
                            if c_name:
                                parts.append(f"Company: {c_name}")
                            if s_name:
                                parts.append(f"Sheet: {s_name}")
                            if rh:
                                parts.append(f"Row Header: {rh}")
                            if ch:
                                parts.append(f"Column Header: {ch}")
                            if val:
                                parts.append(f"Cell Value: {val}")
                            raw_text = " | ".join(parts)

                        if raw_text and raw_text not in seen_blocks:
                            seen_blocks.add(raw_text)
                            context_blocks.append(raw_text)

                        if len(context_blocks) >= cfg.max_blocks:
                            break
                    if len(context_blocks) >= cfg.max_blocks:
                        break

        context_blocks = context_blocks[: cfg.max_blocks]
        if not context_blocks:
            context_blocks = ["[No context blocks available]"]

        return {
            "query_context": query_context_dict,
            "document_context": doc_context_dict,
            "items": context_blocks,
        }


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
