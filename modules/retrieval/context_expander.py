"""PostgreSQL On-Demand Context Expander directly querying timeseries and header context."""

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
    DEFAULT_PG_ADJACENT_RADIUS,
    DEFAULT_PG_CONTEXT_TOP_K,
    DEFAULT_PG_MAX_BLOCKS,
)
from modules.retrieval.rrf_fusion import RetrievalDTO

logger = logging.getLogger(__name__)


# ==============================================================================
# 2. DTOs & Item Models
# ==============================================================================
class ContextDTO(ModuleDTO):
    """Structured context output carrying adjacent rows and timeseries blocks."""

    query_context: QueryContextDTO = Field(
        description="Reader까지 보존되는 원본 질문 컨텍스트"
    )
    document_context: DocumentContextDTO = Field(
        description="컨텍스트 블록이 추출된 원본 문서 컨텍스트"
    )
    top_k_used: int = Field(gt=0, description="확장에 실제 사용한 RRF 후보 수")
    adjacent_radius: int = Field(ge=0, description="검색 셀 기준 인접 행 확장 반경")
    context_characters: int = Field(ge=0, description="전체 컨텍스트 문자 수")
    context_blocks: List[str] = Field(
        min_length=1,
        description="Reader가 그대로 사용할 시트·행 단위 실제 셀 컨텍스트",
    )
    block_count: int = Field(default=0, ge=0, description="생성된 확장 행 블록 개수")


class PgContextExpanderInputDTO(ModuleInputDTO):
    """Input contract containing retrieved search results."""

    retrieval_json: RetrievalDTO = Field(
        description="RRF Fusion에서 전달되는 상위 결합 검색 후보 결과"
    )


class PgContextExpanderConfigDTO(ModuleConfigDTO):
    """Configuration contract for DB-level adjacent row & timeseries expansion."""

    top_k: int = Field(
        default=DEFAULT_PG_CONTEXT_TOP_K,
        gt=0,
        le=500,
        description="인접 행 및 시계열 확장에 사용할 RRF 상위 후보 개수",
    )
    adjacent_radius: int = Field(
        default=DEFAULT_PG_ADJACENT_RADIUS,
        ge=0,
        le=20,
        description="검색 셀과 같은 시트에서 확장할 위·아래 행 반경",
    )
    max_blocks: int = Field(
        default=DEFAULT_PG_MAX_BLOCKS,
        gt=0,
        le=1000,
        description="LLM Generator 및 Calculator로 전달할 최대 확장 컨텍스트 블록 개수",
    )


# Standard Aliases
ContextExpanderInputDTO = PgContextExpanderInputDTO
ContextExpanderConfigDTO = PgContextExpanderConfigDTO
ContextExpanderOutput = ContextDTO


