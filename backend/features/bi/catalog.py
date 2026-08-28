from dataclasses import dataclass
from enum import StrEnum, unique
from types import MappingProxyType
from typing import Final, Mapping

from .models import MetricId, ValueKind

CATALOG_VERSION: Final = "2"
FORMULA_VERSION: Final = "3"
SOURCE_QUESTION_TEMPLATE: Final = (
    "Find the exact reported value of '{metric_label}' for {period_label} in this financial document. "
    "Match equivalent metric names ({metric_aliases}), period labels, and date-formatted column headers across the entire workbook; prioritize relevant statements such as {statement_hint}, but do not require an exact sheet name. "
    "Return the numerical value, currency, scale, and supporting cell_id from the same metric row and requested period. Do not calculate, forecast, or substitute a neighboring period."
)


@unique
class MetricDisplayRole(StrEnum):
    PRIMARY = "primary"
    AUXILIARY = "auxiliary"


@unique
class SignPolicy(StrEnum):
    AS_REPORTED = "as_reported"
    OUTFLOW_NEGATIVE = "outflow_negative"
    PERCENT_POINT = "percent_point"


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    metric_id: MetricId
    label_ko: str
    label_en: str
    description_ko: str
    value_kind: ValueKind
    display_role: MetricDisplayRole


@dataclass(frozen=True, slots=True)
class SourceMetricDefinition(MetricDefinition):
    aliases_ko: tuple[str, ...]
    aliases_en: tuple[str, ...]
    statement_hints: tuple[str, ...]
    row_header_hints: tuple[str, ...]
    excluded_aliases: tuple[str, ...]
    sign_policy: SignPolicy
    question_template: str


@dataclass(frozen=True, slots=True)
class DerivedMetricDefinition(MetricDefinition):
    formula_id: str
    dependencies: tuple[MetricId, ...]


@dataclass(frozen=True, slots=True)
class FallbackMetricDefinition(SourceMetricDefinition):
    fallback_formula_id: str
    dependencies: tuple[MetricId, ...]


_PRIMARY: Final = MetricDisplayRole.PRIMARY
_AUXILIARY: Final = MetricDisplayRole.AUXILIARY
_SOURCE: Final = SOURCE_QUESTION_TEMPLATE


