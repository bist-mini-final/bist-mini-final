"""On-Demand PostgreSQL Direct Timeseries Context Expander Module."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple, cast

from openpyxl.utils.cell import coordinate_to_tuple
from pydantic import BaseModel, Field

from backend.storage.pgvector_store import PgVectorStore
from modules.common.base_module import (
    ExecutableModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleExecutionError,
    ModuleInputDTO,
)
from modules.retrieval.context_expander import ContextDTO
from modules.retrieval.retrieval_models import RetrievalDTO

logger = logging.getLogger(__name__)


class PgContextExpanderInputDTO(ModuleInputDTO):
    retrieval_json: RetrievalDTO = Field(
        description="RRF Fusion에서 전달되는 상위 결합 검색 후보 결과"
    )


class PgContextExpanderConfigDTO(ModuleConfigDTO):
    top_k: int = Field(
        default=25,
        gt=0,
        le=500,
        description="인접 행 및 시계열 확장에 사용할 RRF 상위 후보 개수",
    )
    adjacent_radius: int = Field(
        default=2,
        ge=0,
        le=20,
        description="검색 셀과 같은 시트에서 확장할 위·아래 행 반경",
    )
    max_blocks: int = Field(
        default=100,
        gt=0,
        le=1000,
        description="LLM Generator 및 Calculator로 전달할 최대 확장 컨텍스트 블록 개수",
    )


class PgContextExpanderExecutionDTO(
    PgContextExpanderInputDTO, PgContextExpanderConfigDTO
):
    """Internal union of retrieval data and on-demand expansion policy."""


def _parse_cell_id_coords(cell_id: str) -> Tuple[str, str, Optional[int], Optional[int]]:
    """
    Parses cell_id string into (company, sheet_name, row_idx, col_idx).
    Supports formats like 'IBM:Income_Statement:B15', 'Income_Statement:B15', 'B15'.
    """
    parts = str(cell_id).split(":")
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


class PgContextExpanderModule(ExecutableModule):
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
        version="1",
    )
    input_model = PgContextExpanderInputDTO
    config_model = PgContextExpanderConfigDTO
    execution_model = PgContextExpanderExecutionDTO
    output_model = ContextDTO

    def __init__(self, pgvector_store: Optional[PgVectorStore] = None) -> None:
        self.pgvector_store = pgvector_store or PgVectorStore()

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(PgContextExpanderExecutionDTO, payload)
        retrieval_items = input_data.retrieval_json.items[: input_data.top_k]
        query_context_dict = input_data.retrieval_json.query_context.model_dump(mode="json")
        doc_context_dict = input_data.retrieval_json.document_context.model_dump(mode="json")

        if not retrieval_items:
            return {
                "query_context": query_context_dict,
                "document_context": doc_context_dict,
                "context_blocks": [],
            }

        # Step 1: Collect candidate cell texts and extract sheet + row targets
        context_blocks: List[str] = []
        seen_blocks: Set[str] = set()

        # Add top matched candidate texts directly
        for candidate in retrieval_items:
            t = candidate.text.strip()
            if t and t not in seen_blocks:
                seen_blocks.add(t)
                context_blocks.append(t)

        # Step 2: Query PostgreSQL for row-level adjacent & timeseries cells
        target_rows_by_sheet: Dict[str, Set[int]] = defaultdict(set)
        for candidate in retrieval_items:
            company, sheet, r_idx, _ = _parse_cell_id_coords(candidate.cell_id)
            if sheet and r_idx is not None:
                radius = input_data.adjacent_radius
                for r in range(max(1, r_idx - radius), r_idx + radius + 1):
                    target_rows_by_sheet[sheet].add(r)

        if target_rows_by_sheet:
            conn = self.pgvector_store._raw_connection()
            try:
                with conn.cursor() as cur:
                    for sheet, rows_set in target_rows_by_sheet.items():
                        if not rows_set:
                            continue
                        row_list = sorted(rows_set)
                        sql = """
                            SELECT 
                                document,
                                cmetadata
                            FROM langchain_pg_embedding
                            WHERE cmetadata->>'sheet_name' = %s
                              AND (cmetadata->>'row_index')::int = ANY(%s)
                            ORDER BY (cmetadata->>'row_index')::int, (cmetadata->>'col_index')::int;
                        """
                        cur.execute(sql, (sheet, row_list))
                        fetched = cur.fetchall()

                        # Group by row
                        row_cells_map: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
                        for doc_text, cmeta in fetched:
                            if isinstance(cmeta, dict):
                                r_i = int(cmeta.get("row_index", 0))
                                row_cells_map[r_i].append({"text": doc_text, "meta": cmeta})

                        # Format expanded row blocks
                        for r_i, cells in row_cells_map.items():
                            if not cells:
                                continue
                            # Extract header and values
                            first_meta = cells[0]["meta"]
                            row_header = first_meta.get("row_header", [])
                            header_str = (
                                " > ".join(str(h) for h in row_header)
                                if isinstance(row_header, list)
                                else str(row_header)
                            )
                            values_summary = ", ".join(
                                f"{c['meta'].get('column_header', [''])[0] if isinstance(c['meta'].get('column_header'), list) and c['meta'].get('column_header') else ''}: {c['meta'].get('cell_value', '')}"
                                for c in cells
                                if c["meta"].get("cell_value") is not None
                            )
                            block = f"[{sheet} 행 {r_i}] {header_str} | {values_summary}"
                            if block not in seen_blocks and len(context_blocks) < input_data.max_blocks:
                                seen_blocks.add(block)
                                context_blocks.append(block)

            except Exception as e:
                logger.warning("PgContextExpander on-demand 쿼리 오류: %s", e)
            finally:
                conn.close()

        final_blocks = context_blocks[: input_data.max_blocks]
        if not final_blocks:
            final_blocks = ["No relevant context found."]
        total_chars = sum(len(b) for b in final_blocks)

        context_dto = ContextDTO(
            query_context=input_data.retrieval_json.query_context,
            document_context=input_data.retrieval_json.document_context,
            top_k_used=max(1, min(len(retrieval_items), input_data.top_k)),
            adjacent_radius=input_data.adjacent_radius,
            context_characters=total_chars,
            context_blocks=final_blocks,
            block_count=len(final_blocks),
        )

        return {
            "context_json": context_dto,
            "query_context": query_context_dict,
            "document_context": doc_context_dict,
            "top_k_used": max(1, min(len(retrieval_items), input_data.top_k)),
            "adjacent_radius": input_data.adjacent_radius,
            "context_characters": total_chars,
            "context_blocks": final_blocks,
            "block_count": len(final_blocks),
        }
