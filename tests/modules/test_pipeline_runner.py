from __future__ import annotations

import unittest
from typing import Any, Dict, Optional
from pydantic import Field

from backend.engine.runner import NodeExecutionRecord, PipelineExecutionResult, PipelineRunner
from modules.common.base_module import (
    BaseModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleInputDTO,
)


class StepOneInputDTO(ModuleInputDTO):
    raw_query: str = Field(description="Raw query text")


class StepOneOutputDTO(ModuleDTO):
    processed_query: str = Field(description="Processed query text")


class StepOneModule(BaseModule):
    definition = ModuleDefinition(
        type="step_one",
        label="Step One",
        category="query",
        description="Processes raw query",
        inputs=["raw_query"],
        outputs=["processed_query"],
    )
    input_model = StepOneInputDTO
    config_model = ModuleConfigDTO
    output_model = StepOneOutputDTO

    def execute(self, input_data: StepOneInputDTO, config: Optional[ModuleConfigDTO] = None) -> Dict[str, Any]:
        return {"processed_query": f"PROCESSED: {input_data.raw_query}"}


class StepTwoInputDTO(ModuleInputDTO):
    processed_query: str = Field(description="Input from step one")


class StepTwoOutputDTO(ModuleDTO):
    final_answer: str = Field(description="Final answer")
    cost_usd: Optional[float] = Field(default=None, description="API cost in USD")
    usage: Optional[Dict[str, int]] = Field(default=None, description="Token usage")


class StepTwoModule(BaseModule):
    definition = ModuleDefinition(
        type="step_two",
        label="Step Two",
        category="reader",
        description="Generates final answer",
        inputs=["processed_query"],
        outputs=["final_answer"],
    )
    input_model = StepTwoInputDTO
    config_model = ModuleConfigDTO
    output_model = StepTwoOutputDTO

    def execute(self, input_data: StepTwoInputDTO, config: Optional[ModuleConfigDTO] = None) -> Dict[str, Any]:
        return {
            "final_answer": f"ANSWER FOR [{input_data.processed_query}]",
            "cost_usd": 0.0015,
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        }


class PipelineRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = PipelineRunner()
        self.step1 = StepOneModule()
        self.step2 = StepTwoModule()

    def test_run_sequence_success(self) -> None:
        result = self.runner.run_sequence(
            modules=[self.step1, self.step2],
            initial_input={"raw_query": "삼성전자 2024년 영업이익"},
        )
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(len(result.records), 2)
        self.assertEqual(
            result.final_output.get("final_answer"),
            "ANSWER FOR [PROCESSED: 삼성전자 2024년 영업이익]",
        )
        self.assertEqual(result.total_cost_usd, 0.0015)
        self.assertEqual(result.total_tokens, 30)
        self.assertGreater(result.total_elapsed_ms, 0.0)

    def test_run_sequence_validation_error_stops_gracefully(self) -> None:
        result = self.runner.run_sequence(
            modules=[self.step1, self.step2],
            initial_input={},  # Missing required raw_query field
        )
        self.assertEqual(result.status, "failed")
        self.assertIn("raw_query", str(result.error))
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].status, "failed")