METRIC_CATALOG: Final[Mapping[MetricId, MetricDefinition]] = MappingProxyType(
    {
        MetricId.REVENUE: SourceMetricDefinition(
            MetricId.REVENUE, "매출", "Total Revenue", "기업이 상품과 서비스 판매로 얻은 수익", ValueKind.AMOUNT, _PRIMARY,
            ("매출", "매출액", "영업수익"), ("Total Revenue", "Revenue", "Sales", "IQ_TOTAL_REV", "IQ_REV"),
            ("Income_Statement", "Key_Stats"), ("Total Revenue", "Revenue", "Sales"),
            ("Other Revenue",), SignPolicy.AS_REPORTED, _SOURCE,
        ),
        MetricId.REVENUE_YOY_GROWTH: DerivedMetricDefinition(
            MetricId.REVENUE_YOY_GROWTH, "매출 성장률", "Revenue YoY Growth", "직전 FY 대비 매출 증감률", ValueKind.PERCENT,
            _PRIMARY, "revenue_yoy_growth", (MetricId.REVENUE,),
        ),
        MetricId.OPERATING_INCOME: SourceMetricDefinition(
            MetricId.OPERATING_INCOME, "영업이익", "Operating Income", "본업에서 발생한 이익", ValueKind.AMOUNT, _PRIMARY,
            ("영업이익",), ("Operating Income", "Operating Profit", "EBIT", "IQ_OPER_INC", "IQ_EBIT"),
            ("Income_Statement", "Key_Stats"), ("Operating Income", "Operating Profit", "EBIT"),
            ("Adjusted EBIT",), SignPolicy.AS_REPORTED, _SOURCE,
        ),
        MetricId.OPERATING_MARGIN: DerivedMetricDefinition(
            MetricId.OPERATING_MARGIN, "영업이익률", "Operating Margin", "매출 대비 영업이익 비율", ValueKind.PERCENT,
            _PRIMARY, "operating_margin", (MetricId.OPERATING_INCOME, MetricId.REVENUE),
        ),
        MetricId.NET_INCOME: SourceMetricDefinition(
            MetricId.NET_INCOME, "순이익", "Net Income", "모든 비용과 세금을 반영한 이익", ValueKind.AMOUNT, _PRIMARY,
            ("순이익", "당기순이익"), ("Net Income", "Net Earnings", "IQ_NI", "IQ_NI_CF", "IQ_NET_INC"),
            ("Cash_Flow", "Income_Statement", "Key_Stats"), ("Net Income", "Net Earnings"),
            ("Net Income Attributable to NCI",), SignPolicy.AS_REPORTED, _SOURCE,
        ),
        MetricId.NET_MARGIN: DerivedMetricDefinition(
            MetricId.NET_MARGIN, "순이익률", "Net Margin", "매출 대비 순이익 비율", ValueKind.PERCENT,
            _PRIMARY, "net_margin", (MetricId.NET_INCOME, MetricId.REVENUE),
        ),
        MetricId.OPERATING_CASH_FLOW: SourceMetricDefinition(
            MetricId.OPERATING_CASH_FLOW, "영업현금흐름", "Cash from Ops.", "영업활동에서 창출된 현금", ValueKind.AMOUNT, _PRIMARY,
            ("영업현금흐름", "영업활동현금흐름"), ("Cash from Ops.", "Cash from Operations", "Operating Cash Flow", "CFO", "IQ_CASH_OPER"),
            ("Cash_Flow",), ("Cash from Ops.", "Cash from Operations", "Operating Cash Flow"),
            (), SignPolicy.AS_REPORTED, _SOURCE,
        ),
        MetricId.CAPITAL_EXPENDITURE: SourceMetricDefinition(
            MetricId.CAPITAL_EXPENDITURE, "CapEx", "Capital Expenditure", "유형 및 무형자산 취득을 위한 지출", ValueKind.AMOUNT, _PRIMARY,
            ("자본적지출", "설비투자"), ("Capital Expenditure", "Capital Expenditures", "CapEx", "IQ_CAPEX"),
            ("Cash_Flow", "Key_Stats"), ("Capital Expenditure", "CapEx"),
            ("Capital Expenditure Proceeds",), SignPolicy.OUTFLOW_NEGATIVE, _SOURCE,
        ),
        MetricId.FREE_CASH_FLOW: DerivedMetricDefinition(
            MetricId.FREE_CASH_FLOW, "FCF", "Free Cash Flow", "영업현금흐름에서 자본적지출을 반영한 현금", ValueKind.AMOUNT,
            _PRIMARY, "free_cash_flow", (MetricId.OPERATING_CASH_FLOW, MetricId.CAPITAL_EXPENDITURE),
        ),
        MetricId.FREE_CASH_FLOW_MARGIN: DerivedMetricDefinition(
            MetricId.FREE_CASH_FLOW_MARGIN, "FCF 마진", "Free Cash Flow Margin", "매출 대비 잉여현금흐름 비율", ValueKind.PERCENT,
            _PRIMARY, "free_cash_flow_margin", (MetricId.FREE_CASH_FLOW, MetricId.REVENUE),
        ),
        MetricId.CASH_AND_SHORT_TERM_INVESTMENTS: SourceMetricDefinition(
            MetricId.CASH_AND_SHORT_TERM_INVESTMENTS, "현금 및 단기투자자산", "Total Cash & ST Investments", "즉시 활용 가능한 현금성 자산", ValueKind.AMOUNT,
            _PRIMARY, ("현금 및 단기투자자산", "현금성자산"),
            ("Total Cash & ST Investments", "Cash and Short-Term Investments", "Cash And Equivalents", "Short Term Investments", "IQ_CASH_ST_INVEST", "IQ_CASH_EQUIV"),
            ("Balance_Sheet",), ("Total Cash & ST Investments", "Cash and Short-Term Investments", "Cash And Equivalents"),
            ("Restricted Cash",), SignPolicy.AS_REPORTED, _SOURCE,
        ),
        MetricId.SHORT_TERM_DEBT: SourceMetricDefinition(
            MetricId.SHORT_TERM_DEBT, "단기차입금", "Short-term Borrowings", "1년 이내 상환할 차입금", ValueKind.AMOUNT, _AUXILIARY,
            ("단기차입금",), ("Short-term Borrowings", "Short-Term Debt", "IQ_ST_DEBT"),
            ("Balance_Sheet", "Capital_Structure_Summary"), ("Short-term Borrowings", "Short-Term Debt"),
            ("Current Portion of Long-Term Debt",), SignPolicy.AS_REPORTED, _SOURCE,
        ),
        MetricId.CURRENT_PORTION_OF_LONG_TERM_DEBT: SourceMetricDefinition(
            MetricId.CURRENT_PORTION_OF_LONG_TERM_DEBT, "유동성 장기부채", "Current Portion of Long Term Debt", "1년 이내 만기가 도래하는 장기차입금", ValueKind.AMOUNT,
            _AUXILIARY, ("유동성 장기부채",), ("Current Portion of Long Term Debt", "Current Portion of Long-Term Debt", "IQ_CURRENT_PORT_DEBT"),
            ("Balance_Sheet",), ("Current Portion of Long Term Debt", "Current Portion of Long-Term Debt"),
            ("Short-Term Debt",), SignPolicy.AS_REPORTED, _SOURCE,
        ),
        MetricId.LONG_TERM_DEBT: SourceMetricDefinition(
            MetricId.LONG_TERM_DEBT, "장기차입금", "Long-Term Debt", "1년 이후 상환할 차입금", ValueKind.AMOUNT, _AUXILIARY,
            ("장기차입금",), ("Long-Term Debt", "Total Long Term Debt", "Long-Term Borrowings", "IQ_LT_DEBT"),
            ("Balance_Sheet",), ("Long-Term Debt", "Total Long Term Debt", "Long-Term Borrowings"),
            ("Current Portion of Long-Term Debt",), SignPolicy.AS_REPORTED, _SOURCE,
        ),
        MetricId.TOTAL_DEBT: FallbackMetricDefinition(
            MetricId.TOTAL_DEBT, "총차입금", "Total Debt", "이자 비용이 발생하는 전체 차입금", ValueKind.AMOUNT, _PRIMARY,
            ("총차입금", "총부채성차입금"), ("Total Debt", "Total Debt Issued", "Gross Debt", "IQ_TOTAL_DEBT"),
            ("Balance_Sheet", "Key_Stats"), ("Total Debt", "Total Debt Issued", "Gross Debt"),
            ("Total Liabilities",), SignPolicy.AS_REPORTED, _SOURCE, "total_debt_components",
            (MetricId.SHORT_TERM_DEBT, MetricId.CURRENT_PORTION_OF_LONG_TERM_DEBT, MetricId.LONG_TERM_DEBT),
        ),
        MetricId.NET_DEBT: DerivedMetricDefinition(
            MetricId.NET_DEBT, "순차입금", "Net Debt", "총차입금에서 현금성 자산을 차감한 금액", ValueKind.AMOUNT,
            _PRIMARY, "net_debt", (MetricId.TOTAL_DEBT, MetricId.CASH_AND_SHORT_TERM_INVESTMENTS),
        ),
        MetricId.TOTAL_ASSETS: SourceMetricDefinition(
            MetricId.TOTAL_ASSETS, "총자산", "Total Assets", "기업이 보유한 전체 자산", ValueKind.AMOUNT, _PRIMARY,
            ("총자산",), ("Total Assets", "Assets", "IQ_TOTAL_ASSETS"), ("Balance_Sheet",), ("Total Assets", "Assets"),
            ("Average Total Assets",), SignPolicy.AS_REPORTED, _SOURCE,
        ),
        MetricId.TOTAL_LIABILITIES: SourceMetricDefinition(
            MetricId.TOTAL_LIABILITIES, "총부채", "Total Liabilities", "기업이 부담하는 전체 부채", ValueKind.AMOUNT, _PRIMARY,
            ("총부채",), ("Total Liabilities", "Liabilities", "IQ_TOTAL_LIAB"), ("Balance_Sheet",), ("Total Liabilities", "Liabilities"),
            ("Total Debt",), SignPolicy.AS_REPORTED, _SOURCE,
        ),
        MetricId.TOTAL_EQUITY: SourceMetricDefinition(
            MetricId.TOTAL_EQUITY, "총자본", "Total Equity", "자산에서 부채를 제외한 주주 지분", ValueKind.AMOUNT, _PRIMARY,
            ("총자본", "자본총계"), ("Total Equity", "Total Common Equity", "Shareholders' Equity", "Stockholders' Equity", "IQ_TOTAL_EQUITY", "IQ_TOTAL_COMMON_EQUITY"),
            ("Balance_Sheet", "Key_Stats"), ("Total Equity", "Total Common Equity", "Shareholders' Equity"),
            ("Average Total Equity",), SignPolicy.AS_REPORTED, _SOURCE,
        ),
        MetricId.DEBT_RATIO: DerivedMetricDefinition(
            MetricId.DEBT_RATIO, "부채비율", "Debt Ratio", "총자산 대비 총부채 비율", ValueKind.PERCENT,
            _PRIMARY, "debt_ratio", (MetricId.TOTAL_LIABILITIES, MetricId.TOTAL_ASSETS),
        ),
        MetricId.NET_DEBT_RATIO: DerivedMetricDefinition(
            MetricId.NET_DEBT_RATIO, "순차입금비율", "Net Debt Ratio", "총자산 대비 순차입금 비율", ValueKind.PERCENT,
            _PRIMARY, "net_debt_ratio", (MetricId.NET_DEBT, MetricId.TOTAL_ASSETS),
        ),
    }
)
