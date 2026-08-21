"""
Image Tile Source
─────────────────
PixelRAG 시연용 Source 모듈.

data/artifacts/spreadsheets/ 아래의 스프레드시트 렌더링 이미지에서
행 단위 이미지 타일 목록과 메타데이터를 출력합니다.
실제 PixelRAG 파이프라인에서 Qwen3-VL 임베딩 단계의 입력으로 사용됩니다.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional, Any, Dict, List, Optional, cast

from pydantic import BaseModel, Field

from backend.core.settings import PROCESSED_DATA_DIR, SPREADSHEET_ARTIFACT_DIR
from backend.storage.spreadsheets.workbook_catalog import WorkbookCatalog, WorkbookCatalogError
from modules.common.base_module import (
    BaseModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleInputDTO,
)


class ImageTileSourceInputDTO(ModuleInputDTO):
    file_name: str = Field(
        min_length=1,
        description="data/source_files에서 선택할 Excel 파일명 (이미지 타일 소스로 사용)",
    )
    sheet_name: Optional[str] = Field(
        default=None,
        description="특정 시트만 선택. 비워두면 모든 시트 포함",
    )


class ImageTileSourceConfigDTO(ModuleConfigDTO):
    tile_height_px: int = Field(
        default=64,
        ge=16,
        le=512,
        description="행 단위 타일 높이 (픽셀). PixelRAG 타일링 단위와 일치해야 합니다",
    )
    max_tiles: int = Field(
        default=500,
        ge=1,
        le=5000,
        description="출력할 최대 타일 수",
    )


class ImageTileSourceExecutionDTO(ImageTileSourceInputDTO, ImageTileSourceConfigDTO):
    """Internal union of source selection and tiling policy."""


class ImageTileDTO(ModuleDTO):
    tile_id: str = Field(description="타일 고유 ID (sheet_row 형식)")
    sheet_name: str
    row_range: List[int] = Field(description="[row_start, row_end] 픽셀 범위")
    relative_path: str = Field(description="data/artifacts/spreadsheets/ 기준 상대 경로")
    exists: bool = Field(description="실제 파일 존재 여부")


class ImageTileSourceOutput(ModuleDTO):
    file_name: str
    workbook_hash: str
    total_tiles: int
    tile_height_px: int
    tiles: List[ImageTileDTO]
    artifact_dir: str = Field(description="이미지 타일 저장 기준 디렉터리")
    pipeline_note: str = Field(
        default=(
            "PixelRAG: 각 타일을 Qwen3-VL-Embedding-2B로 벡터화하여 "
            "FAISS 인덱스에 저장한 뒤 VLM(GPT-5.6 Luna)으로 답변을 생성합니다."
        )
    )


class ImageTileSourceModule(BaseModule):
    definition = ModuleDefinition(
        type="image_tile_source",
        label="Image Tile Source (PixelRAG)",
        category="Source",
        description=(
            "Excel 시트를 행 단위로 타일링한 이미지 목록을 출력합니다. "
            "PixelRAG 파이프라인에서 Qwen3-VL 비전 임베딩의 입력으로 사용됩니다. "
            "타일은 data/artifacts/spreadsheets/ 경로에 사전 렌더링되어야 합니다."
        ),
        inputs=[],
        outputs=["output"],
        config_fields=["tile_height_px", "max_tiles"],
        raw_output=True,
        version="1",
    )
    input_model = ImageTileSourceInputDTO
    config_model = ImageTileSourceConfigDTO
    execution_model = ImageTileSourceExecutionDTO
    output_model = ImageTileSourceOutput

    def __init__(self, processed_dir: Path = PROCESSED_DATA_DIR) -> None:
        self.catalog = WorkbookCatalog(processed_dir)
        self.artifact_dir = SPREADSHEET_ARTIFACT_DIR

    def contract(self) -> Dict[str, Any]:
        contract = super().contract()
        available = self.catalog.file_names()
        file_schema = contract["input_schema"]["properties"]["file_name"]
        file_schema["enum"] = available
        if available:
            file_schema["default"] = available[0]
        return contract

    def execute(
        self,
        input_data: ImageTileSourceInputDTO,
        config: Optional[ImageTileSourceConfigDTO] = None,
    ) -> Dict[str, Any]:
        if config is None and isinstance(input_data, ImageTileSourceExecutionDTO):
            cfg = input_data
        else:
            cfg = config or ImageTileSourceConfigDTO()

        try:
            path = self.catalog.resolve(input_data.file_name)
            sheet_names = self.catalog.sheet_names(path)
        except (OSError, ValueError, WorkbookCatalogError) as err:
            raise ModuleExecutionError(str(err)) from err

        workbook_hash = hashlib.sha256(path.read_bytes()).hexdigest()[:16]

        if input_data.sheet_name:
            if input_data.sheet_name not in sheet_names:
                raise ModuleExecutionError(
                    f"시트를 찾을 수 없습니다: {input_data.sheet_name}"
                )
            sheets_to_process = [input_data.sheet_name]
        else:
            sheets_to_process = sheet_names

        tiles: List[Dict[str, Any]] = []
        tile_h = cfg.tile_height_px
        stem = path.stem

        # Generate tile metadata (actual rendering is a preprocessing step)
        # Estimate ~200 rows per sheet at typical row height
        ESTIMATED_ROWS_PER_SHEET = 200
        PIXELS_PER_ROW = 20  # ~20px per Excel row at standard zoom

        for sheet in sheets_to_process:
            total_height_px = ESTIMATED_ROWS_PER_SHEET * PIXELS_PER_ROW
            tile_index = 0
            y = 0
            while y < total_height_px and len(tiles) < cfg.max_tiles:
                tile_id = f"{sheet}_row{tile_index:04d}"
                rel_path = f"{stem}/{sheet}/tile_{tile_index:04d}.webp"
                abs_path = self.artifact_dir / rel_path
                tiles.append(
                    ImageTileDTO(
                        tile_id=tile_id,
                        sheet_name=sheet,
                        row_range=[y, min(y + tile_h, total_height_px)],
                        relative_path=rel_path,
                        exists=abs_path.is_file(),
                    ).model_dump()
                )
                y += tile_h
                tile_index += 1

        return {
            "file_name": path.name,
            "workbook_hash": workbook_hash,
            "total_tiles": len(tiles),
            "tile_height_px": tile_h,
            "tiles": tiles,
            "artifact_dir": str(self.artifact_dir),
            "pipeline_note": (
                "PixelRAG: 각 타일을 Qwen3-VL-Embedding-2B로 벡터화하여 "
                "FAISS 인덱스에 저장한 뒤 VLM(GPT-5.6 Luna)으로 답변을 생성합니다."
            ),
        }
