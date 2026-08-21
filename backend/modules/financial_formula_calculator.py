"""Deterministic Financial Formula Calculator Module for Playground and Pipeline."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, cast

from pydantic import BaseModel, Field

from ..llm.chat_completion import (
    ChatCompletionClient,
    ChatCompletionError,
    ChatCompletionResult,
)
from .base import (
    ExecutableModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleExecutionError,
    ModuleInputDTO,
)
from .context_expander import ContextDTO
from .data_lineage import QueryContextDTO

logger = logging.getLogger(__name__)

CALCULATOR_SYSTEM_PROMPT = """당신은 재무제표 수치 계산 전문 분석가입니다.
제공된 스프레드시트 컨텍스트 블록에서 질문에 필요한 수치들을 정확히 추출하여, 요청된 재무 연산(비율, 증감률, 절대 차이, 배수, 마진 등)의 수식과 변수를 JSON으로 도출하십시오.

[출력 JSON 스키마]
{
  "is_calculation_required": true 또는 false,
  "operation": "ratio" | "yoy_change" | "difference" | "multiple" | "margin" | "sum",
  "expressions": [
    {
      "metric_name": "계산 항목명",
      "formula": "수학 표현식 (예: (A - B) / B * 100 또는 A / B)",
      "variables": {
        "A": {"label": "2025년 총주식보상비용", "value": 1715.0, "unit": "USD million"},
        "B": {"label": "2025년 장기투자자산", "value": 2112.0, "unit": "USD million"}
      },
      "unit": "%" | "USD million" | "배" | "달러",
      "description": "연산 설명"
    }
  ]
}
만약 단순 수치 조회나 정성적 질문이라 계산이 필요 없으면 "is_calculation_required": false로 반환하십시오.
반드시 JSON 포맷으로만 응답하십시오."""


class FinancialFormulaCalculatorInputDTO(ModuleInputDTO):
    context_json: ContextDTO = Field(
        description="Context Expander로부터 전달된 시계열 및 셀 컨텍스트 블록 DTO"
    )


class FinancialFormulaCalculatorConfigDTO(ModuleConfigDTO):
    model: str = Field(
        default="gpt-5.6-luna",
        description="수식 파싱 및 변수 추출에 사용할 LLM ID",
    )
    enabled: bool = Field(
        default=True,
        description="계산 모듈 활성화 여부",
    )


class FinancialFormulaCalculatorExecutionDTO(
    FinancialFormulaCalculatorInputDTO, FinancialFormulaCalculatorConfigDTO
):
    """Execution DTO for FinancialFormulaCalculatorModule."""


class CalculatedMetricDTO(BaseModel):
    metric_name: str
    formula: str
    variables: Dict[str, Any]
    computed_value: Optional[float] = None
    formatted_result: str
    unit: str


class FinancialFormulaCalculatorOutputDTO(BaseModel):
    is_calculation_required: bool
    calculated_metrics: List[CalculatedMetricDTO]
    summary_text: str


class FinancialFormulaCalculatorModule(ExecutableModule):
    definition = ModuleDefinition(
        type="financial_formula_calculator",
        label="Financial Formula Calculator",
        category="Logic",
        description="컨텍스트에서 재무 수치를 추출하고 Python 엔진으로 오차 없는 결정론적 연산(비율, 증감률 등)을 수행합니다.",
        inputs=["context_json"],
        outputs=["formula_result"],
        config_fields=["model", "enabled"],
        raw_output=True,
        version="1",
    )
    input_model = FinancialFormulaCalculatorInputDTO
    config_model = FinancialFormulaCalculatorConfigDTO
    execution_model = FinancialFormulaCalculatorExecutionDTO
    output_model = FinancialFormulaCalculatorOutputDTO

    def __init__(
        self, completion_client: Optional[ChatCompletionClient] = None
    ) -> None:
        self.completion_client = completion_client

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(FinancialFormulaCalculatorExecutionDTO, payload)
        q_context = input_data.context_json.query_context
        question = q_context.question_text if q_context else ""
        blocks = input_data.context_json.context_blocks

        if not input_data.enabled or not question or not blocks:
            return {
                "formula_result": {
                    "is_calculation_required": False,
                    "calculated_metrics": [],
                    "summary_text": "No calculation required.",
                }
            }

        # Check if question contains calculation keywords
        calc_keywords = ["비율", "차이", "증가율", "증감", "몇 배", "비중", "마진", "성장률", "어느 쪽이 더", "더 커", "더 작", "빼면", "나누", "합치면"]
        if not any(k in question for k in calc_keywords):
            return {
                "formula_result": {
                    "is_calculation_required": False,
                    "calculated_metrics": [],
                    "summary_text": "No calculation keywords detected.",
                }
            }

        client = self.completion_client or ChatCompletionClient()
        context_str = "\n".join(blocks[:50])

        user_content = f"질문: {question}\n\n[스프레드시트 컨텍스트]\n{context_str}"
        messages = [
            {"role": "system", "content": CALCULATOR_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        try:
            res: ChatCompletionResult = client.complete_with_metadata(
                model=input_data.model,
                messages=messages,
                response_format={"type": "json_object"},
            )
            parsed = json.loads(res.content)
        except Exception as e:
            logger.warning("Formula calculator 파싱 실패: %s", e)
            return {
                "formula_result": {
                    "is_calculation_required": false,
                    "calculated_metrics": [],
                    "summary_text": f"Parsing failed: {e}",
                }
            }

        if not parsed.get("is_calculation_required"):
            return {
                "formula_result": {
                    "is_calculation_required": false,
                    "calculated_metrics": [],
                    "summary_text": "LLM determined no calculation required.",
                }
            }

        calculated_metrics: List[Dict[str, Any]] = []
        summary_lines = ["[정밀 재무 계산 결과]"]

        for expr in parsed.get("expressions", []):
            formula = expr.get("formula", "")
            vars_dict = expr.get("variables", {})
            unit = expr.get("unit", "")
            metric_name = expr.get("metric_name", "계산 항목")

            # Extract variable numeric values
            num_vars = {}
                if isinstance(v_info, dict):
                    raw_val = v_info.get("value")
                    try:
                        num_vars[v_name] = float(raw_val) if raw_val is not None else 0.0
                    except (ValueError, TypeError):
                        num_vars[v_name] = 0.0
                elif isinstance(v_info, (int, float)):
                    num_vars[v_name] = float(v_info)
                elif isinstance(v_info, str):
                    try:
                        num_vars[v_name] = float(v_info.replace(",", "").strip())
                    except (ValueError, TypeError):
                        num_vars[v_name] = 0.0

            # Safely evaluate Python expression
            computed_val: Optional[float] = None
            formatted_res = ""
            try:
                # Safe evaluation with restricted math builtins
                import math
                safe_globals = {"math": math, "abs": abs, "round": round}
                computed_val = float(eval(formula, safe_globals, num_vars))
                if unit == "%":
                    formatted_res = f"{computed_val:.2f}%"
                elif "배" in unit:
                    formatted_res = f"{computed_val:.2f}배"
                else:
                    formatted_res = f"{computed_val:,.2f} {unit}".strip()
            except Exception as eval_err:
                formatted_res = f"계산 실패 ({eval_err})"

            calculated_metrics.append(
                {
                    "metric_name": metric_name,
                    "formula": formula,
                    "variables": vars_dict,
                    "computed_value": computed_val,
                    "formatted_result": formatted_res,
                    "unit": unit,
                }
            )
            summary_lines.append(
                f"- {metric_name}: {formatted_res} (산출식: {formula}, 변수: {num_vars})"
            )

        return {
            "formula_result": {
                "is_calculation_required": True,
                "calculated_metrics": calculated_metrics,
                "summary_text": "\n".join(summary_lines),
            }
        }
