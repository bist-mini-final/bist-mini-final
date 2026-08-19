"""Independent module for refining Reader answers by querying direct spreadsheet cell metadata from PostgreSQL."""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from pydantic import Field

from ..llm.chat_completion import (
    ChatCompletionClient,
    ChatCompletionError,
    ChatCompletionResult,
)
from ..storage.pgvector_store import PgVectorStore
from .answer_refiner_presets import (
    CELL_EXTRACTOR_SYSTEM_PROMPT,
    REFINER_SYSTEM_PROMPT,
    REFINER_USER_TEMPLATE,
    answer_refiner_config_presets,
)
from .base import (
    ExecutableModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleInputDTO,
)
from .data_lineage import DocumentContextDTO, QueryContextDTO
from .reader import AnswerDTO, ApiUsageDTO


def _col_to_num(col: str) -> int:
    """Convert Excel column letters (e.g. 'A', 'O', 'AA') to 1-based number."""
    num = 0
    for ch in col.upper():
        if 'A' <= ch <= 'Z':
            num = num * 26 + (ord(ch) - ord('A') + 1)
    return num


def _num_to_col(num: int) -> str:
    """Convert 1-based number to Excel column letters (e.g. 1 -> 'A', 15 -> 'O')."""
    col = ""
    while num > 0:
        num, remainder = divmod(num - 1, 26)
        col = chr(ord('A') + remainder) + col
    return col


def _split_cell_coord(coord: str) -> Optional[Tuple[str, int]]:
    """
    Parse a spreadsheet cell coordinate into its column label and row number.
    
    Parameters:
        coord (str): Cell coordinate, such as ``"O50"``.
    
    Returns:
        Optional[Tuple[str, int]]: An uppercase column label and row number, or ``None`` for an invalid coordinate.
    """
    match = re.match(r"^([A-Za-z]+)(\d+)$", coord.strip())
    if match:
        return match.group(1).upper(), int(match.group(2))
    return None


class DirectCellDTO(ModuleDTO):
    """Structured representation of a cell directly retrieved from database metadata."""

    cell_id: str = Field(description="고유 셀 식별자 (예: IS:I16 또는 IS Cell I16)")
    sheet_name: str = Field(description="시트명 (예: Income_Statement)")
    cell_coord: str = Field(description="셀 좌표 (예: I16)")
    cell_value: Optional[str] = Field(default=None, description="원장 셀 값")
    row_header: List[str] = Field(default_factory=list, description="계층형 행 헤더 목록")
    column_header: List[str] = Field(default_factory=list, description="계층형 열 헤더 목록")
    company_name: Optional[str] = Field(default=None, description="기업명")
    source_text: str = Field(description="청크 원문 텍스트")


class AnswerRefinerInputDTO(ModuleInputDTO):
    answer_json: AnswerDTO = Field(
        description="Reader 모듈로부터 생성된 초기 답변 및 질문·문서 계보 DTO"
    )
    target_cell_ids: Optional[List[str]] = Field(
        default=None,
        description="직접 조회를 강제할 추가 셀 ID 목록 (선택 사항)",
    )


class AnswerRefinerConfigDTO(ModuleConfigDTO):
    model: str = Field(default="gpt-5.6-luna", description="답변 정밀 개선에 사용할 LLM ID")
    preset: str = Field(default="luna_cell_refiner", description="Refiner 프롬프트 프리셋 ID")
    system_prompt: str = Field(
        default=REFINER_SYSTEM_PROMPT,
        description="직접 셀 근거 기반 답변 정밀 교정 시스템 프롬프트",
    )
    user_prompt_template: str = Field(
        default=REFINER_USER_TEMPLATE,
        description="{question}, {initial_answer}, {direct_cells_text} 템플릿 변수를 포함하는 사용자 프롬프트",
    )
    max_direct_cells: int = Field(
        default=25,
        ge=1,
        le=60,
        description="DB에서 직접 인출할 최대 셀 개수",
    )
    spatial_column_radius: int = Field(
        default=3,
        ge=0,
        le=10,
        description="발견된 셀 좌표 기준으로 좌우 인접 열(연도/타임라인)을 자동 확장할 반경 (예: O50 -> N50, P50, Q50, R50)",
    )
    enable_auto_cell_discovery: bool = Field(
        default=True,
        description="질문 및 초기 답변에서 필요한 셀 좌표를 자동 판별하여 추가 인출할지 여부",
    )


