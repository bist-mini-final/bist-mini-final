from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Final, Mapping, cast

FORMULA_PATH: Final = Path(__file__).with_name("formulas.json")
SUPPORTED_SCHEMA_VERSION: Final = 1


class FormulaDefinitionError(ValueError):
    """Raised when the versioned formula catalog is invalid or unsafe."""


class FormulaEvaluationError(ValueError):
    """Raised when a valid formula cannot be evaluated for the supplied inputs."""


@dataclass(frozen=True, slots=True)
class FormulaDefinition:
    formula_id: str
    expression: str
    variables: tuple[str, ...]
    parsed_expression: ast.Expression


def _validate_node(node: ast.AST, variables: frozenset[str]) -> None:
    match node:
        case ast.Expression(body=body):
            _validate_node(body, variables)
        case ast.BinOp(left=left, op=operator, right=right):
            if not isinstance(operator, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
                raise FormulaDefinitionError("only +, -, *, and / are allowed")
            _validate_node(left, variables)
            _validate_node(right, variables)
        case ast.UnaryOp(op=operator, operand=operand):
            if not isinstance(operator, (ast.UAdd, ast.USub)):
                raise FormulaDefinitionError("only unary + and - are allowed")
            _validate_node(operand, variables)
        case ast.Name(id=name):
            if name not in variables:
                raise FormulaDefinitionError(f"undeclared formula variable: {name}")
        case ast.Constant(value=value):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise FormulaDefinitionError("formula constants must be numeric")
        case _:
            raise FormulaDefinitionError(
                f"unsupported formula syntax: {type(node).__name__}"
            )


def parse_formula(
    formula_id: str,
    expression: str,
    variables: tuple[str, ...],
) -> FormulaDefinition:
    if not formula_id or not formula_id.replace("_", "").isalnum():
        raise FormulaDefinitionError(f"invalid formula_id: {formula_id!r}")
    if not variables or len(set(variables)) != len(variables):
        raise FormulaDefinitionError(f"invalid variables for formula {formula_id}")
    if any(not variable.isidentifier() for variable in variables):
        raise FormulaDefinitionError(f"invalid variable name for formula {formula_id}")
    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise FormulaDefinitionError(f"invalid formula syntax: {formula_id}") from exc
    _validate_node(parsed, frozenset(variables))
    referenced = {
        node.id for node in ast.walk(parsed) if isinstance(node, ast.Name)
    }
    if referenced != set(variables):
        raise FormulaDefinitionError(
            f"declared variables do not match expression for formula {formula_id}"
        )
    return FormulaDefinition(formula_id, expression, variables, parsed)


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise FormulaDefinitionError(f"{field} must be a string")
    return value


@lru_cache(maxsize=1)
def load_formula_catalog() -> Mapping[str, FormulaDefinition]:
    try:
        payload = json.loads(FORMULA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FormulaDefinitionError("formula catalog could not be loaded") from exc
    if not isinstance(payload, dict):
        raise FormulaDefinitionError("formula catalog root must be an object")
    if payload.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise FormulaDefinitionError("unsupported formula catalog schema_version")
    raw_formulas = payload.get("formulas")
    if not isinstance(raw_formulas, list):
        raise FormulaDefinitionError("formula catalog formulas must be an array")

    formulas: dict[str, FormulaDefinition] = {}
    for raw_formula in raw_formulas:
        if not isinstance(raw_formula, dict):
            raise FormulaDefinitionError("each formula must be an object")
        formula_id = _require_string(raw_formula.get("formula_id"), "formula_id")
        expression = _require_string(raw_formula.get("expression"), "expression")
        raw_variables = raw_formula.get("variables")
        if not isinstance(raw_variables, list) or not all(
            isinstance(variable, str) for variable in raw_variables
        ):
            raise FormulaDefinitionError("formula variables must be a string array")
        if formula_id in formulas:
            raise FormulaDefinitionError(f"duplicate formula_id: {formula_id}")
        variables = cast(tuple[str, ...], tuple(raw_variables))
        formulas[formula_id] = parse_formula(formula_id, expression, variables)
    return formulas


def _evaluate_node(node: ast.AST, values: Mapping[str, Decimal]) -> Decimal:
    match node:
        case ast.Expression(body=body):
            return _evaluate_node(body, values)
        case ast.Name(id=name):
            try:
                return values[name]
            except KeyError as exc:
                raise FormulaEvaluationError(f"missing formula input: {name}") from exc
        case ast.Constant(value=value) if isinstance(value, (int, float)):
            return Decimal(str(value))
        case ast.UnaryOp(op=ast.UAdd(), operand=operand):
            return _evaluate_node(operand, values)
        case ast.UnaryOp(op=ast.USub(), operand=operand):
            return -_evaluate_node(operand, values)
        case ast.BinOp(left=left, op=operator, right=right):
            left_value = _evaluate_node(left, values)
            right_value = _evaluate_node(right, values)
            match operator:
                case ast.Add():
                    return left_value + right_value
                case ast.Sub():
                    return left_value - right_value
                case ast.Mult():
                    return left_value * right_value
                case ast.Div():
                    try:
                        return left_value / right_value
                    except ZeroDivisionError as exc:
                        raise FormulaEvaluationError("zero_denominator") from exc
                case _:
                    raise FormulaEvaluationError("unsupported binary operator")
        case _:
            raise FormulaEvaluationError("unsupported expression node")


def evaluate_formula(
    formula_id: str,
    values: Mapping[str, Decimal],
) -> Decimal:
    try:
        formula = load_formula_catalog()[formula_id]
    except KeyError as exc:
        raise FormulaEvaluationError(f"unknown formula_id: {formula_id}") from exc
    if set(values) != set(formula.variables):
        raise FormulaEvaluationError(f"formula inputs do not match: {formula_id}")
    return _evaluate_node(formula.parsed_expression, values)


__all__ = [
    "FormulaDefinition",
    "FormulaDefinitionError",
    "FormulaEvaluationError",
    "evaluate_formula",
    "load_formula_catalog",
    "parse_formula",
]

