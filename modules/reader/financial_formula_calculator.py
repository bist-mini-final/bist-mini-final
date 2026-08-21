"""Module for deterministic Python financial formula calculations."""

from __future__ import annotations

import ast
import json
import logging
import operator
from typing import Optional, Any, Dict, List, Optional, cast

from pydantic import BaseModel, Field

from backend.providers.llm.chat_completion import (
    ChatCompletionClient,
    ChatCompletionError,
    ChatCompletionResult,
)
from modules.common.base_module import (
    BaseModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleExecutionError,
    ModuleInputDTO,
)
from modules.retrieval.context_expander import ContextDTO

logger = logging.getLogger(__name__)

CALCULATOR_SYSTEM_PROMPT = """당신은 재무 제표 분석 및 정밀 재무 계산 전문가입니다.
주어진 재무 컨텍스트와 사용자의 질문을 분석하여, 질문에 답변하기 위해 수치 계산(비율, 증감률, 절대 차이, 비중, 배수 등)이 필요한지 판별하십시오.

계산이 필요한 경우:
1. 컨텍스트에서 필요한 수치 변수(variables)를 정확히 추출하십시오.
2. Python `eval`로 계산 가능한 수식(formula)을 작성하십시오. (예: `(A - B) / B * 100`, `A / B`, `A - B`, `(A + B) / C` 등)
3. 다음과 같은 JSON 포맷으로만 응답하십시오:
{
  "is_calculation_required": true,
  "expressions": [
    {
      "metric_name": "계산할 지표명 (예: 총주식보상비용 대비 장기투자자산 비율)",
      "formula": "B / A * 100",
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

_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


_ALLOWED_FUNCTIONS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
}


def _evaluate_ast_node(node: ast.AST, variables: Dict[str, float]) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError(f"지원되지 않는 상수 타입: {type(node.value)}")
    elif isinstance(node, ast.Name):
        if node.id in variables:
            return float(variables[node.id])
        raise ValueError(f"정의되지 않은 변수: {node.id}")
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in _ALLOWED_FUNCTIONS:
            func = _ALLOWED_FUNCTIONS[node.func.id]
            arg_vals = [_evaluate_ast_node(arg, variables) for arg in node.args]
            return float(func(*arg_vals))
        raise ValueError(f"허용되지 않는 함수 호출: {ast.dump(node)}")
    elif isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type in _ALLOWED_OPERATORS:
            return _ALLOWED_OPERATORS[op_type](_evaluate_ast_node(node.operand, variables))
        raise ValueError(f"지원되지 않는 단항 연산자: {op_type}")
    elif isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type in _ALLOWED_OPERATORS:
            left_val = _evaluate_ast_node(node.left, variables)
            right_val = _evaluate_ast_node(node.right, variables)
            return _ALLOWED_OPERATORS[op_type](left_val, right_val)
        raise ValueError(f"지원되지 않는 이항 연산자: {op_type}")
    elif isinstance(node, ast.Expression):
        return _evaluate_ast_node(node.body, variables)
    else:
        raise ValueError(f"허용되지 않는 AST 노드: {type(node)}")


def _evaluate_formula(formula: str, variables: Dict[str, float]) -> float:
    """Safely evaluates an arithmetic formula using AST whitelist."""
    parsed = ast.parse(formula.strip(), mode="eval")
    return _evaluate_ast_node(parsed, variables)


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
    calc_keywords: List[str] = Field(
        default_factory=lambda: [
            "비율", "비중", "증감률", "증감액", "성장률", "차이", "마진", "배수",
            "YoY", "QoQ", "CAGR", "합계", "총액", "평균", "대비", "몇 %", "몇 배",
            "percent", "ratio", "margin", "growth", "difference", "sum", "total", "average",
        ],
        description="계산 실행 트리거 키워드 목록",
    )
    max_context_blocks: int = Field(
        default=50,
        ge=1,
        le=500,
        description="수식 계산기에 전달할 최대 컨텍스트 블록 수",
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
    calculated_metrics: List[CalculatedMetricDTO] = Field(default_factory=list)
    summary_text: str = ""
    formula_result: Optional[Dict[str, Any]] = None


class FinancialFormulaCalculatorModule(BaseModule):
    definition = ModuleDefinition(
        type="financial_formula_calculator",
        label="Financial Formula Calculator",
        category="Logic",
        description="컨텍스트에서 재무 수치를 추출하고 Python 엔진으로 오차 없는 결정론적 연산(비율, 증감률 등)을 수행합니다.",
        inputs=["context_json"],
        outputs=["formula_result"],
        config_fields=["model", "enabled", "calc_keywords", "max_context_blocks"],
        raw_output=True,
        version="1",
    )
    input_model = FinancialFormulaCalculatorInputDTO
    config_model = FinancialFormulaCalculatorConfigDTO
    execution_model = FinancialFormulaCalculatorExecutionDTO
    output_model = FinancialFormulaCalculatorOutputDTO

    def __init__(self, completion_client: Optional[ChatCompletionClient] = None) -> None:
        self.completion_client = completion_client or ChatCompletionClient()

    def execute(
        self,
        input_data: FinancialFormulaCalculatorInputDTO,
        config: Optional[FinancialFormulaCalculatorConfigDTO] = None,
    ) -> Dict[str, Any]:
        if config is None and isinstance(input_data, FinancialFormulaCalculatorExecutionDTO):
            cfg = input_data
        else:
            cfg = config or FinancialFormulaCalculatorConfigDTO()
        if not cfg.enabled:
            result_dict: Dict[str, Any] = {
                "is_calculation_required": False,
                "calculated_metrics": [],
                "summary_text": "Formula calculator disabled.",
            }
            result_dict["formula_result"] = dict(result_dict)
            return result_dict

        q_text = input_data.context_json.query_context.question_text
        keywords = cfg.calc_keywords

        if not any(kw.lower() in q_text.lower() for kw in keywords):
            result_dict = {
                "is_calculation_required": False,
                "calculated_metrics": [],
                "summary_text": "No calculation keywords detected.",
            }
            result_dict["formula_result"] = dict(result_dict)
            return result_dict

        blocks = input_data.context_json.context_blocks
        limit = cfg.max_context_blocks
        context_preview = "\n\n".join(blocks[:limit])

        messages = [
            {"role": "system", "content": CALCULATOR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"질문: {q_text}\n\n[재무 컨텍스트]\n{context_preview}\n\n위 질문에 대해 계산이 필요한지 분석하고 수식 및 변수를 JSON으로 작성하십시오.",
            },
        ]

        client = self.completion_client
        try:
            comp_res: ChatCompletionResult = client.complete_with_metadata(
                model=cfg.model,
                messages=messages,
                response_format={"type": "json_object"},
            )
            parsed = json.loads(comp_res.content)
        except Exception as e:
            logger.warning("Formula calculator 파싱 실패: %s", e)
            result_dict = {
                "is_calculation_required": False,
                "calculated_metrics": [],
                "summary_text": f"Parsing failed: {e}",
            }
            result_dict["formula_result"] = dict(result_dict)
            return result_dict

        if not parsed.get("is_calculation_required"):
            result_dict = {
                "is_calculation_required": False,
                "calculated_metrics": [],
                "summary_text": "LLM determined no calculation required.",
            }
            result_dict["formula_result"] = dict(result_dict)
            return result_dict

        calculated_metrics: List[Dict[str, Any]] = []
        summary_lines = ["[정밀 재무 계산 결과]"]

        for expr in parsed.get("expressions", []):
            if not isinstance(expr, dict):
                continue
            formula = expr.get("formula", "")
            vars_dict = expr.get("variables", {})
            unit = expr.get("unit", "")
            metric_name = expr.get("metric_name", "계산 항목")

            # Safely extract variables and evaluate formula inside try-catch
            computed_val: Optional[float] = None
            formatted_res = ""
            try:
                if not isinstance(vars_dict, dict):
                    raise ValueError(f"변수 목록이 매핑(dict) 형태가 아닙니다: {type(vars_dict)}")

                num_vars: Dict[str, float] = {}
                for v_name, v_info in vars_dict.items():
                    if isinstance(v_info, dict):
                        raw_val = v_info.get("value")
                        if raw_val is None:
                            raise ValueError(f"변수 '{v_name}'의 value 필드가 누락되었습니다")
                        num_vars[v_name] = float(str(raw_val).replace(",", "").strip())
                    elif isinstance(v_info, (int, float)):
                        num_vars[v_name] = float(v_info)
                    elif isinstance(v_info, str):
                        num_vars[v_name] = float(v_info.replace(",", "").strip())
                    else:
                        raise ValueError(f"변수 '{v_name}'의 값이 비수치 데이터입니다: {v_info}")

                computed_val = _evaluate_formula(formula, num_vars)
                if unit == "%":
                    formatted_res = f"{computed_val:.2f}%"
                elif "배" in unit:
                    formatted_res = f"{computed_val:.2f}배"
                elif unit:
                    formatted_res = f"{computed_val:,.2f} {unit}"
                else:
                    formatted_res = f"{computed_val:,.2f}"
            except Exception as e:
                logger.warning("수식 계산 오류 '%s': %s", formula, e)
                computed_val = None
                formatted_res = f"계산 실패: {e}"

            vars_summary = (
                ", ".join(
                    f"{k}={v.get('value') if isinstance(v, dict) else v}"
                    for k, v in vars_dict.items()
                )
                if isinstance(vars_dict, dict)
                else str(vars_dict)
            )
            summary_lines.append(
                f"- {metric_name}: {formatted_res} (수식: `{formula}`, 변수: {vars_summary})"
            )

            calculated_metrics.append(
                {
                    "metric_name": metric_name,
                    "formula": formula,
                    "variables": vars_dict if isinstance(vars_dict, dict) else {},
                    "computed_value": computed_val,
                    "formatted_result": formatted_res,
                    "unit": unit,
                }
            )

        output_dict = {
            "is_calculation_required": True,
            "calculated_metrics": calculated_metrics,
            "summary_text": "\n".join(summary_lines),
        }
        output_dict["formula_result"] = dict(output_dict)
        return output_dict
