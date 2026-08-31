from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import Field

from backend.platform.openai.responses import OpenAIResponseResult
from modules.common.base_llm import BaseLLMModule, calculate_openai_cost
from modules.common.base_module import (
    BaseModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleInputDTO,
)


class DummyInputDTO(ModuleInputDTO):
    text: str = Field(description="Sample input")


class DummyConfigDTO(ModuleConfigDTO):
    temperature: float = Field(default=0.7)


class DummyOutputDTO(ModuleDTO):
    result: str = Field(description="Sample output")


class DummyModule(BaseModule):
    definition = ModuleDefinition(
        type="dummy_module",
        label="Dummy Module",
        category="Test",
        description="Test module",
        inputs=["input"],
        outputs=["output"],
        config_fields=["temperature"],
    )
    input_model = DummyInputDTO
    config_model = DummyConfigDTO
    output_model = DummyOutputDTO

    def execute(self, input_data: DummyInputDTO, config: DummyConfigDTO | None = None):
        cfg = config or DummyConfigDTO()
        return {"result": f"{input_data.text}:{cfg.temperature}"}


class DummyLLMModule(BaseLLMModule):
    definition = ModuleDefinition(
        type="dummy_llm_module",
        label="Dummy LLM Module",
        category="Test",
        description="Test LLM module",
        inputs=["input"],
        outputs=["output"],
        config_fields=[],
    )
    input_model = DummyInputDTO
    config_model = DummyConfigDTO
    output_model = DummyOutputDTO

    def execute(self, input_data: DummyInputDTO, config: DummyConfigDTO | None = None):
        parsed, _, _, _ = self.complete_structured(
            messages_or_prompt=input_data.text,
            response_model=DummyOutputDTO,
            model="gpt-5.6-luna",
        )
        return parsed.model_dump()


def test_base_module_auto_execution_dto():
    module = DummyModule()
    # Test execution with dict input
    res = module.run({"text": "hello", "temperature": 0.2})
    assert res == {"result": "hello:0.2"}

    # Test execution with DTO instance
    res2 = module.run(DummyInputDTO(text="world"))
    assert res2 == {"result": "world:0.7"}


def test_base_llm_module_complete_structured():
    mock_client = MagicMock()
    mock_client.create_response.return_value = OpenAIResponseResult(
        response_id="resp_test",
        content='{"result": "mocked_answer"}',
        usage={"prompt_tokens": 10, "completion_tokens": 20},
        latency_seconds=0.15,
    )

    llm_module = DummyLLMModule(completion_client=mock_client)
    res = llm_module.run({"text": "query"})
    assert res == {"result": "mocked_answer"}
    response_format = mock_client.create_response.call_args.kwargs["text_format"]
    schema = response_format["schema"]
    assert response_format["type"] == "json_schema"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["result"]


def test_base_module_native_async_execution_keeps_validation_contract() -> None:
    class NativeAsyncModule(DummyModule):
        def execute(self, input_data, config=None):
            raise AssertionError("sync execute must not be called")

        async def execute_async(self, input_data, config=None):
            cfg = config or DummyConfigDTO()
            await asyncio.sleep(0)
            return {"result": f"{input_data.text}:{cfg.temperature}"}

    result = asyncio.run(NativeAsyncModule().run_async({"text": "async", "temperature": 0.3}))
    assert result == {"result": "async:0.3"}


