from typing import Any, cast

from pydantic import BaseModel, Field, RootModel

from .base import EmptyModuleConfigDTO, ExecutableModule, ModuleDefinition


class JsonInspectorInputDTO(RootModel[Any]):
    root: Any = Field(description="상류 모듈에서 전달된 원본 JSON 값")


class JsonInspectorOutput(RootModel[Any]):
    root: Any = Field(description="가공하거나 감싸지 않고 그대로 전달하는 원본 JSON 값")


class JsonInspectorModule(ExecutableModule):
    definition = ModuleDefinition(
        type="json_inspector",
        label="JSON Data Inspector",
        category="Output",
        description=(
            "원본 JSON을 그대로 전달하고 캔버스에서는 상류 모듈에 맞는 "
            "테이블 또는 Markdown 뷰로 미리 봅니다."
        ),
        inputs=["input"],
        outputs=["output"],
        raw_input=True,
        raw_output=True,
        cacheable=False,
        version="2",
    )
    input_model = JsonInspectorInputDTO
    config_model = EmptyModuleConfigDTO
    execution_model = JsonInspectorInputDTO
    output_model = JsonInspectorOutput

    def execute(self, payload: BaseModel) -> Any:
        return cast(JsonInspectorInputDTO, payload).root
