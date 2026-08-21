"""Financial terminology thesaurus and line-item synonym mapping dictionary.

Source: Notion Financial Evaluation Set v2.0 & US-GAAP / IFRS Spreadsheet Metadata.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


# Notion v2.0 Standard Metric Mapping Rules & Financial Line Items
FINANCIAL_THESAURUS: List[Dict[str, Any]] = [
    {
        "standard_metric": "Total Revenue",
        "korean_names": ["매출", "매출액", "매출 규모", "전체 매출", "외형"],
        "english_synonyms": ["Total Revenue", "Revenue", "Sales", "Total Sales"],
        "sheet_hint": "Income_Statement",
        "caution": "Gross Profit(매출총이익)이나 Operating Income과 혼동 금지",
    },
    {
        "standard_metric": "Operating Income / EBIT",
        "korean_names": ["영업이익", "본업 이익", "본업으로 남긴 이익", "EBIT"],
        "english_synonyms": ["Operating Income", "EBIT", "Operating Profit"],
        "sheet_hint": "Income_Statement",
        "caution": "EBITDA 및 순이익(Net Income)과 구분",
    },
    {
        "standard_metric": "Net Income to Company",
        "korean_names": ["당기순이익", "순이익", "최종 이익", "최종 손익", "순손실"],
        "english_synonyms": ["Net Income to Company", "Net Income", "Net Profit", "Net Loss"],
        "sheet_hint": "Income_Statement",
        "caution": "Earnings from Continuing Operations와 구분",
    },
    {
        "standard_metric": "Total Cash & ST Investments",
        "korean_names": ["현금", "현금성 자산", "현금 및 단기투자자산", "현금·단기투자자산", "단기 자산"],
        "english_synonyms": ["Cash & Short-Term Investments", "Cash & Cash Equivalents", "Total Cash & ST Investments", "Marketable Securities"],
        "sheet_hint": "Balance_Sheet",
        "caution": "현금흐름표의 Net Change in Cash와 구분, 1년 내 현금화 자산은 Total Current Assets와 구분",
    },
    {
        "standard_metric": "Cash from Operations",
        "korean_names": ["영업활동현금흐름", "영업현금", "영업으로 번 현금", "본업 현금창출", "CFO"],
        "english_synonyms": ["Cash from Operations", "Cash Provided by Operating Activities", "Operating Cash Flow", "CFO"],
        "sheet_hint": "Cash_Flow",
        "caution": "EBITDA와 대체 불가, Net Change in Cash와 구분",
    },
    {
        "standard_metric": "Levered Free Cash Flow",
        "korean_names": ["잉여현금흐름", "FCF", "설비투자 후 남은 현금", "프리캐시플로우"],
        "english_synonyms": ["Levered Free Cash Flow", "Free Cash Flow", "FCF", "CFO - Capital Expenditures"],
        "sheet_hint": "Cash_Flow",
        "caution": "Unlevered FCF와 구분",
    },
    {
        "standard_metric": "Total Debt",
        "korean_names": ["차입금", "총차입금", "총차입부채", "차입금 전체", "빚"],
        "english_synonyms": ["Total Debt", "Short-Term Debt + Long-Term Debt", "Total Borrowings"],
        "sheet_hint": "Balance_Sheet",
        "caution": "Total Liabilities(총부채)와 엄격히 구분",
    },
    {
        "standard_metric": "Net Debt",
        "korean_names": ["순차입금", "순부채", "실제 빚 부담"],
        "english_synonyms": ["Net Debt", "Total Debt - Total Cash"],
        "sheet_hint": "Balance_Sheet",
        "caution": "음수(-) Net Debt는 순차입금이 아니라 순현금(Net Cash) 상태를 의미",
    },
    {
        "standard_metric": "Total Current Assets",
        "korean_names": ["유동자산", "1년 안에 현금화할 수 있는 자산", "단기자산 총계"],
        "english_synonyms": ["Total Current Assets", "Current Assets"],
        "sheet_hint": "Balance_Sheet",
        "caution": "단순 현금(Cash)과 유동자산 총계 구분",
    },
    {
        "standard_metric": "Total Current Liabilities",
        "korean_names": ["유동부채", "1년 내 상환해야 하는 부채", "단기 부채"],
        "english_synonyms": ["Total Current Liabilities", "Current Liabilities"],
        "sheet_hint": "Balance_Sheet",
        "caution": "비유동부채 및 총부채와 구분",
    },
    {
        "standard_metric": "Total Common Equity",
        "korean_names": ["보통주자본총계", "보통주 자본", "총자본", "주주지분"],
        "english_synonyms": ["Total Common Equity", "Common Stockholders' Equity", "Total Shareholders' Equity", "Total Equity"],
        "sheet_hint": "Balance_Sheet",
        "caution": "Common Stock(보통주 자본금)과 엄격히 구분. 자본총계는 Total Common Equity임",
    },
    {
        "standard_metric": "Accumulated Depreciation",
        "korean_names": ["감가상각누계액", "감가상각누계"],
        "english_synonyms": ["Accumulated Depreciation", "Accumulated Depreciation & Amortization"],
        "sheet_hint": "Balance_Sheet",
        "caution": "차감계정이므로 음수(-) 부호 유지 필요",
    },
    {
        "standard_metric": "Gross Property, Plant & Equipment",
        "korean_names": ["유형자산 취득원가", "총유형자산", "유형자산 원가"],
        "english_synonyms": ["Gross Property, Plant & Equipment", "Gross PP&E", "Property, Plant & Equipment - Gross"],
        "sheet_hint": "Balance_Sheet",
        "caution": "Net PP&E(순유형자산)과 구분",
    },
    {
        "standard_metric": "Accounts Receivable",
        "korean_names": ["매출채권", "외상매출금", "받을 돈"],
        "english_synonyms": ["Accounts Receivable", "Receivables - Trade", "Trade Accounts Receivable"],
        "sheet_hint": "Balance_Sheet",
        "caution": "매출채권 변동(Change in Accounts Receivable)은 Cash Flow 표 항목임",
    },
    {
        "standard_metric": "Accounts Payable",
        "korean_names": ["매입채무", "외상매입금", "줄 돈"],
        "english_synonyms": ["Accounts Payable", "Payables - Trade", "Trade Accounts Payable"],
        "sheet_hint": "Balance_Sheet",
        "caution": "매입채무 변동(Change in Accounts Payable)은 Cash Flow 표 항목임",
    },
    {
        "standard_metric": "Accrued Expenses",
        "korean_names": ["미지급비용", "미지급 비용"],
        "english_synonyms": ["Accrued Expenses", "Accrued Expenses and Other Current Liabilities", "Accrued Liabilities"],
        "sheet_hint": "Balance_Sheet",
        "caution": "미지급세금 및 기타유동부채와 구분",
    },
    {
        "standard_metric": "Long-Term Investments",
        "korean_names": ["장기투자자산", "장기 투자 자산"],
        "english_synonyms": ["Long-Term Investments", "Other Long-Term Assets", "Investments in Affiliates"],
        "sheet_hint": "Balance_Sheet",
        "caution": "단기투자자산(Short-Term Investments)과 구분",
    },
    {
        "standard_metric": "Pension & Postretirement Liabilities",
        "korean_names": ["연금·퇴직급여부채", "연금 및 퇴직급여부채", "퇴직급여부채"],
        "english_synonyms": ["Pension & Postretirement Benefits", "Pension and other postretirement benefit obligations"],
        "sheet_hint": "Balance_Sheet",
        "caution": "비유동부채 세부 항목",
    },
    {
        "standard_metric": "Non-Current Deferred Revenue",
        "korean_names": ["비유동 선수수익", "장기 선수수익"],
        "english_synonyms": ["Deferred Revenue - Non-Current", "Non-Current Deferred Income"],
        "sheet_hint": "Balance_Sheet",
        "caution": "유동 선수수익(Current Deferred Revenue)과 구분",
    },
    {
        "standard_metric": "Key Stats Estimates",
        "korean_names": ["전망", "예상", "내년", "앞으로", "추정치", "2026년 예상", "2027년 예상"],
        "english_synonyms": ["2026E", "2027E", "2028E", "Key Stats Forecast", "Estimates"],
        "sheet_hint": "Key_Stats",
        "caution": "실적 열(Actual 2023~2025)과 혼용 금지, Key_Stats 시트의 전망 컬럼 사용",
    },
]


# Canonical company alias mapping table
COMPANY_ALIASES_MAP: Dict[str, str] = {
    "ibm": "IBM",
    "아이비엠": "IBM",
    "i.b.m": "IBM",
    "bistelligence": "Bistelligence",
    "비스텔리전스": "Bistelligence",
    "비스텔": "Bistelligence",
    "bist": "Bistelligence",
    "coldplay": "Coldplay",
    "콜드플레이": "Coldplay",
    "콜플": "Coldplay",
    "dh innovation": "DH Innovation",
    "dh": "DH Innovation",
    "디에이치": "DH Innovation",
    "디에이치이노베이션": "DH Innovation",
    "디에이치 이노베이션": "DH Innovation",
}


def resolve_company_names(query: str, default: Optional[List[str]] = None) -> List[str]:
    """Extract and canonicalize company names mentioned in the user query."""
    query_lower = query.lower()
    found: List[str] = []
    
    # Check for "세 회사", "모든 회사", "전체 회사"
    if any(k in query for k in ["세 회사", "3개 회사", "모든 회사", "전체 회사", "어느 회사가", "각 사"]):
        return ["IBM", "Bistelligence", "Coldplay", "DH Innovation"]

    for alias, canonical in COMPANY_ALIASES_MAP.items():
        if alias in query_lower and canonical not in found:
            found.append(canonical)

    if not found and default:
        return default
    return found or (default or ["IBM"])


def get_relevant_thesaurus_entries(query: str) -> List[Dict[str, Any]]:
    """Retrieve relevant financial thesaurus entries matching the query."""
    query_lower = query.lower()
    matched = []
    for entry in FINANCIAL_THESAURUS:
        for k_name in entry["korean_names"]:
            if k_name.lower() in query_lower:
                matched.append(entry)
                break
        else:
            for e_syn in entry["english_synonyms"]:
                if e_syn.lower() in query_lower:
                    matched.append(entry)
                    break
    return matched


def format_thesaurus_prompt_guide(query: str) -> str:
    """Format matching financial line items as prompt guidance for Decomposer."""
    entries = get_relevant_thesaurus_entries(query)
    if not entries:
        return ""

    lines = ["\n[표준 재무 지표 및 시트 매핑 가이드]"]
    for e in entries:
        k_str = ", ".join(e["korean_names"][:3])
        e_str = ", ".join(e["english_synonyms"][:3])
        lines.append(f"- 사용자 표현: {k_str}")
        lines.append(f"  * 표준 지표명(Row Header): {e['standard_metric']} ({e_str})")
        lines.append(f"  * 대상 시트(Sheet Name): {e.get('sheet_hint', 'Any')}")
        if "caution" in e:
            lines.append(f"  * 주의 사항: {e['caution']}")
    return "\n".join(lines)
