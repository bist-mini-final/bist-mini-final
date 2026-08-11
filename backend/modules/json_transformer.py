from typing import Any, Dict, cast

from pydantic import BaseModel, Field

from .base import ExecutableModule, ModuleDefinition, ModuleDTO


class JsonTransformerInput(ModuleDTO):
    any_json: Dict[str, Any] = Field(
        description="변환할 임의 JSON 객체; 최상위 키만 이름 변경"
    )
    mappings: Dict[str, str] = Field(
        default_factory=dict,
        description="source_field: target_field 형식의 필드명 매핑 규칙",
    )


class JsonTransformerOutput(ModuleDTO):
    transformed_json: Dict[str, Any] = Field(
        description="매핑 규칙이 적용된 JSON 객체 출력 포트"
    )


class JsonTransformerModule(ExecutableModule):
    definition = ModuleDefinition(
        type="json_transformer",
        label="JSON Format Mapper",
        category="Transform",
        description="입력 JSON의 필드명을 매핑 규칙에 따라 변환합니다.",
        inputs=["any_json"],
        outputs=["transformed_json"],
        config_fields=["mappings"],
    )
    input_model = JsonTransformerInput
    output_model = JsonTransformerOutput

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(JsonTransformerInput, payload)
        transformed = dict(input_data.any_json)
        for source_key, target_key in input_data.mappings.items():
            if source_key in transformed:
                transformed[target_key] = transformed.pop(source_key)
        return {"transformed_json": transformed}
