from collections import defaultdict
from typing import Any, DefaultDict, Dict, List, Set, Tuple, cast

from openpyxl.utils.cell import coordinate_to_tuple
from pydantic import BaseModel, Field

from .base import ExecutableModule, ModuleDefinition, ModuleDTO, ModuleExecutionError
from .cell_text_serializer import CellTextDocumentDTO, CellTextSerializerOutput
from .retrieval_models import RetrievalDTO


class ContextExpanderInput(ModuleDTO):
    retrieval_json: RetrievalDTO = Field(
        description="RRF Fusion에서 전달되는 셀 단위 결합 검색 결과"
    )
    document_input: CellTextSerializerOutput = Field(
        description="인접 행과 실제 값을 복원할 Structured Cell Text 문서"
    )
    top_k: int = Field(
        default=100,
        gt=0,
        le=1000,
        description="인접 행 확장에 사용할 RRF 상위 후보 개수",
    )
    adjacent_radius: int = Field(
        default=3,
        ge=0,
        le=100,
        description="검색 셀과 같은 시트에서 확장할 위·아래 행 반경",
    )
    max_blocks: int = Field(
        default=500,
        gt=0,
        le=5000,
        description="Reader로 전달할 최대 확장 행 블록 개수",
    )


class ContextDTO(ModuleDTO):
    question_id: str = Field(description="원본 질문 ID")
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


class ContextExpanderModule(ExecutableModule):
    definition = ModuleDefinition(
        type="context",
        label="Context Expander",
        category="Transform",
        description="RRF 후보 셀을 기준으로 같은 시트의 인접 행과 모든 열 값을 확장합니다.",
        inputs=["retrieval_json", "document_input"],
        outputs=["context_json"],
        config_fields=["top_k", "adjacent_radius", "max_blocks"],
        version="2",
    )
    input_model = ContextExpanderInput
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
    def _format_row(
        sheet_name: str,
        row_header: List[str],
        documents: List[CellTextDocumentDTO],
    ) -> str:
        cells = []
        for document in sorted(
            documents,
            key=lambda item: coordinate_to_tuple(item.cell_coord)[1],
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

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(ContextExpanderInput, payload)
        candidates = input_data.retrieval_json.items[: input_data.top_k]
        if not candidates:
            raise ModuleExecutionError("컨텍스트를 확장할 RRF 후보가 없습니다")

        documents_by_id = self._actual_documents(input_data.document_input.items)
        rows: DefaultDict[Tuple[str, int], List[CellTextDocumentDTO]] = defaultdict(list)
        row_headers: Dict[Tuple[str, int], List[str]] = {}
        for document in documents_by_id.values():
            row, _ = coordinate_to_tuple(document.cell_coord)
            row_key = (document.sheet_name, row)
            rows[row_key].append(document)
            row_headers.setdefault(row_key, document.row_header)

        expanded_rows: List[Tuple[str, int]] = []
        seen_rows: Set[Tuple[str, int]] = set()
        matched_candidates = 0
        for candidate in candidates:
            document = documents_by_id.get(candidate.cell_id)
            if document is None:
                continue
            matched_candidates += 1
            candidate_row, _ = coordinate_to_tuple(document.cell_coord)
            for offset in range(-input_data.adjacent_radius, input_data.adjacent_radius + 1):
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
            for sheet_name, row in expanded_rows[: input_data.max_blocks]
        ]
        if not context_blocks:
            raise ModuleExecutionError("인접 행 확장 결과가 비어 있습니다")
        context_text = "\n\n".join(context_blocks)
        return {
            "context_json": {
                "question_id": input_data.retrieval_json.question_id.upper(),
                "top_k_used": matched_candidates,
                "adjacent_radius": input_data.adjacent_radius,
                "context_characters": len(context_text),
                "context_blocks": context_blocks,
                "block_count": len(context_blocks),
            }
        }
