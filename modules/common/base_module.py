"""모든 RAG 파이프라인 모듈의 최상위 추상 기본 클래스(BaseModule) 및 공통 DTO 정의.

템플릿 메서드 패턴(`run()`), Pydantic 입력/출력/설정 계약 자동 검증,
에러 분류 래핑 및 Swagger OpenAPI 계약 명세 직렬화 기능을 제공합니다.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import logging
from abc import ABC, abstractmethod
from typing import (
    Any,
    ClassVar,
    Dict,
    Generic,
    List,
    Literal,
    Mapping,
    Optional,
    Type,
    TypeVar,
    cast,
)

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from modules.common.exceptions import (
    DocumentParsingError,
    ModuleExecutionError,
    ModuleValidationError,
    PipelineBaseError,
    ProviderApiError,
    StorageError,
)

InputModelT = TypeVar("InputModelT", bound=BaseModel)
OutputModelT = TypeVar("OutputModelT", bound=BaseModel)
ConfigModelT = TypeVar("ConfigModelT", bound=BaseModel)
logger = logging.getLogger(__name__)


class ModuleDTO(BaseModel):
    """Strict DTO base preventing typo/undefined fields from disappearing silently."""

    model_config = ConfigDict(extra="forbid")


def question_id_for(question_text: str) -> str:
    """Return a deterministic, stable content ID for correlating queries across the pipeline."""
    normalized = " ".join(question_text.split())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16].upper()
    return f"QUERY-{digest}"


class QueryContextDTO(ModuleDTO):
    """Identity and original text of the user query carried across pipeline nodes."""

    question_id: str = Field(
        min_length=1,
        description="전체 질의 파이프라인에서 유지되는 원본 질문 ID",
    )
    question_text: str = Field(
        min_length=1,
        description="검색·컨텍스트·답변이 참조하는 사용자의 원문 질문",
    )
    external_context_sources: List[str] = Field(
        default_factory=list,
        max_length=4,
        description=(
            "pgvector catalog 밖에서 답변 결합 단계에 제공되는 첨부 원천 이름. "
            "이 원천의 기업은 catalog retrieval 대상으로 강제하지 않습니다."
        ),
    )


class DocumentContextDTO(ModuleDTO):
    """Identity of the source document represented by retrieval-side data."""

    file_name: str = Field(
        min_length=1,
        description="검색 문서와 벡터 인덱스가 만들어진 원본 파일명",
    )
    workbook_hash: str = Field(
        min_length=1,
        description="원본 문서 버전을 식별하는 콘텐츠 해시",
    )
    index_id: Optional[str] = Field(
        default=None,
        description="검색 대상 pgvector 컬렉션 ID(다중 컬렉션은 쉼표로 구분)",
    )
    company_name: Optional[str] = Field(
        default=None,
        description="원본 문서가 대응하는 공식 기업명",
    )
    sheet_names: Optional[List[str]] = Field(
        default=None,
        description="원본 문서에 포함된 시트명 목록",
    )


class ModuleInputDTO(ModuleDTO):
    """Public data schema received from upstream workflow connections."""


class ModuleConfigDTO(ModuleDTO):
    """Module-owned configuration schema stored on a workflow node."""


class EmptyModuleConfigDTO(ModuleConfigDTO):
    """Explicit empty config contract for modules with no parameters."""


class ModuleExecutionRequestDTO(ModuleDTO):
    """Validated envelope used by the CLI and module execution API."""

    input: Any
    config: Any = None


# ==============================================================================
# Module Definition Metadata
# ==============================================================================
class ModuleTaskPolicy(BaseModel):
    """Declares execution concurrency and affinity constraints for runtime schedulers."""

    model_config = ConfigDict(extra="ignore")
    enabled: bool = True
    singleton: bool = False
    task_affinity: Literal["cpu", "gpu", "io", "network"] = "io"
    max_inflight: Optional[int] = Field(default=None, ge=1)
    retries: int = Field(default=0, ge=0)
    retry_delay_seconds: float = Field(default=1.0, ge=0)
    timeout_seconds: Optional[float] = Field(default=None, ge=0)
    tags: List[str] = Field(default_factory=list)
    resource_profile: Optional[str] = None


class ModuleConfigPreset(BaseModel):
    """A named configuration preset exposed to user interfaces and workflows."""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    description: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)


class ModuleDefinition(BaseModel):
    """Static capabilities and port contract declared by a pipeline module."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    type: str = Field(min_length=1)
    label: str = Field(min_length=1)
    category: str = Field(min_length=1)
    description: str = Field(min_length=1)
    inputs: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)
    config_fields: List[str] = Field(default_factory=list)
    branch_outputs: Dict[str, str] = Field(default_factory=dict)
    raw_output: bool = False
    raw_input: bool = False
    cacheable: bool = True
    presets: List[Any] = Field(default_factory=list)
    config_presets: List[Any] = Field(default_factory=list)
    task: Optional[ModuleTaskPolicy] = None
    task_policy: ModuleTaskPolicy = Field(default_factory=ModuleTaskPolicy)
    version: Optional[str] = None


