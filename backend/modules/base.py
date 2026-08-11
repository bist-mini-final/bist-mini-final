from abc import ABC, abstractmethod
from typing import Any, Dict, List, Mapping, Type

from pydantic import BaseModel, ConfigDict, Field


def select_schema_fields(
    schema: Dict[str, Any],
    field_names: List[str],
    title: str,
) -> Dict[str, Any]:
    """Create a focused JSON schema without mutating Pydantic's full schema."""

    selected = set(field_names)
    focused = dict(schema)
    focused["title"] = title
    focused["properties"] = {
        name: field_schema
        for name, field_schema in schema.get("properties", {}).items()
        if name in selected
    }
    required = [name for name in schema.get("required", []) if name in selected]
    if required:
        focused["required"] = required
    else:
        focused.pop("required", None)
    return focused


class ModuleDTO(BaseModel):
    """Strict DTO base so misspelled field names never disappear silently."""

    model_config = ConfigDict(extra="forbid")


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


class ExecutableModule(ABC):
    """Validates one module input and produces its named outputs."""

    definition: ModuleDefinition
    input_model: Type[BaseModel]
    output_model: Type[BaseModel]
    branch_output_models: Dict[str, Type[BaseModel]] = {}

    def cache_payload(self, payload: Any) -> Any:
        """Return the validated, default-filled input used to identify a result."""

        return self.input_model.model_validate(payload).model_dump(mode="json")

    def run(self, payload: Any) -> Any:
        validated_input = self.input_model.model_validate(payload)
        raw_output = self.execute(validated_input)
        validated_output = self.output_model.model_validate(raw_output)
        return validated_output.model_dump(mode="json")

    def contract(self) -> Dict[str, Any]:
        """Return the palette metadata and canonical JSON schemas."""

        execution_schema = self.input_model.model_json_schema()
        all_fields = list(execution_schema.get("properties", {}))
        unknown_config_fields = set(self.definition.config_fields) - set(all_fields)
        if unknown_config_fields:
            raise ModuleExecutionError(
                f"모듈 {self.definition.type}의 설정 필드가 실행 DTO에 없습니다: "
                + ", ".join(sorted(unknown_config_fields))
            )
        input_fields = [
            field for field in all_fields if field not in self.definition.config_fields
        ]
        if self.definition.raw_input and self.definition.config_fields:
            raise ModuleExecutionError(
                f"원본 입력 모듈 {self.definition.type}에는 설정 필드를 함께 둘 수 없습니다"
            )
        input_schema = (
            execution_schema
            if self.definition.raw_input
            else select_schema_fields(
                execution_schema,
                input_fields,
                f"{self.definition.type} input",
            )
        )
        return {
            **self.definition.model_dump(),
            "input_schema": input_schema,
            "config_schema": select_schema_fields(
                execution_schema,
                self.definition.config_fields,
                f"{self.definition.type} config",
            ),
            "output_schema": self.output_model.model_json_schema(),
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
