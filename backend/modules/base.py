from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Any, Callable, ClassVar, Dict, List, Mapping, Optional, Type

from pydantic import BaseModel, ConfigDict, Field, create_model


class ModuleDTO(BaseModel):
    """Strict DTO base so misspelled field names never disappear silently."""

    model_config = ConfigDict(extra="forbid")


class ModuleInputDTO(ModuleDTO):
    """Public JSON received from a module's upstream connection or caller."""


class ModuleConfigDTO(ModuleDTO):
    """Module-owned settings stored on a workflow node."""


class EmptyModuleConfigDTO(ModuleConfigDTO):
    """Explicit config contract for modules with no settings."""


class ModuleExecutionRequestDTO(ModuleDTO):
    """Stable independent-execution envelope used by the HTTP API and CLI."""

    input: Any = Field(description="모듈의 공개 Input DTO JSON")
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="워크플로 연결과 분리된 모듈 설정 DTO JSON",
    )


class ModuleConfigPreset(BaseModel):
    id: str
    label: str
    values: Dict[str, Any]


class ModuleDefinition(BaseModel):
    """Public contract used by the frontend module palette."""

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


class ModuleExecutionError(ValueError):
    """Raised when a valid payload cannot be executed with the cached data."""


_UNSET = object()


def focused_dto_model(
    source_model: Type[BaseModel],
    field_names: List[str],
    model_name: str,
    base_model: Type[BaseModel],
) -> Type[BaseModel]:
    """Build a real Pydantic DTO from one side of a legacy execution model."""

    model_fields: Dict[str, Any] = {}
    for field_name in field_names:
        field = deepcopy(source_model.model_fields[field_name])
        model_fields[field_name] = (field.annotation, field)
    return create_model(model_name, __base__=base_model, **model_fields)


