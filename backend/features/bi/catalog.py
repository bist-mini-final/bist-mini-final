from dataclasses import dataclass
from enum import StrEnum, unique
from types import MappingProxyType
from typing import Final, Mapping

from .models import MetricId, ValueKind


CATALOG_VERSION: Final = "1"
FORMULA_VERSION: Final = "1"
SOURCE_QUESTION_TEMPLATE: Final = (
    "이 문서에서 {period_label}의 {metric_label} 값을 찾아라. "
    "계산하지 말고 원문 값, 통화, 배율, 근거 cell_id를 구조화해 반환하라."
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
            MetricId.REVENUE, "매출", "기업이 상품과 서비스 판매로 얻은 수익", ValueKind.AMOUNT, _PRIMARY,
            ("매출", "매출액", "영업수익"), ("Revenue", "Total Revenue", "Sales"),
            ("Income Statement", "Key Statistics"), ("Revenue", "Sales"),
            ("Other Revenue",), SignPolicy.AS_REPORTED, _SOURCE,
        ),
        MetricId.REVENUE_YOY_GROWTH: DerivedMetricDefinition(
            MetricId.REVENUE_YOY_GROWTH, "매출 성장률", "직전 FY 대비 매출 증감률", ValueKind.PERCENT,
            _PRIMARY, "revenue_yoy_growth", (MetricId.REVENUE,),
        ),
        MetricId.OPERATING_INCOME: SourceMetricDefinition(
            MetricId.OPERATING_INCOME, "영업이익", "본업에서 발생한 이익", ValueKind.AMOUNT, _PRIMARY,
            ("영업이익",), ("Operating Income", "Operating Profit", "EBIT"),
            ("Income Statement",), ("Operating Income", "Operating Profit", "EBIT"),
            ("Adjusted EBIT",), SignPolicy.AS_REPORTED, _SOURCE,
        ),
        MetricId.OPERATING_MARGIN: DerivedMetricDefinition(
            MetricId.OPERATING_MARGIN, "영업이익률", "매출 대비 영업이익 비율", ValueKind.PERCENT,
            _PRIMARY, "operating_margin", (MetricId.OPERATING_INCOME, MetricId.REVENUE),
        ),
        MetricId.NET_INCOME: SourceMetricDefinition(
            MetricId.NET_INCOME, "순이익", "모든 비용과 세금을 반영한 이익", ValueKind.AMOUNT, _PRIMARY,
            ("순이익", "당기순이익"), ("Net Income", "Net Earnings"),
            ("Income Statement",), ("Net Income", "Net Earnings"),
            ("Net Income Attributable to NCI",), SignPolicy.AS_REPORTED, _SOURCE,
        ),
        MetricId.NET_MARGIN: DerivedMetricDefinition(
            MetricId.NET_MARGIN, "순이익률", "매출 대비 순이익 비율", ValueKind.PERCENT,
            _PRIMARY, "net_margin", (MetricId.NET_INCOME, MetricId.REVENUE),
        ),
        MetricId.OPERATING_CASH_FLOW: SourceMetricDefinition(
            MetricId.OPERATING_CASH_FLOW, "영업현금흐름", "영업활동에서 창출된 현금", ValueKind.AMOUNT, _PRIMARY,
            ("영업현금흐름", "영업활동현금흐름"), ("Operating Cash Flow", "Cash from Operations", "CFO"),
            ("Cash Flow Statement",), ("Operating Cash Flow", "Cash from Operations"),
            (), SignPolicy.AS_REPORTED, _SOURCE,
        ),
        MetricId.CAPITAL_EXPENDITURE: SourceMetricDefinition(
            MetricId.CAPITAL_EXPENDITURE, "CapEx", "유형 및 무형자산 취득을 위한 지출", ValueKind.AMOUNT, _PRIMARY,
            ("자본적지출", "설비투자"), ("Capital Expenditure", "Capital Expenditures", "CapEx"),
            ("Cash Flow Statement", "Key Statistics"), ("Capital Expenditure", "CapEx"),
            ("Capital Expenditure Proceeds",), SignPolicy.OUTFLOW_NEGATIVE, _SOURCE,
        ),
        MetricId.FREE_CASH_FLOW: DerivedMetricDefinition(
            MetricId.FREE_CASH_FLOW, "FCF", "영업현금흐름에서 자본적지출을 반영한 현금", ValueKind.AMOUNT,
            _PRIMARY, "free_cash_flow", (MetricId.OPERATING_CASH_FLOW, MetricId.CAPITAL_EXPENDITURE),
        ),
        MetricId.CASH_AND_SHORT_TERM_INVESTMENTS: SourceMetricDefinition(
            MetricId.CASH_AND_SHORT_TERM_INVESTMENTS, "현금 및 단기투자자산", "즉시 활용 가능한 현금성 자산", ValueKind.AMOUNT,
            _PRIMARY, ("현금 및 단기투자자산", "현금성자산"),
            ("Cash and Short-Term Investments", "Cash and Cash Equivalents"),
            ("Balance Sheet",), ("Cash and Short-Term Investments", "Cash and Cash Equivalents"),
            ("Restricted Cash",), SignPolicy.AS_REPORTED, _SOURCE,
        ),
        MetricId.SHORT_TERM_DEBT: SourceMetricDefinition(
            MetricId.SHORT_TERM_DEBT, "단기차입금", "1년 이내 상환할 차입금", ValueKind.AMOUNT, _AUXILIARY,
            ("단기차입금",), ("Short-Term Debt", "Short-Term Borrowings"),
            ("Balance Sheet",), ("Short-Term Debt", "Short-Term Borrowings"),
            ("Current Portion of Long-Term Debt",), SignPolicy.AS_REPORTED, _SOURCE,
        ),
        MetricId.CURRENT_PORTION_OF_LONG_TERM_DEBT: SourceMetricDefinition(
            MetricId.CURRENT_PORTION_OF_LONG_TERM_DEBT, "유동성 장기부채", "1년 이내 만기가 도래하는 장기차입금", ValueKind.AMOUNT,
            _AUXILIARY, ("유동성 장기부채",), ("Current Portion of Long-Term Debt", "Current Maturities"),
            ("Balance Sheet",), ("Current Portion of Long-Term Debt", "Current Maturities"),
            ("Short-Term Debt",), SignPolicy.AS_REPORTED, _SOURCE,
        ),
        MetricId.LONG_TERM_DEBT: SourceMetricDefinition(
            MetricId.LONG_TERM_DEBT, "장기차입금", "1년 이후 상환할 차입금", ValueKind.AMOUNT, _AUXILIARY,
            ("장기차입금",), ("Long-Term Debt", "Long-Term Borrowings"),
            ("Balance Sheet",), ("Long-Term Debt", "Long-Term Borrowings"),
            ("Current Portion of Long-Term Debt",), SignPolicy.AS_REPORTED, _SOURCE,
        ),
        MetricId.TOTAL_DEBT: FallbackMetricDefinition(
            MetricId.TOTAL_DEBT, "총차입금", "이자 비용이 발생하는 전체 차입금", ValueKind.AMOUNT, _PRIMARY,
            ("총차입금", "총부채성차입금"), ("Total Debt", "Gross Debt"),
            ("Balance Sheet", "Key Statistics"), ("Total Debt", "Gross Debt"),
            ("Total Liabilities",), SignPolicy.AS_REPORTED, _SOURCE, "total_debt_components",
            (MetricId.SHORT_TERM_DEBT, MetricId.CURRENT_PORTION_OF_LONG_TERM_DEBT, MetricId.LONG_TERM_DEBT),
        ),
        MetricId.NET_DEBT: DerivedMetricDefinition(
            MetricId.NET_DEBT, "순차입금", "총차입금에서 현금성 자산을 차감한 금액", ValueKind.AMOUNT,
            _PRIMARY, "net_debt", (MetricId.TOTAL_DEBT, MetricId.CASH_AND_SHORT_TERM_INVESTMENTS),
        ),
        MetricId.TOTAL_ASSETS: SourceMetricDefinition(
            MetricId.TOTAL_ASSETS, "총자산", "기업이 보유한 전체 자산", ValueKind.AMOUNT, _PRIMARY,
            ("총자산",), ("Total Assets",), ("Balance Sheet",), ("Total Assets",),
            ("Average Total Assets",), SignPolicy.AS_REPORTED, _SOURCE,
        ),
        MetricId.TOTAL_LIABILITIES: SourceMetricDefinition(
            MetricId.TOTAL_LIABILITIES, "총부채", "기업이 부담하는 전체 부채", ValueKind.AMOUNT, _PRIMARY,
            ("총부채",), ("Total Liabilities",), ("Balance Sheet",), ("Total Liabilities",),
            ("Total Debt",), SignPolicy.AS_REPORTED, _SOURCE,
        ),
        MetricId.TOTAL_EQUITY: SourceMetricDefinition(
            MetricId.TOTAL_EQUITY, "총자본", "자산에서 부채를 제외한 주주 지분", ValueKind.AMOUNT, _PRIMARY,
            ("총자본", "자본총계"), ("Total Equity", "Shareholders' Equity", "Stockholders' Equity"),
            ("Balance Sheet",), ("Total Equity", "Shareholders' Equity"),
            ("Average Total Equity",), SignPolicy.AS_REPORTED, _SOURCE,
        ),
    }
)
