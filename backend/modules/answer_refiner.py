"""Independent module for refining Reader answers by querying direct spreadsheet cell metadata from PostgreSQL via pure LLM spatial reasoning."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from pydantic import Field

from ..llm.chat_completion import (
    ChatCompletionClient,
    ChatCompletionError,
    ChatCompletionResult,
)
from ..llm.cost import calculate_openai_cost
from ..spreadsheets.structured_cell_text import SHEET_CODE_MAP, canonical_sheet_name
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

logger = logging.getLogger(__name__)


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


class CellCandidateDTO(ModuleDTO):
    """A normalized cell coordinate with its optional referenced sheet."""

    cell_coord: str = Field(pattern=r"^[A-Z]{1,3}[1-9]\d{0,6}$")
    sheet_name: Optional[str] = None


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
    cell_extractor_prompt: str = Field(
        default=CELL_EXTRACTOR_SYSTEM_PROMPT,
        description="2D 스프레드시트 공간 위상 추론을 통한 타겟 셀 후보 추출 시스템 프롬프트",
    )
    max_direct_cells: int = Field(
        default=25,
        ge=1,
        le=60,
        description="DB에서 직접 인출할 최대 셀 개수",
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
            "Reader 답변에서 추가 검증이 필요한 셀을 LLM 2D 공간 위상 추론으로 선별하고, "
            "PostgreSQL pgvector 메타데이터에서 해당 셀들을 직접 조회하여 답변을 보강 및 정밀 개선합니다."
        ),
        inputs=["answer_json"],
        outputs=["refined_answer_json"],
        config_fields=[
            "model",
            "preset",
            "system_prompt",
            "user_prompt_template",
            "cell_extractor_prompt",
            "max_direct_cells",
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

    @staticmethod
    def _parse_candidate_token(
        raw_token: Any,
        sheet_codes: Dict[str, str],
    ) -> Optional[CellCandidateDTO]:
        """
        Normalize a raw cell candidate token (dict or string) into a CellCandidateDTO.
        
        Handles:
            - Dict: {"cell_coord": "P50", "sheet_name": "IS"}
            - Qualified strings: "IS:P50", "Income_Statement!P50", "IS Cell P50"
            - Standalone strings: "P50"
        """
        if isinstance(raw_token, dict):
            coord = raw_token.get("cell_coord") or raw_token.get("coord")
            sheet = raw_token.get("sheet_name") or raw_token.get("sheet")
            if not coord or not isinstance(coord, str):
                return None
            match = re.search(r"([A-Z]{1,3}[1-9]\d{0,6})", coord.upper())
            if not match:
                return None
            clean_coord = match.group(1)
            norm_sheet = None
            if sheet and isinstance(sheet, str) and sheet.strip():
                s = sheet.strip()
                norm_sheet = sheet_codes.get(s.upper(), canonical_sheet_name(s))
            return CellCandidateDTO(cell_coord=clean_coord, sheet_name=norm_sheet)

        if not isinstance(raw_token, str) or not raw_token.strip():
            return None

        token_str = raw_token.strip()
        # Parse patterns like 'IS:P50', 'Income_Statement!P50', 'IS Cell P50', or 'P50'
        qualified = re.search(
            r"^(?:(?P<sheet>[A-Za-z_][A-Za-z0-9_ ]*?)\s*(?:[!:]|\s+Cell\s+))?\s*(?P<coord>[A-Z]{1,3}[1-9]\d{0,6})$",
            token_str,
            flags=re.IGNORECASE,
        )
        if qualified:
            clean_coord = qualified.group("coord").upper()
            sheet_raw = qualified.group("sheet")
            norm_sheet = None
            if sheet_raw and sheet_raw.strip():
                s = sheet_raw.strip()
                norm_sheet = sheet_codes.get(s.upper(), canonical_sheet_name(s))
            return CellCandidateDTO(cell_coord=clean_coord, sheet_name=norm_sheet)

        # Fallback coordinate search
        match = re.search(r"([A-Z]{1,3}[1-9]\d{0,6})", token_str.upper())
        if match:
            return CellCandidateDTO(cell_coord=match.group(1), sheet_name=None)

        return None

    def _infer_candidate_cells(
        self,
        question: str,
        initial_answer: str,
        explicit_cell_ids: Optional[List[str]] = None,
        model: str = "gpt-5.6-luna",
        extractor_prompt: str = CELL_EXTRACTOR_SYSTEM_PROMPT,
        max_cells: int = 25,
    ) -> List[CellCandidateDTO]:
        """
        Uses LLM spatial & topological reasoning to infer candidate cell coordinates
        required to verify, correct, or complete the initial answer.
        """
        candidates: List[CellCandidateDTO] = []
        sheet_codes = {
            code.upper(): sheet_name
            for sheet_name, code in SHEET_CODE_MAP.items()
        }

        # 1. Add explicit cell IDs provided by caller/workflow
        for cell_id in explicit_cell_ids or []:
            cand = self._parse_candidate_token(cell_id, sheet_codes)
            if cand and not any(
                c.cell_coord == cand.cell_coord and c.sheet_name == cand.sheet_name
                for c in candidates
            ):
                candidates.append(cand)

        # 2. Perform LLM 2D Spatial Topology Reasoning
        if self.completion_client and len(candidates) < max_cells:
            try:
                res = self.completion_client.complete_with_metadata(
                    messages=[
                        {"role": "system", "content": extractor_prompt},
                        {
                            "role": "user",
                            "content": f"User Question: {question}\nInitial Draft Answer: {initial_answer}",
                        },
                    ],
                    model=model,
                )
                raw_text = res.content.strip()
                json_match = re.search(r"\[[\s\S]*\]", raw_text)
                if json_match:
                    items = json.loads(json_match.group(0))
                    if isinstance(items, list):
                        for item in items:
                            cand = self._parse_candidate_token(item, sheet_codes)
                            if cand and not any(
                                c.cell_coord == cand.cell_coord and c.sheet_name == cand.sheet_name
                                for c in candidates
                            ):
                                candidates.append(cand)
            except Exception as err:
                logger.warning("LLM 셀 공간 위상 추론 실패: %s", err)

        return candidates[:max_cells]

    def execute(self, payload: Any) -> Dict[str, Any]:
        """
        Refine an initial Reader answer using direct spreadsheet cell metadata identified
        via LLM spatial reasoning.
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

        # 1. Infer Target Cells via LLM Spatial Reasoning
        target_cells = self._infer_candidate_cells(
            question=question_text,
            initial_answer=initial_answer,
            explicit_cell_ids=parsed.target_cell_ids,
            model=parsed.model,
            extractor_prompt=parsed.cell_extractor_prompt,
            max_cells=parsed.max_direct_cells,
        )

        # 2. Directly Fetch Cell Metadata from PostgreSQL
        direct_cells: List[DirectCellDTO] = []
        if target_cells:
            fetched_raw_cells = self.pgvector_store.fetch_cells_by_metadata(
                cell_identifiers=[candidate.cell_coord for candidate in target_cells],
                cell_references=[
                    candidate.model_dump(mode="json")
                    for candidate in target_cells
                ],
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

        # 3. Construct Direct Cells Text for Refinement Prompt
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

        # 4. Execute Refinement LLM Completion
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
                res: ChatCompletionResult = self.completion_client.complete_with_metadata(
                    messages=[
                        {"role": "system", "content": parsed.system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    model=parsed.model,
                )
                api_usage = ApiUsageDTO(
                    prompt_tokens=res.usage.get("prompt_tokens", 0),
                    completion_tokens=res.usage.get("completion_tokens", 0),
                    cached_tokens=res.usage.get("cached_tokens", 0),
                    reasoning_tokens=res.usage.get("reasoning_tokens", 0),
                    total_tokens=res.usage.get("total_tokens", 0),
                )
                estimated_cost_usd = calculate_openai_cost(
                    parsed.model,
                    prompt_tokens=api_usage.prompt_tokens,
                    completion_tokens=api_usage.completion_tokens,
                    cached_tokens=api_usage.cached_tokens,
                )

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