def test_base_llm_module_complete_structured_async() -> None:
    mock_client = MagicMock()
    mock_client.create_response_async = AsyncMock(
        return_value=OpenAIResponseResult(
            response_id="resp_async",
            content='{"result": "async_answer"}',
            usage={"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
            latency_seconds=0.05,
        )
    )
    llm_module = DummyLLMModule(completion_client=mock_client)

    parsed, usage, _, latency = asyncio.run(
        llm_module.complete_structured_async(
            "query",
            DummyOutputDTO,
            "gpt-5.6-luna",
        )
    )

    assert parsed.result == "async_answer"
    assert usage.total_tokens == 6
    assert latency == 0.05
    mock_client.create_response_async.assert_awaited_once()


def test_base_module_rejects_unknown_fields_and_reports_progress():
    from modules.common.exceptions import ModuleExecutionError

    module = DummyModule()
    progress = MagicMock()
    module.set_progress_callback(progress)
    module.report_progress({"completed": 1})
    progress.assert_called_once_with({"completed": 1})

    with pytest.raises(ModuleExecutionError, match="알 수 없는 입력 필드"):
        module.run({"text": "hello", "temperatur": 0.2})


def test_calculate_openai_cost():
    cost_mini = calculate_openai_cost("gpt-5.6-luna", 1000, 1000)
    assert cost_mini > 0

    cost_embed = calculate_openai_cost("text-embedding-3-large", 1000, 0)
    assert cost_embed > 0


def test_pipeline_exception_hierarchy():
    from modules.common.exceptions import (
        DocumentParsingError,
        ModuleExecutionError,
        ModuleValidationError,
        PipelineBaseError,
        ProviderApiError,
        StorageError,
    )

    val_err = ModuleValidationError(
        "Input is missing", module_type="dummy", details={"field": "text"}
    )
    assert isinstance(val_err, ModuleExecutionError)
    assert isinstance(val_err, PipelineBaseError)
    assert val_err.status_code == 422
    assert val_err.error_code == "MODULE_VALIDATION_ERROR"
    assert val_err.to_dict()["module_type"] == "dummy"

    prov_err = ProviderApiError("OpenAI timeout", module_type="llm", provider="openai")
    assert isinstance(prov_err, ModuleExecutionError)
    assert prov_err.status_code == 502
    assert prov_err.error_code == "PROVIDER_API_ERROR"

    storage_err = StorageError("DB failed", module_type="storage")
    assert isinstance(storage_err, PipelineBaseError)
    assert storage_err.status_code == 500

    doc_err = DocumentParsingError("Sheet not found", module_type="excel")
    assert isinstance(doc_err, PipelineBaseError)
    assert doc_err.status_code == 422


def test_base_module_validation_error_wrapping():
    from modules.common.exceptions import ModuleValidationError

    module = DummyModule()
    # Missing required field "text"
    with pytest.raises(ModuleValidationError) as exc_info:
        module.run({})
    assert exc_info.value.module_type == "dummy_module"
    assert exc_info.value.status_code == 422
    assert "errors" in exc_info.value.details


def test_base_module_output_schema_mismatch_wrapping():
    from modules.common.exceptions import ModuleExecutionError

    class BadOutputModule(BaseModule):
        definition = ModuleDefinition(
            type="bad_output",
            label="Bad Output",
            category="Test",
            description="Test bad output",
            inputs=["input"],
            outputs=["output"],
            config_fields=[],
        )
        input_model = DummyInputDTO
        config_model = DummyConfigDTO
        output_model = DummyOutputDTO

        def execute(self, input_data: DummyInputDTO, config: DummyConfigDTO | None = None):
            return {"wrong_field": 123}

    bad_module = BadOutputModule()
    with pytest.raises(ModuleExecutionError) as exc_info:
        bad_module.run({"text": "test"})
    assert exc_info.value.module_type == "bad_output"
    assert "출력 스키마 불일치" in str(exc_info.value)


def test_base_module_provider_api_error_wrapping():
    from modules.common.exceptions import ProviderApiError

    class ApiFailingModule(BaseModule):
        definition = ModuleDefinition(
            type="api_failing",
            label="API Failing",
            category="Test",
            description="Test API fail",
            inputs=["input"],
            outputs=["output"],
            config_fields=[],
        )
        input_model = DummyInputDTO
        config_model = DummyConfigDTO
        output_model = DummyOutputDTO

        def execute(self, input_data: DummyInputDTO, config: DummyConfigDTO | None = None):
            raise RuntimeError("OpenAI API rate limit exceeded")

    module = ApiFailingModule()
    with pytest.raises(ProviderApiError) as exc_info:
        module.run({"text": "test"})
    assert exc_info.value.module_type == "api_failing"
    assert exc_info.value.status_code == 502