class AnswerRefinerExecutionDTO(AnswerRefinerInputDTO, AnswerRefinerConfigDTO):
    """Internal execution DTO."""


class RefinedAnswerDTO(ModuleDTO):
    query_context: QueryContextDTO = Field(description="원본 질문 식별자 및 원문")
    document_context: DocumentContextDTO = Field(description="참조 원본 문서 식별자")
    initial_answer: str = Field(description="Reader 모듈이 생성했던 1차 초기 답변")
    refined_answer: str = Field(min_length=1, description="직접 셀 메타데이터가 반영된 최종 개선 답변")
    refinement_summary: str = Field(description="셀 근거를 통해 확인/수정된 사항 요약")
    direct_cells: List[DirectCellDTO] = Field(
        default_factory=list, description="DB 메타데이터에서 직접 인출된 셀 정보 목록"
    )
    model: str = Field(description="답변 개선에 사용된 LLM 모델 ID")
    api_usage: ApiUsageDTO = Field(description="LLM 토큰 사용량")
    latency_seconds: float = Field(ge=0, description="모듈 실행 시간(초)")
    estimated_cost_usd: float = Field(ge=0, description="예상 API 비용(USD)")


class AnswerRefinerOutput(ModuleDTO):
    refined_answer_json: RefinedAnswerDTO = Field(description="최종 개선된 답변 출력 포트")


