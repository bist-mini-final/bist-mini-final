from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Optional, Any, DefaultDict, Dict, List, Optional, Set, Tuple, Union, cast

from openpyxl.utils.cell import coordinate_to_tuple
from pydantic import BaseModel, Field

from backend.storage.pgvector_store import PgVectorStore
from modules.common.base_module import (
    DocumentContextDTO,
    BaseModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleInputDTO,
    QueryContextDTO,
)
from modules.common.config import (
    DEFAULT_ADJACENT_RADIUS,
    DEFAULT_MAX_BLOCKS,
    DEFAULT_RETRIEVAL_TOP_K,
)
from modules.retrieval.retrieval_models import RankedSearchResultDTO, RetrievalDTO
from modules.structure.cell_text_serializer import CellTextDocumentDTO, CellTextSerializerOutput

logger = logging.getLogger(__name__)


class ContextExpanderInputDTO(ModuleInputDTO):
    retrieval_json: Union[RetrievalDTO, RankedSearchResultDTO] = Field(
        description="RRF Fusion에서 전달되는 셀 단위 결합 검색 결과"
    )
    document_input: CellTextSerializerOutput = Field(
        description="인접 행과 실제 값을 복원할 Structured Cell Text 문서"
    )


class ContextExpanderConfigDTO(ModuleConfigDTO):
    top_k: int = Field(
        default=DEFAULT_RETRIEVAL_TOP_K,
        gt=0,
        le=1000,
        description="인접 행 확장에 사용할 RRF 상위 후보 개수",
    )
    adjacent_radius: int = Field(
        default=DEFAULT_ADJACENT_RADIUS,
        ge=0,
        le=100,
        description="검색 셀과 같은 시트에서 확장할 위·아래 행 반경",
    )
    max_blocks: int = Field(
        default=DEFAULT_MAX_BLOCKS,
        gt=0,
        le=5000,
        description="Reader로 전달할 최대 확장 행 블록 개수",
    )


class ContextExpanderExecutionDTO(ContextExpanderInputDTO, ContextExpanderConfigDTO):
    """Internal union of retrieval data and expansion policy."""


class ContextDTO(ModuleDTO):
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
    block_count: int = Field(gt=0, description="생성된 확장 행 블록 개수")


class ContextExpanderOutput(ModuleDTO):
    context_json: ContextDTO = Field(
        description="Reader로 전달할 확장 컨텍스트 출력 포트"
    )