class BaseModule(
    ABC,
    Generic[InputModelT, OutputModelT, ConfigModelT],
):
    """Pure abstract foundation for all runnable pipeline modules."""

    definition: ClassVar[ModuleDefinition]
    input_model: ClassVar[Type[BaseModel]]
    config_model: ClassVar[Type[BaseModel]]
    execution_model: ClassVar[Optional[Type[BaseModel]]] = None
    output_model: ClassVar[Type[BaseModel]]
    branch_output_models: ClassVar[Dict[str, Type[BaseModel]]] = {}

    def set_progress_callback(self, callback: Optional[Any]) -> None:
        """Attach a lightweight runtime callback without forcing every leaf to initialize it."""
        self._progress_callback = callback

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if getattr(cls, "__abstractmethods__", None):
            return
        if cls.__name__ in ("BaseLLMModule", "BaseModule", "BaseEmbeddingModule"):
            return
        if not hasattr(cls, "definition") or not isinstance(cls.definition, ModuleDefinition):
            return
        if not hasattr(cls, "input_model") or not issubclass(cls.input_model, BaseModel):
            raise TypeError(f"Module {cls.__name__} must declare 'input_model = SomeInputDTO'")
        if not hasattr(cls, "config_model") or not issubclass(cls.config_model, BaseModel):
            raise TypeError(f"Module {cls.__name__} must declare 'config_model = SomeConfigDTO'")
        if not hasattr(cls, "output_model") or not issubclass(cls.output_model, BaseModel):
            raise TypeError(f"Module {cls.__name__} must declare 'output_model = SomeOutputDTO'")

    def report_progress(self, payload: Dict[str, Any]) -> None:
        """Report progress when a runtime worker installed a callback."""
        callback = getattr(self, "_progress_callback", None)
        if callback is not None:
            callback(payload)

    @property
    def request_model(self) -> Type[BaseModel]:
        if self.execution_model is not None and self.execution_model is not self.input_model:
            return self.execution_model
        return self.input_model

    @property
    def input_fields(self) -> List[str]:
        return list(self.input_model.model_fields)

    @property
    def config_fields(self) -> List[str]:
        return list(self.config_model.model_fields)

    @property
    def required_input_fields(self) -> List[str]:
        return [
            name for name, field in self.input_model.model_fields.items() if field.is_required()
        ]

    def validate_config(self, config: Any = None) -> ConfigModelT:
        """Validate configuration parameters against the module config model."""
        return cast(
            ConfigModelT,
            self.config_model.model_validate({} if config is None else config),
        )

    def _validated_execution(
        self,
        input_payload: Any,
        config: Any,
    ) -> tuple[InputModelT, ConfigModelT, BaseModel]:
        """Validate input and config, automatically bridging them."""
        actual_input = (
            input_payload.model_dump() if isinstance(input_payload, BaseModel) else input_payload
        )
        actual_config = config.model_dump() if isinstance(config, BaseModel) else config

        if isinstance(actual_input, dict):
            input_fields = set(getattr(self.input_model, "model_fields", {}).keys())
            config_fields = set(getattr(self.config_model, "model_fields", {}).keys())

            unknown_fields = set(actual_input) - input_fields - config_fields
            if unknown_fields:
                unknown = ", ".join(sorted(unknown_fields))
                raise ValueError(f"알 수 없는 입력 필드입니다: {unknown}")

            if input_fields:
                input_data = {k: v for k, v in actual_input.items() if k in input_fields}
            else:
                input_data = actual_input

            if actual_config is None and config_fields:
                cfg_data = {k: v for k, v in actual_input.items() if k in config_fields}
                if cfg_data:
                    actual_config = cfg_data
            actual_input = input_data

        validated_input = cast(
            InputModelT,
            self.input_model.model_validate(actual_input),
        )
        validated_config = self.validate_config(actual_config)
        if (
            self.definition.raw_input
            or self.execution_model is None
            or self.execution_model is self.input_model
        ):
            execution_payload = validated_input
        else:
            execution_values = validated_input.model_dump(mode="python")
            execution_values.update(validated_config.model_dump(mode="python"))
            execution_payload = self.execution_model.model_validate(execution_values)
        return validated_input, validated_config, execution_payload

    def run(self, input_payload: Any, config: Any = None) -> Dict[str, Any]:
        """Execute the module with given input and config, returning validated output with standardized error wrapping."""
        mod_type = (
            getattr(self, "definition", None) and getattr(self.definition, "type", None)
        ) or self.__class__.__name__

        try:
            validated_input, validated_config, execution_payload = self._validated_execution(
                input_payload, config
            )
        except ValidationError as error:
            raise ModuleValidationError(
                f"모듈 [{mod_type}] 입력/설정 검증 실패: {error}",
                module_type=mod_type,
                details={"errors": error.errors(include_url=False)},
            ) from error
        except Exception as error:
            raise ModuleValidationError(
                f"모듈 [{mod_type}] 입력 데이터 처리 중 오류: {error}",
                module_type=mod_type,
            ) from error

        try:
            sig = inspect.signature(self.execute)
            params = [
                p
                for p in sig.parameters.values()
                if p.name != "self" and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
            ]
            if len(params) >= 2:
                raw_output = self.execute(validated_input, validated_config)
            else:
                # execution_model may intentionally combine input and config
                # into a different DTO for legacy single-argument modules.
                raw_output = self.execute(cast(Any, execution_payload))
        except PipelineBaseError as error:
            classified = self._classify_execution_error(error, mod_type)
            if classified is not error:
                raise classified from error
            if error.module_type is None:
                error.module_type = mod_type
            raise
        except Exception as error:
            raise self._classify_execution_error(error, mod_type) from error

        try:
            validated_output = self.output_model.model_validate(raw_output)
            return validated_output.model_dump(mode="json")
        except ValidationError as error:
            raise ModuleExecutionError(
                f"모듈 [{mod_type}] 출력 스키마 불일치: {error}",
                module_type=mod_type,
                details={"errors": error.errors(include_url=False)},
            ) from error

    async def run_async(
        self,
        input_payload: Any,
        config: Any = None,
    ) -> Dict[str, Any]:
        """Execute a native async implementation or adapt the sync module safely.

        Existing modules keep their original behavior in a worker thread. Modules
        that override :meth:`execute_async` are validated and error-classified with
        the same contract as :meth:`run`, while their provider/storage awaits stay
        on the workflow event loop.
        """
        if type(self).execute_async is BaseModule.execute_async:
            return await asyncio.to_thread(self.run, input_payload, config)

        mod_type = (
            getattr(self, "definition", None) and getattr(self.definition, "type", None)
        ) or self.__class__.__name__

        try:
            validated_input, validated_config, execution_payload = self._validated_execution(
                input_payload, config
            )
        except ValidationError as error:
            raise ModuleValidationError(
                f"모듈 [{mod_type}] 입력/설정 검증 실패: {error}",
                module_type=mod_type,
                details={"errors": error.errors(include_url=False)},
            ) from error
        except Exception as error:
            raise ModuleValidationError(
                f"모듈 [{mod_type}] 입력 데이터 처리 중 오류: {error}",
                module_type=mod_type,
            ) from error

        try:
            sig = inspect.signature(self.execute_async)
            params = [
                parameter
                for parameter in sig.parameters.values()
                if parameter.name != "self"
                and parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
            ]
            if len(params) >= 2:
                raw_output = await self.execute_async(
                    validated_input,
                    validated_config,
                )
            else:
                raw_output = await self.execute_async(cast(Any, execution_payload))
        except PipelineBaseError as error:
            classified = self._classify_execution_error(error, mod_type)
            if classified is not error:
                raise classified from error
            if error.module_type is None:
                error.module_type = mod_type
            raise
        except Exception as error:
            raise self._classify_execution_error(error, mod_type) from error

        try:
            validated_output = self.output_model.model_validate(raw_output)
            return validated_output.model_dump(mode="json")
        except ValidationError as error:
            raise ModuleExecutionError(
                f"모듈 [{mod_type}] 출력 스키마 불일치: {error}",
                module_type=mod_type,
                details={"errors": error.errors(include_url=False)},
            ) from error

    async def execute_async(
        self,
        input_data: InputModelT,
        config: Optional[ConfigModelT] = None,
    ) -> OutputModelT | Mapping[str, Any]:
        """Compatibility hook for modules that only implement synchronous I/O."""
        return await asyncio.to_thread(self.execute, input_data, config)

    def contract(self) -> Dict[str, Any]:
        """Return the module definition and canonical JSON schemas for UI."""
        return {
            **self.definition.model_dump(),
            "documentation_url": f"/api/modules/{self.definition.type}/docs",
            "input_schema": self.input_model.model_json_schema(),
            "config_schema": self.config_model.model_json_schema(),
            "output_schema": self.output_model.model_json_schema(),
            "execution_schema": self.request_model.model_json_schema(),
            "branch_schemas": {
                branch: model.model_json_schema()
                for branch, model in self.branch_output_models.items()
            },
        }

    @staticmethod
    def _classify_execution_error(
        error: Exception,
        module_type: str,
    ) -> PipelineBaseError:
        """Map provider, storage and workbook failures to stable API error contracts."""
        if isinstance(
            error, (ProviderApiError, StorageError, DocumentParsingError, ModuleValidationError)
        ):
            return error

        error_name = type(error).__name__.lower()
        error_module = type(error).__module__.lower()
        message = str(error)
        lowered = message.lower()

        provider_markers = (
            "openai",
            "api_key",
            "rate limit",
            "timeout",
            "connection refused",
            "chatcompletion",
            "visionerror",
        )
        if (
            "provider" in error_module
            or any(marker in error_name for marker in ("chatcompletion", "vision", "provider"))
            or any(marker in lowered for marker in provider_markers)
        ):
            return ProviderApiError(
                f"모듈 [{module_type}] 외부 API 호출 실패: {message}",
                module_type=module_type,
            )

        storage_markers = ("psycopg", "sqlalchemy", "pgvector", "database", "storage")
        if any(marker in error_name for marker in storage_markers) or any(
            marker in error_module for marker in storage_markers
        ):
            return StorageError(
                f"모듈 [{module_type}] 저장소 처리 실패: {message}",
                module_type=module_type,
            )

        document_markers = ("openpyxl", "workbook", "worksheet", "excel")
        if any(marker in error_module for marker in document_markers):
            return DocumentParsingError(
                f"모듈 [{module_type}] 문서 처리 실패: {message}",
                module_type=module_type,
            )

        if isinstance(error, PipelineBaseError):
            return error
        return ModuleExecutionError(
            f"모듈 [{module_type}] 실행 중 오류: {message}",
            module_type=module_type,
        )

    def execution_outcome(
        self,
        output: Any,
        cache_hit: bool,
    ) -> Literal["generated", "cached"]:
        """Resolve a control-flow branch from this module's declared output ports."""
        matching_branches = [
            branch
            for branch, port in self.definition.branch_outputs.items()
            if isinstance(output, Mapping) and port in output
        ]
        if len(matching_branches) == 1:
            return cast(Literal["generated", "cached"], matching_branches[0])
        if self.definition.branch_outputs:
            raise ModuleExecutionError(
                f"모듈 {self.definition.type}의 출력 분기를 결정할 수 없습니다"
            )
        return "cached" if cache_hit else "generated"

    @abstractmethod
    def execute(
        self,
        input_data: InputModelT,
        config: Optional[ConfigModelT] = None,
    ) -> OutputModelT | Mapping[str, Any]:
        """Execute the module with validated input_data and optional config."""


__all__ = [
    "BaseModule",
    "ConfigModelT",
    "DocumentContextDTO",
    "DocumentParsingError",
    "EmptyModuleConfigDTO",
    "ModuleConfigDTO",
    "ModuleConfigPreset",
    "ModuleDTO",
    "ModuleDefinition",
    "ModuleExecutionError",
    "ModuleExecutionRequestDTO",
    "ModuleInputDTO",
    "ModuleTaskPolicy",
    "ModuleValidationError",
    "InputModelT",
    "PipelineBaseError",
    "ProviderApiError",
    "OutputModelT",
    "QueryContextDTO",
    "StorageError",
    "question_id_for",
]