class AnswerRefinerModule(ExecutableModule):
    definition = ModuleDefinition(
        type="answer_refiner",
        label="Direct Cell Answer Refiner",
        category="Output",
        description=(
            "Reader 답변에서 추가 검증이 필요한 셀 ID를 선별하고, "
            "PostgreSQL pgvector 메타데이터에서 해당 셀들을 직접 조회하여 답변을 보강 및 정밀 개선합니다."
        ),
        inputs=["answer_json"],
        outputs=["refined_answer_json"],
        config_fields=[
            "model",
            "preset",
            "system_prompt",
            "user_prompt_template",
            "max_direct_cells",
            "spatial_column_radius",
            "enable_auto_cell_discovery",
        ],
        config_presets=answer_refiner_config_presets(),
        version="1",
    )
    input_model = AnswerRefinerInputDTO
    config_model = AnswerRefinerConfigDTO
    execution_model = AnswerRefinerExecutionDTO
    output_model = AnswerRefinerOutput

    def __init__(
        self,
        completion_client: Optional[ChatCompletionClient] = None,
        pgvector_store: Optional[PgVectorStore] = None,
    ) -> None:
        """Initialize the answer refiner with optional completion and vector-store dependencies."""
        self.completion_client = completion_client
        self.pgvector_store = pgvector_store or PgVectorStore()

    def _expand_spatial_neighbors(self, coord: str, radius: int) -> List[str]:
        """
        Expand a valid cell coordinate to neighboring columns within the specified radius.
        
        Parameters:
        	coord (str): Cell coordinate to expand.
        	radius (int): Number of columns to include on each side.
        
        Returns:
        	List[str]: The original coordinate followed by right- and left-side neighboring coordinates. Invalid coordinates or non-positive radii return the uppercased original coordinate.
        """
        parsed = _split_cell_coord(coord)
        if not parsed or radius <= 0:
            return [coord.upper()]

        col_str, row_num = parsed
        base_col_num = _col_to_num(col_str)

        expanded = [coord.upper()]
        # Expand horizontal columns (prioritize rightward timeline years, then leftward)
        for offset in range(1, radius + 1):
            right_col = _num_to_col(base_col_num + offset)
            if right_col:
                expanded.append(f"{right_col}{row_num}")
            if base_col_num - offset > 0:
                left_col = _num_to_col(base_col_num - offset)
                expanded.append(f"{left_col}{row_num}")

        return expanded

    def _extract_candidate_cell_ids(
        self,
        question: str,
        initial_answer: str,
        explicit_cell_ids: Optional[List[str]] = None,
        spatial_radius: int = 3,
    ) -> List[str]:
        """
        Extracts cell references from the question and initial answer, then adds nearby horizontal cell coordinates.
        
        Parameters:
        	question (str): The question text to scan for cell references.
        	initial_answer (str): The initial answer text to scan for cell references.
        	explicit_cell_ids (Optional[List[str]]): Cell identifiers to include in the candidate set.
        	spatial_radius (int): Number of neighboring columns to include around each candidate cell.
        
        Returns:
        	List[str]: Unique cell identifiers found or generated from the supplied text and explicit identifiers.
        """
        base_candidates: List[str] = list(explicit_cell_ids or [])

        # Heuristic 1: Regex matches for cell patterns like 'IS Cell O50', 'O50', 'Income_Statement!E16'
        text_corpus = f"{question}\n{initial_answer}"
        pattern = r"\b(?:[A-Za-z0-9_]+[!:])?([A-Z]{1,3}\d{1,4})\b"
        for m in re.findall(pattern, text_corpus):
            cand = m.upper()
            if cand not in base_candidates:
                base_candidates.append(cand)

        # Heuristic 2: Match 'IS Cell I16' or 'Cell I16'
        named_cell_pattern = r"(?:[A-Za-z0-9_]+\s+)?Cell\s+([A-Z]{1,3}\d{1,4})"
        for m in re.findall(named_cell_pattern, text_corpus, flags=re.IGNORECASE):
            cand = m.upper()
            if cand not in base_candidates:
                base_candidates.append(cand)

        # Perform Spatial Horizontal Timeline Expansion
        final_candidates: List[str] = []
        for cand in base_candidates:
            neighbors = self._expand_spatial_neighbors(cand, spatial_radius)
            for n in neighbors:
                if n not in final_candidates:
                    final_candidates.append(n)

        return final_candidates

    def execute(self, payload: Any) -> Dict[str, Any]:
        """
        Refine an initial Reader answer using matching spreadsheet cell metadata and optional language-model processing.
        
        Parameters:
            payload (Any): Answer-refinement input containing the initial answer, configuration, and optional target cell identifiers.
        
        Returns:
            Dict[str, Any]: JSON-serializable refined answer data, including direct cells, refinement details, usage, latency, and estimated cost.
        
        Raises:
            ModuleExecutionError: If the language-model refinement request fails.
        """
        started_at = time.perf_counter()
        if isinstance(payload, AnswerRefinerExecutionDTO):
            parsed = payload
        elif isinstance(payload, dict):
            parsed = AnswerRefinerExecutionDTO.model_validate(payload)
        else:
            parsed = AnswerRefinerExecutionDTO.model_validate(payload.model_dump())

        initial_dto = parsed.answer_json
        question_text = initial_dto.query_context.question_text
        initial_answer = initial_dto.answer
        workbook_hash = initial_dto.document_context.workbook_hash

        # 1. Identify Candidate Cell IDs and expand horizontal timeline neighbors
        target_cell_ids = self._extract_candidate_cell_ids(
            question=question_text,
            initial_answer=initial_answer,
            explicit_cell_ids=parsed.target_cell_ids,
            spatial_radius=parsed.spatial_column_radius,
        )

        # 2. LLM-assisted Auto Cell Discovery if enabled
        if parsed.enable_auto_cell_discovery and self.completion_client and len(target_cell_ids) < parsed.max_direct_cells:
            try:
                extract_res = self.completion_client.complete(
                    messages=[
                        {"role": "system", "content": CELL_EXTRACTOR_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": f"Question: {question_text}\nDraft Answer: {initial_answer}",
                        },
                    ],
                    model=parsed.model,
                    temperature=0.0,
                    max_tokens=200,
                )
                raw_json = extract_res.content.strip()
                if raw_json.startswith("[") and raw_json.endswith("]"):
                    discovered = json.loads(raw_json)
                    if isinstance(discovered, list):
                        for item in discovered:
                            if isinstance(item, str) and item.strip():
                                clean_item = item.strip().upper()
                                for n in self._expand_spatial_neighbors(clean_item, parsed.spatial_column_radius):
                                    if n not in target_cell_ids:
                                        target_cell_ids.append(n)
            except Exception:
                # Graceful fallback to regex & spatial expansion
                pass

        # 3. Directly Fetch Cell Metadata from PostgreSQL
        fetched_raw_cells = self.pgvector_store.fetch_cells_by_metadata(
            cell_identifiers=target_cell_ids[: parsed.max_direct_cells],
            workbook_hash=workbook_hash,
            limit=parsed.max_direct_cells,
        )

        direct_cells = [
            DirectCellDTO(
                cell_id=c["cell_id"],
                sheet_name=c["sheet_name"],
                cell_coord=c["cell_coord"],
                cell_value=c.get("cell_value"),
                row_header=c.get("row_header", []),
                column_header=c.get("column_header", []),
                company_name=c.get("company_name"),
                source_text=c.get("source_text", ""),
            )
            for c in fetched_raw_cells
        ]

        # 4. Construct Direct Cells Text for Refinement Prompt
        if direct_cells:
            cell_lines = []
            for dc in direct_cells:
                row_h = " > ".join(dc.row_header) if dc.row_header else "N/A"
                col_h = " > ".join(dc.column_header) if dc.column_header else "N/A"
                val = dc.cell_value if dc.cell_value is not None else "(empty)"
                cell_lines.append(
                    f"- [{dc.sheet_name}!{dc.cell_coord}] Row: {row_h} | Col: {col_h} | Value: {val} | Full: {dc.source_text}"
                )
            direct_cells_text = "\n".join(cell_lines)
        else:
            direct_cells_text = "No additional direct cell metadata found in database matching identified coordinates."

        # 5. Execute Refinement LLM Completion
        user_prompt = parsed.user_prompt_template.format(
            question=question_text,
            initial_answer=initial_answer,
            direct_cells_text=direct_cells_text,
        )

        refined_answer = initial_answer
        refinement_summary = "No modifications made."
        api_usage = ApiUsageDTO()
        estimated_cost_usd = 0.0

        if self.completion_client:
            try:
                res: ChatCompletionResult = self.completion_client.complete(
                    messages=[
                        {"role": "system", "content": parsed.system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    model=parsed.model,
                    temperature=0.2,
                    max_tokens=1200,
                )
                api_usage = ApiUsageDTO(
                    prompt_tokens=res.usage.prompt_tokens,
                    completion_tokens=res.usage.completion_tokens,
                    cached_tokens=res.usage.cached_tokens,
                    reasoning_tokens=res.usage.reasoning_tokens,
                    total_tokens=res.usage.total_tokens,
                )
                estimated_cost_usd = res.estimated_cost_usd

                # Parse JSON output format
                content = res.content.strip()
                json_match = re.search(r"\{[\s\S]*\}", content)
                if json_match:
                    try:
                        data = json.loads(json_match.group(0))
                        refined_answer = data.get("refined_answer", content)
                        refinement_summary = data.get(
                            "refinement_summary", "Refined with direct cell metadata."
                        )
                    except json.JSONDecodeError:
                        refined_answer = content
                        refinement_summary = "Refined with direct cell metadata."
                else:
                    refined_answer = content
                    refinement_summary = "Refined with direct cell metadata."
            except ChatCompletionError as err:
                raise ModuleExecutionError(f"Answer Refiner LLM execution failed: {err}") from err
        else:
            # Fallback mock for testing without live API keys
            if direct_cells:
                refined_answer = (
                    f"{initial_answer}\n\n[Direct Cell Verification]\n"
                    + "\n".join(
                        f"- {c.sheet_name}!{c.cell_coord} ({' > '.join(c.row_header)}): {c.cell_value}"
                        for c in direct_cells[:8]
                    )
                )
                refinement_summary = (
                    f"Directly verified {len(direct_cells)} cells from database metadata."
                )

        latency_seconds = max(0.0, time.perf_counter() - started_at)

        refined_dto = RefinedAnswerDTO(
            query_context=initial_dto.query_context,
            document_context=initial_dto.document_context,
            initial_answer=initial_answer,
            refined_answer=refined_answer,
            refinement_summary=refinement_summary,
            direct_cells=direct_cells,
            model=parsed.model,
            api_usage=api_usage,
            latency_seconds=latency_seconds,
            estimated_cost_usd=estimated_cost_usd,
        )

        return AnswerRefinerOutput(refined_answer_json=refined_dto).model_dump(mode="json")
