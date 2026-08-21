"""Clean, strictly-typed base abstractions for all modular RAG pipeline components."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import Any, Callable, ClassVar, Dict, List, Literal, Mapping, Optional, Type, cast

from pydantic import BaseModel, ConfigDict, Field, create_model


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


class ModuleInputDTO(ModuleDTO):
    """Public data schema received from upstream workflow connections."""


class ModuleConfigDTO(ModuleDTO):
    """Module-owned configuration schema stored on a workflow node."""


class EmptyModuleConfigDTO(ModuleConfigDTO):
    """Explicit empty config contract for modules with no parameters."""


class ModuleExecutionRequestDTO(ModuleDTO):
    """Stable independent-execution envelope used by the HTTP API and CLI."""

    input: Any = Field(description="모듈의 공개 Input DTO")
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="워크플로 연결과 분리된 모듈 설정 DTO",
    )


class ModuleConfigPreset(BaseModel):
    """Preset configuration option for quick selection in UI."""

    id: str
    label: str
    values: Dict[str, Any]


class ModuleTaskPolicy(BaseModel):
    """Portable execution policy for Kubernetes worker scheduling."""

    engine: Literal["kubernetes"] = "kubernetes"
    enabled: bool = True
    retries: int = Field(default=0, ge=0, le=20)
    retry_delay_seconds: float = Field(default=0, ge=0, le=3600)
    timeout_seconds: Optional[float] = Field(default=None, gt=0, le=86400)
    tags: List[str] = Field(default_factory=list)
    resource_profile: Literal[
        "interactive",
        "standard",
        "high-memory",
        "gpu",
    ] = "standard"


class ModuleDefinition(BaseModel):
    """Public contract used by the frontend workflow palette and backend registry."""

    type: str
    label: str
    category: str
    description: str
    inputs: List[str]
    outputs: List[str]
    branch_outputs: Dict[str, str] = Field(default_factory=dict)
    config_fields: List[str] = Field(default_factory=list)
    config_presets: List[ModuleConfigPreset] = Field(default_factory=list)
    raw_input: bool = False
    raw_output: bool = False
    version: str = "1"
    cacheable: bool = True
    task: ModuleTaskPolicy = Field(default_factory=ModuleTaskPolicy)


class ModuleExecutionError(ValueError):
    """Raised when module execution fails during computation."""


class ExecutableModule(ABC):
    """Abstract Base Class for all RAG pipeline modules.

    Enforces strict Input, Config, Execution, and Output DTO layers.
    """

    definition: ClassVar[ModuleDefinition]
    input_model: ClassVar[Type[BaseModel]]
    config_model: ClassVar[Type[BaseModel]]
    execution_model: ClassVar[Type[BaseModel]]
    output_model: ClassVar[Type[BaseModel]]
    request_model: ClassVar[Type[BaseModel]]
    branch_output_models: ClassVar[Dict[str, Type[BaseModel]]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Validate DTO declarations on subclass definition."""
        super().__init_subclass__(**kwargs)
        definition = cls.__dict__.get("definition")
        if definition is None:
            return

        if not cls.__doc__:
            cls.__doc__ = definition.description

        declared_input_model = cls.__dict__.get("input_model")
        declared_config_model = cls.__dict__.get("config_model")
        declared_execution_model = cls.__dict__.get("execution_model")

        if declared_input_model is not None and declared_config_model is not None:
            cls.input_model = declared_input_model
            cls.config_model = declared_config_model
            if declared_execution_model is None:
                declared_execution_model = declared_input_model
            cls.execution_model = declared_execution_model

            input_fields = set(declared_input_model.model_fields)
            config_fields = set(declared_config_model.model_fields)
            if input_fields.intersection(config_fields):
                raise TypeError(
                    f"모듈 {definition.type}의 Input/Config DTO 필드가 중복됩니다: "
                    + ", ".join(sorted(input_fields.intersection(config_fields)))
                )
        elif declared_execution_model is not None:
            cls.execution_model = declared_execution_model
            cls.input_model = declared_execution_model
            cls.config_model = EmptyModuleConfigDTO

        # Prepare HTTP/CLI request wrapper model
        cls.request_model = create_model(
            f"{definition.type.title().replace('_', '')}ExecutionRequestDTO",
            __base__=ModuleDTO,
            input=(cls.input_model, Field(description="모듈 Input DTO")),
            config=(
                cls.config_model,
                Field(default_factory=cls.config_model, description="모듈 Config DTO"),
            ),
        )

    def set_progress_callback(
        self,
        callback: Optional[Callable[[Dict[str, Any]], None]],
    ) -> None:
        """Attach or clear progress update callback."""
        self._progress_callback = callback

    def report_progress(self, progress: Mapping[str, Any]) -> None:
        """Publish execution progress to registered callback."""
        callback = getattr(self, "_progress_callback", None)
        if callback is not None:
            callback(dict(progress))

    @property
    def input_fields(self) -> List[str]:
        return list(self.input_model.model_fields)

    @property
    def config_fields(self) -> List[str]:
        return list(self.config_model.model_fields)

    @property
    def required_input_fields(self) -> List[str]:
        return [
            name
            for name, field in self.input_model.model_fields.items()
            if field.is_required()
        ]

    def validate_config(self, config: Any = None) -> BaseModel:
        """Validate configuration parameters against the module config model."""
        return self.config_model.model_validate({} if config is None else config)

    def _validated_execution(
        self,
        input_payload: Any,
        config: Any,
    ) -> tuple[BaseModel, BaseModel, BaseModel]:
        """Validate input and config, producing the unified execution model."""
        validated_input = self.input_model.model_validate(input_payload)
        validated_config = self.validate_config(config)
        if self.definition.raw_input or self.execution_model is self.input_model:
            execution_payload = validated_input
        else:
            execution_values = validated_input.model_dump(mode="python")
            execution_values.update(validated_config.model_dump(mode="python"))
            execution_payload = self.execution_model.model_validate(execution_values)
        return validated_input, validated_config, execution_payload

    def cache_payload(self, input_payload: Any, config: Any = None) -> Dict[str, Any]:
        """Return a normalized, deterministic dictionary for in-memory caching."""
        validated_input, validated_config, _ = self._validated_execution(
            input_payload,
            config,
        )
        return {
            "input": validated_input.model_dump(mode="json"),
            "config": validated_config.model_dump(mode="json"),
        }

    def run(self, input_payload: Any, config: Any = None) -> Dict[str, Any]:
        """Execute the module with given input and config, returning validated output."""
        _, _, execution_payload = self._validated_execution(input_payload, config)
        raw_output = self.execute(execution_payload)
        validated_output = self.output_model.model_validate(raw_output)
        return validated_output.model_dump(mode="json")

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
    def execute(self, payload: BaseModel) -> Any:
        """Execute the module with an already validated input model."""


# Canonical alias for Pythonic naming
BaseModule = ExecutableModule