class ExecutableModule(ABC):
    """Run one module through separate Input, Config, and Output DTO layers.

    Implementations receive their combined execution model in ``execute``.  That
    model is an internal adapter only: callers and workflow orchestration validate
    and transport input/config independently.
    """

    definition: ClassVar[ModuleDefinition]
    input_model: ClassVar[Type[BaseModel]]
    config_model: ClassVar[Type[BaseModel]]
    execution_model: ClassVar[Type[BaseModel]]
    output_model: ClassVar[Type[BaseModel]]
    request_model: ClassVar[Type[BaseModel]]
    branch_output_models: ClassVar[Dict[str, Type[BaseModel]]] = {}

    def set_progress_callback(
        self,
        callback: Optional[Callable[[Dict[str, Any]], None]],
    ) -> None:
        """Attach a run-scoped progress sink without coupling modules to workflows."""

        self._progress_callback = callback

    def report_progress(self, progress: Mapping[str, Any]) -> None:
        """Publish JSON-compatible progress when the current executor supports it."""

        callback = getattr(self, "_progress_callback", None)
        if callback is not None:
            callback(dict(progress))

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Validate DTO boundaries and materialize the execution request DTO."""

        super().__init_subclass__(**kwargs)
        definition = cls.__dict__.get("definition")
        declared_input_model = cls.__dict__.get("input_model")
        declared_config_model = cls.__dict__.get("config_model")
        declared_execution_model = cls.__dict__.get("execution_model")
        if definition is None:
            return
        if not cls.__doc__:
            cls.__doc__ = definition.description

        if declared_input_model is not None or declared_config_model is not None:
            if declared_input_model is None or declared_config_model is None:
                raise TypeError(
                    f"모듈 {definition.type}은 input_model과 config_model을 함께 선언해야 합니다"
                )
            cls.input_model = declared_input_model
            cls.config_model = declared_config_model
            if declared_execution_model is None:
                if declared_config_model.model_fields:
                    raise TypeError(
                        f"설정이 있는 모듈 {definition.type}은 execution_model을 선언해야 합니다"
                    )
                declared_execution_model = declared_input_model
            cls.execution_model = declared_execution_model

            input_fields = set(declared_input_model.model_fields)
            config_fields = set(declared_config_model.model_fields)
            if input_fields.intersection(config_fields):
                raise TypeError(
                    f"모듈 {definition.type}의 Input/Config DTO 필드가 겹칩니다: "
                    + ", ".join(sorted(input_fields.intersection(config_fields)))
                )
            if config_fields != set(definition.config_fields):
                raise TypeError(
                    f"모듈 {definition.type}의 Config DTO와 config_fields 선언이 다릅니다"
                )
            if not definition.raw_input:
                execution_fields = set(declared_execution_model.model_fields)
                expected_fields = input_fields | config_fields
                if execution_fields != expected_fields:
                    raise TypeError(
                        f"모듈 {definition.type}의 Execution DTO 필드가 Input/Config 합계와 다릅니다"
                    )
        else:
            if declared_execution_model is None:
                return

            all_fields = list(declared_execution_model.model_fields)
            unknown_config_fields = set(definition.config_fields) - set(all_fields)
            if unknown_config_fields:
                raise TypeError(
                    f"모듈 {definition.type}의 설정 필드가 실행 DTO에 없습니다: "
                    + ", ".join(sorted(unknown_config_fields))
                )
            if definition.raw_input and definition.config_fields:
                raise TypeError(
                    f"원본 입력 모듈 {definition.type}에는 설정 필드를 함께 둘 수 없습니다"
                )

            cls.execution_model = declared_execution_model
            focused_input_fields = [
                field_name
                for field_name in all_fields
                if field_name not in definition.config_fields
            ]
            cls.input_model = (
                declared_execution_model
                if definition.raw_input
                else focused_dto_model(
                    declared_execution_model,
                    focused_input_fields,
                    f"{definition.type.title().replace('_', '')}InputDTO",
                    ModuleInputDTO,
                )
            )
            cls.config_model = focused_dto_model(
                declared_execution_model,
                list(definition.config_fields),
                f"{definition.type.title().replace('_', '')}ConfigDTO",
                ModuleConfigDTO,
            )
        cls.request_model = create_model(
            f"{definition.type.title().replace('_', '')}ExecutionRequestDTO",
            __base__=ModuleDTO,
            input=(cls.input_model, Field(description="모듈 Input DTO")),
            config=(
                cls.config_model,
                Field(default_factory=cls.config_model, description="모듈 Config DTO"),
            ),
        )

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
        return self.config_model.model_validate({} if config is None else config)

    def _validated_execution(
        self,
        input_payload: Any,
        config: Any,
    ) -> tuple[BaseModel, BaseModel, BaseModel]:
        validated_input = self.input_model.model_validate(input_payload)
        validated_config = self.validate_config(config)
        if self.definition.raw_input:
            execution_payload = validated_input
        else:
            execution_values = validated_input.model_dump(mode="python")
            execution_values.update(validated_config.model_dump(mode="python"))
            execution_payload = self.execution_model.model_validate(execution_values)
        return validated_input, validated_config, execution_payload

    def _legacy_request(self, payload: Any) -> tuple[Any, Dict[str, Any]]:
        """Split the pre-refactor combined Python payload for local compatibility."""

        if self.definition.raw_input:
            return payload, {}
        if isinstance(payload, BaseModel):
            payload = payload.model_dump(mode="python")
        if not isinstance(payload, Mapping):
            # Let the focused input DTO produce the canonical validation error.
            return payload, {}
        # Run compatibility migrations (for example legacy settings discarded by
        # a ``model_validator(mode="before")``) before enforcing the new layers.
        normalized_payload = self.execution_model.model_validate(payload).model_dump(
            mode="python"
        )
        config_names = set(self.config_fields)
        return (
            {
                key: value
                for key, value in normalized_payload.items()
                if key not in config_names
            },
            {
                key: value
                for key, value in normalized_payload.items()
                if key in config_names
            },
        )

    def cache_payload(self, input_payload: Any, config: Any = _UNSET) -> Any:
        """Return a default-filled, explicitly layered cache identity."""

        if config is _UNSET:
            input_payload, config = self._legacy_request(input_payload)
        validated_input, validated_config, _ = self._validated_execution(
            input_payload,
            config,
        )
        return {
            "input": validated_input.model_dump(mode="json"),
            "config": validated_config.model_dump(mode="json"),
        }

    def run(self, input_payload: Any, config: Any = _UNSET) -> Any:
        """Execute from separate JSON values; combined Python payloads remain supported."""

        if config is _UNSET:
            input_payload, config = self._legacy_request(input_payload)
        _, _, execution_payload = self._validated_execution(input_payload, config)
        raw_output = self.execute(execution_payload)
        validated_output = self.output_model.model_validate(raw_output)
        return validated_output.model_dump(mode="json")

    def contract(self) -> Dict[str, Any]:
        """Return the palette metadata and canonical JSON schemas."""

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
    ) -> str:
        """Resolve a control-flow branch from this module's declared output ports."""

        matching_branches = [
            branch
            for branch, port in self.definition.branch_outputs.items()
            if isinstance(output, Mapping) and port in output
        ]
        if len(matching_branches) == 1:
            return matching_branches[0]
        if self.definition.branch_outputs:
            raise ModuleExecutionError(
                f"모듈 {self.definition.type}의 출력 분기를 결정할 수 없습니다"
            )
        return "cached" if cache_hit else "generated"

    @abstractmethod
    def execute(self, payload: BaseModel) -> Any:
        """Execute the module with an already validated input model."""
