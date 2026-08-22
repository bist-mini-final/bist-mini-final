"""선택된 엑셀 통합 문서로부터 기업 엔티티(공식 기업명, 티커, 표시명)를 LLM으로 추출하고 DB에 영속화하는 모듈.

통합 문서의 파일명, 시트명 목록, 상단 헤더 셀 텍스트를 샘플링하여 LLM 프롬프트에 전달하고,
추출된 기업명 및 티커 정보를 pgvector 메타데이터 컬렉션에 자동 매핑/저장합니다.

Example:
    Input DTO (입력 예시):
    ```json
    {
      "index_input": {
        "collection_name": "rag_cells_a1b2c3d4",
        "workbook_hash": "a1b2c3d4...",
        "vector_count": 1200
      },
      "file_name": "samsung_2023_financials.xlsx",
      "workbook_hash": "a1b2c3d4..."
    }
    ```

    Output DTO (출력 예시):
    ```json
    {
      "company_name": "삼성전자",
      "ticker": "005930",
      "display_name": "삼성전자 (005930)",
      "confidence": "high",
      "persisted": true,
      "collection_name": "rag_cells_a1b2c3d4",
      "metrics": {
        "kind": "llm_structured",
        "model": "gpt-5.6-luna",
        "latency_seconds": 0.45
      }
    }
    ```
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Literal, Optional

import openpyxl
from pydantic import BaseModel, Field, model_validator

from backend.core.settings import PROCESSED_DATA_DIR
from backend.storage.pgvector_store import PgVectorStore
from backend.storage.spreadsheets.workbook_catalog import WorkbookCatalog
from modules.common.base_llm import (
    BaseLLMModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleInputDTO,
)
from modules.common.config import DEFAULT_ENTITY_EXTRACTOR_MODEL
from modules.common.exceptions import ProviderApiError, StorageError
from modules.storage.pgvector_index_writer import VectorIndexDTO

logger = logging.getLogger(__name__)

COMPANY_EXTRACTION_SYSTEM_PROMPT = """You identify the corporate entity represented in a spreadsheet.
Analyze the file name, worksheet names, and sampled header cells to infer the primary company name and ticker symbol (if applicable).

