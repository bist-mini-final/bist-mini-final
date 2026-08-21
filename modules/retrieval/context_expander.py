from __future__ import annotations

from collections import defaultdict
from typing import Optional, Any, DefaultDict, Dict, List, Set, Tuple, Union, cast

from openpyxl.utils.cell import coordinate_to_tuple
from pydantic import BaseModel, Field

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
from modules.structure.cell_text_serializer import CellTextDocumentDTO, CellTextSerializerOutput
from modules.retrieval.retrieval_models import RankedSearchResultDTO, RetrievalDTO


class ContextExpanderInputDTO(ModuleInputDTO):
    retrieval_json: Union[RetrievalDTO, RankedSearchResultDTO] = Field(
        description="RRF Fusion에서 전달되는 셀 단위 결합 검색 결과"
    )
    document_input: CellTextSerializerOutput = Field(
        description="인접 행과 실제 값을 복원할 Structured Cell Text 문서"
    )


from modules.common.config import (
    DEFAULT_ADJACENT_RADIUS,
    DEFAULT_MAX_BLOCKS,
    DEFAULT_RETRIEVAL_TOP_K,
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
