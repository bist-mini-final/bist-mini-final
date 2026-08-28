from decimal import Decimal

import pytest

from backend.features.bi.formula_dsl import (
    FormulaDefinitionError,
    FormulaEvaluationError,
    evaluate_formula,
    load_formula_catalog,
    parse_formula,
)


def test_versioned_formula_catalog_is_loaded_and_evaluated() -> None:
    catalog = load_formula_catalog()

    assert set(catalog) == {
        "operating_margin",
        "net_margin",
        "free_cash_flow",
        "free_cash_flow_margin",
        "debt_ratio",
        "net_debt_ratio",
        "net_debt",
    }
    assert evaluate_formula(
        "operating_margin",
        {"operating_income": Decimal("25"), "revenue": Decimal("100")},
    ) == Decimal("25.00")


@pytest.mark.parametrize(
    "expression",
    (
        "__import__('os').system('whoami')",
        "value.__class__",
        "value[0]",
        "abs(value)",
        "unknown + value",
        "value ** 2",
    ),
)
def test_formula_parser_rejects_unsafe_or_undeclared_syntax(expression: str) -> None:
    with pytest.raises(FormulaDefinitionError):
        parse_formula("unsafe", expression, ("value",))


def test_formula_evaluator_rejects_input_contract_mismatch() -> None:
    with pytest.raises(FormulaEvaluationError, match="inputs do not match"):
        evaluate_formula("net_debt", {"total_debt": Decimal("10")})


def test_formula_evaluator_reports_zero_denominator() -> None:
    with pytest.raises(FormulaEvaluationError, match="zero_denominator"):
        evaluate_formula(
            "debt_ratio",
            {"total_liabilities": Decimal("10"), "total_assets": Decimal("0")},
        )