Guidelines:
1. Formal Name: Preserve the standard official company name in Korean or English (e.g., 'Samsung Electronics', '삼성전자').
2. Ticker: Extract the exchange ticker or stock code if present (e.g., '005930', 'AAPL'). If not a listed company or not found, leave ticker as an empty string.
3. Display Name: Format as 'Company Name (TICKER)' when a ticker is known, or just 'Company Name' otherwise."""


class CompanyEntityDocument(BaseModel):
    """Provider-only structured response without persistence-specific fields."""

    company_name: str = Field(description="공식 기업명")
    ticker: str = Field(description="티커 심볼, 없으면 빈 문자열")
    display_name: str = Field(description="기업명 또는 기업명 (티커)")
    confidence: Literal["high", "medium", "low"] = Field(
        description="추출 신뢰도"
    )


class CompanyEntityExtractorInputDTO(ModuleInputDTO):
    """Input payload accepting either upstream VectorIndexDTO or standalone file selection."""

    index_input: Optional[VectorIndexDTO] = Field(
        default=None,
        description="pgvector Index Writer의 인덱스 출력 DTO (전달 시 DB 메타데이터에 즉시 영속화)",
    )
    file_name: Optional[str] = Field(
        default=None,
        description="처리할 Excel 파일명 (index_input 생략 시 직접 전달 가능)",
    )
    workbook_hash: Optional[str] = Field(
        default=None,
        description="파일 해시 (index_input 생략 시 직접 전달 가능)",
    )
    sheet_names: Optional[List[str]] = Field(
        default=None,
        description="표시 시트명 목록",
    )
    index_id: Optional[str] = Field(
        default=None,
        description="직접 지정할 pgvector 인덱스 ID",
    )

    @model_validator(mode="after")
    def resolve_fields(self) -> "CompanyEntityExtractorInputDTO":
        if self.index_input is not None:
            if not self.file_name:
                self.file_name = self.index_input.file_name
            if not self.workbook_hash:
                self.workbook_hash = self.index_input.workbook_hash
            if not self.index_id:
                self.index_id = self.index_input.index_id
        if not self.file_name:
            self.file_name = "unknown.xlsx"
        return self


class CompanyEntityExtractorConfigDTO(ModuleConfigDTO):
    model: str = Field(
        default=DEFAULT_ENTITY_EXTRACTOR_MODEL,
        description="기업 엔티티 추출에 사용할 LLM 모델",
    )
    allow_heuristic_fallback: bool = Field(
        default=True,
        description="LLM 추출 실패 시 파일명 기반 결과 사용 여부",
    )


class CompanyEntityExtractorOutputDTO(ModuleDTO):
    company_name: str = Field(default="", description="공식 기업명")
    ticker: str = Field(default="", description="티커 심볼 (없으면 빈 문자열)")
    display_name: str = Field(default="", description="'기업명 (TICKER)' 형식 표시명")
    index_id: Optional[str] = Field(default=None, description="메타데이터가 영속화된 pgvector 인덱스 ID")
    confidence: Literal["high", "medium", "low"] = Field(
        default="low",
        description="추출 신뢰도",
    )
    source: str = Field(default="heuristic", description="추출 방법 (llm / heuristic)")


class CompanyEntityExtractorModule(BaseLLMModule):
    """Extract company metadata with an LLM and persist directly into PostgreSQL pgvector DB."""

    definition: ClassVar[ModuleDefinition] = ModuleDefinition(
        type="company_entity_extractor",
        label="Company Entity Extractor & Persistence",
        category="Storage / DB",
        description="Excel 워크북에서 공식 기업명과 티커를 추출하고 pgvector DB 인덱스 및 청크에 즉시 영속화합니다.",
        inputs=["index_input", "input"],
        outputs=["company_output", "output"],
        config_fields=["model", "allow_heuristic_fallback"],
        raw_output=True,
        version="4",
    )
    input_model = CompanyEntityExtractorInputDTO
    config_model = CompanyEntityExtractorConfigDTO
    output_model = CompanyEntityExtractorOutputDTO

    def __init__(
        self,
        catalog: WorkbookCatalog | None = None,
        processed_dir: Path = PROCESSED_DATA_DIR,
        completion_client: Optional[Any] = None,
        pgvector_store: Optional[PgVectorStore] = None,
    ) -> None:
        super().__init__(completion_client=completion_client)
        self.catalog = catalog or WorkbookCatalog(processed_dir)
        self.pgvector_store = pgvector_store or PgVectorStore()

    @staticmethod
    def _heuristic(file_name: str) -> Dict[str, Any]:
        name = Path(file_name).stem.replace("_", " ").replace("-", " ").strip()
        return {
            "company_name": name,
            "ticker": "",
            "display_name": name,
            "confidence": "low",
            "source": "heuristic",
        }

    @staticmethod
    def _sample_workbook(path: Path, sheet_names: Optional[List[str]] = None) -> List[str]:
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        sampled: List[str] = []
        try:
            target_sheets = sheet_names[:2] if sheet_names else workbook.sheetnames[:2]
            for sheet_name in target_sheets:
                if sheet_name not in workbook.sheetnames:
                    continue
                sheet = workbook[sheet_name]
                lines: List[str] = []
                for row in sheet.iter_rows(values_only=True, max_row=8, max_col=10):
                    cells = [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]
                    if cells:
                        lines.append(" | ".join(cells[:10]))
                if lines:
                    sampled.append(f"[{sheet_name}]\n" + "\n".join(lines))
        finally:
            workbook.close()
        return sampled

    def execute(
        self,
        input_data: CompanyEntityExtractorInputDTO,
        config: Optional[CompanyEntityExtractorConfigDTO] = None,
    ) -> Dict[str, Any]:
        cfg = config or CompanyEntityExtractorConfigDTO()
        file_name = input_data.file_name or "unknown.xlsx"
        fallback = self._heuristic(file_name)
        target_index_id = input_data.index_id or (
            input_data.index_input.index_id if input_data.index_input else None
        )

        try:
            workbook_path = self.catalog.resolve(file_name)
            sampled_lines = self._sample_workbook(workbook_path, input_data.sheet_names)
        except Exception as error:
            logger.warning("기업 엔티티 셀 샘플링 실패: %s", error)
            sampled_lines = []

        if not sampled_lines:
            company_name = fallback["company_name"]
            ticker = fallback["ticker"]
            display_name = fallback["display_name"]
            confidence = fallback["confidence"]
            source = fallback["source"]
        else:
            sampled_text = "\n".join(sampled_lines)[:2500]
            context = (
                f"File Name: {file_name}\n"
                f"Sheet Names: {input_data.sheet_names or 'All'}\n\n"
                f"Top Cells Content:\n{sampled_text}"
            )

            try:
                parsed_res, _, _, _ = self.complete_structured(
                    messages_or_prompt=context,
                    response_model=CompanyEntityDocument,
                    model=cfg.model,
                    system_prompt=COMPANY_EXTRACTION_SYSTEM_PROMPT,
                )
                company_name = parsed_res.company_name.strip()
                ticker = parsed_res.ticker.strip()
                display_name = parsed_res.display_name.strip() or (
                    f"{company_name} ({ticker})" if ticker else company_name
                )
                if not display_name:
                    display_name = fallback["display_name"]
                    company_name = fallback["company_name"]
                confidence = parsed_res.confidence or "high"
                source = "llm"
            except Exception as error:
                if not cfg.allow_heuristic_fallback:
                    raise ProviderApiError(
                        f"기업 엔티티 LLM 추출 실패: {error}",
                        provider="llm",
                    ) from error
                logger.warning("기업 엔티티 LLM 추출 실패, 파일명 기반 결과 사용: %s", error)
                company_name = fallback["company_name"]
                ticker = fallback["ticker"]
                display_name = fallback["display_name"]
                confidence = fallback["confidence"]
                source = fallback["source"]

        # Persist directly into pgvector collection and chunk metadata if index_id is provided
        if target_index_id:
            try:
                self.pgvector_store.update_index_company(
                    target_index_id,
                    display_name or company_name,
                )
            except Exception as error:
                raise StorageError(
                    f"pgvector 기업 메타데이터 저장 실패: {error}"
                ) from error

        return {
            "index_id": target_index_id,
            "company_name": company_name or display_name,
            "ticker": ticker,
            "display_name": display_name,
            "confidence": confidence,
            "source": source,
        }


# Backward compatibility alias
CompanyEntityExtractorExecutionDTO = CompanyEntityExtractorInputDTO

__all__ = [
    "COMPANY_EXTRACTION_SYSTEM_PROMPT",
    "CompanyEntityExtractorConfigDTO",
    "CompanyEntityExtractorExecutionDTO",
    "CompanyEntityExtractorInputDTO",
    "CompanyEntityExtractorModule",
    "CompanyEntityExtractorOutputDTO",
]