class ContextExpanderModule(BaseModule):
    definition = ModuleDefinition(
        type="context",
        label="Context Expander",
        category="Transform",
        description="RRF 후보 셀을 기준으로 같은 시트의 인접 행과 모든 열 값을 확장합니다.",
        inputs=["retrieval_json", "document_input"],
        outputs=["context_json"],
        config_fields=["top_k", "adjacent_radius", "max_blocks"],
        version="3",
    )
    input_model = ContextExpanderInputDTO
    config_model = ContextExpanderConfigDTO
    execution_model = ContextExpanderExecutionDTO
    output_model = ContextExpanderOutput

    @staticmethod
    def _actual_documents(
        items: List[CellTextDocumentDTO],
    ) -> Dict[str, CellTextDocumentDTO]:
        documents: Dict[str, CellTextDocumentDTO] = {}
        for item in items:
            current = documents.get(item.cell_id)
            if current is None or (
                current.variant != "header_with_value"
                and item.variant == "header_with_value"
            ):
                documents[item.cell_id] = item
        return documents

    @staticmethod
    def _safe_coord(coord: str, default_row: int = 1) -> Tuple[int, int]:
        try:
            return coordinate_to_tuple(coord)
        except Exception:
            return (default_row, 1)

    @classmethod
    def _format_row(
        cls,
        sheet_name: str,
        row_header: List[str],
        documents: List[CellTextDocumentDTO],
    ) -> str:
        cells = []
        for document in sorted(
            documents,
            key=lambda item: cls._safe_coord(item.cell_coord)[1],
        ):
            column_header = (
                " > ".join(document.column_header)
                if document.column_header
                else document.cell_coord
            )
            cells.append(
                f"[{column_header} ({document.cell_id})]: {document.cell_value}"
            )
        resolved_row_header = " > ".join(row_header) if row_header else "N/A"
        return (
            f"Sheet: {sheet_name} | Row Header: {resolved_row_header}\n"
            "  -> Horizontally & Vertically Expanded Cells: "
            + " | ".join(cells)
        )

    def execute(
        self,
        input_data: ContextExpanderInputDTO,
        config: Optional[ContextExpanderConfigDTO] = None,
    ) -> Dict[str, Any]:
        if config is None and isinstance(input_data, ContextExpanderExecutionDTO):
            cfg = input_data
        else:
            cfg = config or ContextExpanderConfigDTO()
        expected_document = {
            "file_name": input_data.document_input.file_name,
            "workbook_hash": input_data.document_input.workbook_hash,
        }
        if input_data.retrieval_json.document_context.model_dump(mode="json") != expected_document:
            raise ModuleExecutionError(
                "검색 결과와 Structured Cell Text의 document_context가 일치하지 않습니다"
            )
        candidates = input_data.retrieval_json.items[: cfg.top_k]
        if not candidates:
            raise ModuleExecutionError("컨텍스트를 확장할 RRF 후보가 없습니다")

        documents_by_id = self._actual_documents(input_data.document_input.items)
        rows: DefaultDict[Tuple[str, int], List[CellTextDocumentDTO]] = defaultdict(list)
        row_headers: Dict[Tuple[str, int], List[str]] = {}
        for index, document in enumerate(documents_by_id.values()):
            row, _ = self._safe_coord(document.cell_coord, index + 1)
            row_key = (document.sheet_name, row)
            rows[row_key].append(document)
            row_headers.setdefault(row_key, document.row_header)

        expanded_rows: List[Tuple[str, int]] = []
        seen_rows: Set[Tuple[str, int]] = set()
        matched_candidates = 0
        for index, candidate in enumerate(candidates):
            document = documents_by_id.get(candidate.cell_id)
            if document is None:
                continue
            matched_candidates += 1
            candidate_row, _ = self._safe_coord(document.cell_coord, index + 1)
            for offset in range(-cfg.adjacent_radius, cfg.adjacent_radius + 1):
                row_key = (document.sheet_name, candidate_row + offset)
                if row_key in rows and row_key not in seen_rows:
                    seen_rows.add(row_key)
                    expanded_rows.append(row_key)

        if matched_candidates == 0:
            raise ModuleExecutionError(
                "RRF 후보 Cell ID가 Structured Cell Text 문서에 존재하지 않습니다"
            )

        context_blocks = [
            self._format_row(
                sheet_name,
                row_headers[(sheet_name, row)],
                rows[(sheet_name, row)],
            )
            for sheet_name, row in expanded_rows[: cfg.max_blocks]
        ]
        if not context_blocks:
            raise ModuleExecutionError("인접 행 확장 결과가 비어 있습니다")
        context_text = "\n\n".join(context_blocks)
        return {
            "context_json": {
                "query_context": input_data.retrieval_json.query_context.model_dump(
                    mode="json"
                ),
                "document_context": expected_document,
                "top_k_used": matched_candidates,
                "adjacent_radius": cfg.adjacent_radius,
                "context_characters": len(context_text),
                "context_blocks": context_blocks,
                "block_count": len(context_blocks),
            }
        }