# ==============================================================================
# 3. Coordinate Helper Functions
# ==============================================================================
def _parse_cell_id_coords(cell_id: str) -> Tuple[str, str, Optional[int], Optional[int]]:
    """Parses cell_id string into (company, sheet_name, row_idx, col_idx)."""
    parts = cell_id.split(":")
    company = ""
    sheet = ""
    coord = ""

    if len(parts) >= 3:
        company = parts[0]
        sheet = parts[1]
        coord = parts[2]
    elif len(parts) == 2:
        sheet = parts[0]
        coord = parts[1]
    else:
        coord = parts[0]

    row_idx = None
    col_idx = None
    if coord:
        match = re.search(r"([A-Za-z]+)(\d+)", coord)
        if match:
            try:
                r_tuple, c_tuple = coordinate_to_tuple(coord)
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
        config_fields=["top_k", "adjacent_radius", "max_blocks"],
        raw_output=True,
        version="2",
    )
    input_model = PgContextExpanderInputDTO
    config_model = PgContextExpanderConfigDTO
    output_model = ContextDTO

    def __init__(self, pgvector_store: Optional[PgVectorStore] = None) -> None:
        super().__init__()
        self.pgvector_store = pgvector_store or PgVectorStore()

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
                "top_k_used": 0,
                "adjacent_radius": cfg.adjacent_radius,
                "context_characters": 0,
                "context_blocks": ["[No context blocks available]"],
                "block_count": 0,
            }

        # Step 1: Collect candidate cell texts and extract sheet + row targets
        context_blocks: List[str] = []
        seen_blocks: Set[str] = set()

        for candidate in retrieval_items:
            t = candidate.text.strip()
            if t and t not in seen_blocks:
                seen_blocks.add(t)
                context_blocks.append(t)

        # Step 2: Query PostgreSQL for row-level adjacent & timeseries cells
        target_rows_by_sheet: Dict[str, Set[int]] = defaultdict(set)
        for candidate in retrieval_items:
            _, sheet, r_idx, _ = _parse_cell_id_coords(candidate.cell_id)
            if sheet and r_idx is not None:
                radius = cfg.adjacent_radius
                for r in range(max(1, r_idx - radius), r_idx + radius + 1):
                    target_rows_by_sheet[sheet].add(r)

        collection_name = doc_context_dict.get("index_id")
        workbook_hash = doc_context_dict.get("workbook_hash")
        if not collection_name and retrieval_items:
            for cand in retrieval_items:
                cid = cand.cell_id
                if ":" in cid:
                    collection_name = cid.split(":")[0]
                    break

        if collection_name and target_rows_by_sheet:
            for sheet, row_indices in target_rows_by_sheet.items():
                rows_by_index = self.pgvector_store.fetch_rows_cells(
                    collection_name=collection_name,
                    workbook_hash=workbook_hash,
                    sheet_name=sheet,
                    row_indices=sorted(row_indices),
                    limit_per_row=50,
                )
                for r_idx in sorted(row_indices):
                    rows = rows_by_index.get(r_idx, [])
                    if not rows:
                        continue

                    row_header_label = ""
                    col_entries = []
                    for cell in sorted(
                        rows,
                        key=lambda value: (
                            value.get("col_index") is None,
                            value.get("col_index") or 0,
                        ),
                    ):
                        if not row_header_label and cell.get("row_header"):
                            rh = cell["row_header"]
                            row_header_label = " > ".join(rh) if isinstance(rh, list) else str(rh)
                        col_h = cell.get("column_header")
                        ch_label = " > ".join(col_h) if isinstance(col_h, list) else str(col_h or cell.get("cell_coord", ""))
                        val = cell.get("cell_value") or cell.get("text", "")
                        coord = cell.get("cell_coord", "")
                        col_entries.append(f"[{ch_label} (Cell {coord})]: {val}")

                    if col_entries:
                        formatted_block = (
                            f"[Sheet: {sheet}] Row Header: {row_header_label or 'N/A'}\n"
                            f"  -> Horizontally & Vertically Expanded Cells: " + " | ".join(col_entries)
                        )
                        if formatted_block not in seen_blocks:
                            seen_blocks.add(formatted_block)
                            context_blocks.append(formatted_block)

                    if len(context_blocks) >= cfg.max_blocks:
                        break
                if len(context_blocks) >= cfg.max_blocks:
                    break

        context_blocks = context_blocks[: cfg.max_blocks]
        if not context_blocks:
            context_blocks = ["[No context blocks available]"]

        total_chars = sum(len(b) for b in context_blocks)

        return {
            "query_context": query_context_dict,
            "document_context": doc_context_dict,
            "top_k_used": len(retrieval_items),
            "adjacent_radius": cfg.adjacent_radius,
            "context_characters": total_chars,
            "context_blocks": context_blocks,
            "block_count": len(context_blocks),
        }


# Standard Module Alias
ContextExpanderModule = PgContextExpanderModule


# ==============================================================================
# 5. Exports
# ==============================================================================
__all__ = [
    "ContextDTO",
    "ContextExpanderConfigDTO",
    "ContextExpanderInputDTO",
    "ContextExpanderModule",
    "ContextExpanderOutput",
    "DocumentContextDTO",
    "PgContextExpanderConfigDTO",
    "PgContextExpanderInputDTO",
    "PgContextExpanderModule",
    "QueryContextDTO",
]
