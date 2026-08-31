"""Generate and persist one shared semantic profile after workbook indexing."""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field

from backend.domains.data_sources.infrastructure.spreadsheets.workbook_catalog import (
    WorkbookCatalog,
)
from backend.domains.data_sources.infrastructure.spreadsheets.workbook_profile_extractor import (
    WorkbookProfileExtractor,
)
from modules.common.base_module import (
    BaseModule,
    EmptyModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
)
from modules.common.exceptions import DocumentParsingError, StorageError
from modules.storage.pgvector_index_writer import VectorIndexDTO
from modules.storage.ports import WorkbookProfileRepositoryPort
from modules.structure.luna_vlm_structure_detector import SpreadsheetStructureOutput


class WorkbookProfilePersistenceInputDTO(ModuleDTO):
    structure_input: SpreadsheetStructureOutput = Field(
        description="원본 워크북과 감지된 표 구조",
    )
    index_input: VectorIndexDTO = Field(
        description="저장이 완료된 벡터 인덱스 식별자",
    )


class WorkbookProfilePersistenceOutputDTO(ModuleDTO):
    profile_version: str
    status: str
    period_count: int = Field(ge=0)
    currency: str | None = None
    amount_scale: str | None = None
    diagnostics: list[str] = Field(default_factory=list)


_DEFINITION = ModuleDefinition(
    type="workbook_profile_persistence",
    label="Workbook Profile Persistence",
    category="Storage / DB",
    description="원본 워크북의 통화·단위·기간·시트 역할 프로필을 공통 저장합니다.",
    inputs=["structure_input", "index_input"],
    outputs=["output"],
    config_fields=[],
    raw_output=True,
    cacheable=False,
    version="1",
)


class WorkbookProfilePersistenceModule(BaseModule):
    definition: ClassVar[ModuleDefinition] = _DEFINITION
    input_model = WorkbookProfilePersistenceInputDTO
    config_model = EmptyModuleConfigDTO
    output_model = WorkbookProfilePersistenceOutputDTO

    def __init__(
        self,
        *,
        profiles: WorkbookProfileRepositoryPort,
        catalog: WorkbookCatalog,
        extractor: WorkbookProfileExtractor | None = None,
    ) -> None:
        super().__init__()
        self._profiles = profiles
        self._catalog = catalog
        self._extractor = extractor or WorkbookProfileExtractor()

    def execute(
        self,
        input_data: WorkbookProfilePersistenceInputDTO,
        config: EmptyModuleConfigDTO | None = None,
    ) -> dict[str, object]:
        structure = input_data.structure_input
        index = input_data.index_input
        if structure.workbook_hash != index.workbook_hash:
            raise ModuleExecutionError("구조 분석과 인덱스의 workbook_hash가 다릅니다")
        try:
            profile = self._extractor.extract(
                workbook_path=self._catalog.resolve(structure.file_name),
                structure=structure,
                index_id=index.index_id,
            )
        except Exception as error:
            raise DocumentParsingError(f"워크북 프로필 생성 실패: {error}") from error
        try:
            stored = self._profiles.save(profile)
        except Exception as error:
            raise StorageError(f"워크북 프로필 저장 실패: {error}") from error
        return {
            "profile_version": stored.profile_version,
            "status": stored.status,
            "period_count": len(stored.periods),
            "currency": stored.currency,
            "amount_scale": stored.amount_scale.value if stored.amount_scale else None,
            "diagnostics": list(stored.diagnostics),
        }


__all__ = [
    "WorkbookProfilePersistenceInputDTO",
    "WorkbookProfilePersistenceModule",
    "WorkbookProfilePersistenceOutputDTO",
]