# ==============================================================================
# 2. Pg Context Expander Module
# ==============================================================================

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
        version="1",
    )
    input_model = PgContextExpanderInputDTO
    config_model = PgContextExpanderConfigDTO
    execution_model = PgContextExpanderExecutionDTO
    output_model = ContextDTO

    def __init__(self, pgvector_store: Optional[PgVectorStore] = None) -> None:
        self.pgvector_store = pgvector_store or PgVectorStore()

    def execute(
        self,
        input_data: PgContextExpanderInputDTO,
        config: Optional[PgContextExpanderConfigDTO] = None,
    ) -> Dict[str, Any]:
        if config is None and isinstance(input_data, PgContextExpanderExecutionDTO):
            cfg = input_data
        else:
            cfg = config or PgContextExpanderConfigDTO()
        retrieval_items = input_data.retrieval_json.items[: cfg.top_k]
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
                radius = cfg.adjacent_radius
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
                            if block not in seen_blocks and len(context_blocks) < cfg.max_blocks:
                                seen_blocks.add(block)
                                context_blocks.append(block)

            except Exception as e:
                logger.warning("PgContextExpander on-demand 쿼리 오류: %s", e)
            finally:
                conn.close()

        final_blocks = context_blocks[: cfg.max_blocks]
        if not final_blocks:
            final_blocks = ["No relevant context found."]
        total_chars = sum(len(b) for b in final_blocks)

        context_dto = ContextDTO(
            query_context=input_data.retrieval_json.query_context,
            document_context=input_data.retrieval_json.document_context,
            top_k_used=max(1, min(len(retrieval_items), cfg.top_k)),
            adjacent_radius=cfg.adjacent_radius,
            context_characters=total_chars,
            context_blocks=final_blocks,
            block_count=len(final_blocks),
        )

        return {
            "context_json": context_dto,
            "query_context": query_context_dict,
            "document_context": doc_context_dict,
            "top_k_used": max(1, min(len(retrieval_items), cfg.top_k)),
            "adjacent_radius": cfg.adjacent_radius,
            "context_characters": total_chars,
            "context_blocks": final_blocks,
            "block_count": len(final_blocks),
        }

# ==============================================================================
# 3. Timeseries Context Expander Module
# ==============================================================================

class TimeseriesContextExpanderInputDTO(ModuleInputDTO):
    retrieval_json: RetrievalDTO = Field(
        description="RRF 융합 검색 결과 DTO"
    )
    document_input: CellTextSerializerOutput = Field(
        description="Excel 구조화 셀 문서 입력 포트"
    )




class TimeseriesContextExpanderConfigDTO(ModuleConfigDTO):
    top_k: int = Field(
        default=DEFAULT_RETRIEVAL_TOP_K,
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


class TimeseriesContextExpanderModule(BaseModule):
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

    def execute(
        self,
        input_data: TimeseriesContextExpanderInputDTO,
        config: Optional[TimeseriesContextExpanderConfigDTO] = None,
    ) -> Dict[str, Any]:
        if config is None and isinstance(input_data, TimeseriesContextExpanderExecutionDTO):
            cfg = input_data
        else:
            cfg = config or TimeseriesContextExpanderConfigDTO()
        documents = input_data.document_input.items
        candidates = input_data.retrieval_json.items[: cfg.top_k]

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

        if cfg.expand_full_row:
            expanded_rows: List[Tuple[str, int]] = []
            seen_rows: Set[Tuple[str, int]] = set()

            for index, candidate in enumerate(candidates):
                document = doc_by_cell_id.get(candidate.cell_id)
                if document is None:
                    continue
                matched_count += 1
                candidate_row, _ = self._safe_coord(document.cell_coord, index + 1)

                for offset in range(-cfg.adjacent_radius, cfg.adjacent_radius + 1):
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
                for sheet_name, row in expanded_rows[: cfg.max_blocks]
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
                for offset in range(-cfg.adjacent_radius, cfg.adjacent_radius + 1):
                    row_key = (document.sheet_name, candidate_row + offset)
                    for d in rows.get(row_key, []):
                        if d.cell_id not in seen_cells:
                            seen_cells.add(d.cell_id)
                            context_blocks.append(
                                f"[Sheet: {d.sheet_name}] {' > '.join(d.row_header)} | "
                                f"{' > '.join(d.column_header)}: {d.cell_value or d.text} (Cell {d.cell_coord})"
                            )
                if len(context_blocks) >= cfg.max_blocks:
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
                "adjacent_radius": cfg.adjacent_radius,
                "context_characters": len(context_text),
                "context_blocks": context_blocks,
                "block_count": len(context_blocks),
            }
        }

__all__ = [
    "ContextDTO",
    "ContextExpanderConfigDTO",
    "ContextExpanderExecutionDTO",
    "ContextExpanderInputDTO",
    "ContextExpanderModule",
    "ContextExpanderOutput",
    "PgContextExpanderConfigDTO",
    "PgContextExpanderExecutionDTO",
    "PgContextExpanderInputDTO",
    "PgContextExpanderModule",
    "TimeseriesContextExpanderConfigDTO",
    "TimeseriesContextExpanderExecutionDTO",
    "TimeseriesContextExpanderInputDTO",
    "TimeseriesContextExpanderModule",
]
