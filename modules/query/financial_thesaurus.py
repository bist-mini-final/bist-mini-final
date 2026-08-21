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
    {
        "standard_metric": "Total Common Equity",
        "korean_names": ["보통주자본총계", "보통주 자본 총계", "보통주 지분 총액", "자기자본 총계", "총 보통주자본"],
        "english_synonyms": ["Total Common Equity", "Total Stockholders' Equity", "Total Equity"],
        "sheet_hint": "Balance_Sheet",
        "caution": "개별 '보통주(Common Stock)' 행과 엄격히 구분하여 'Total Common Equity' 행을 참조할 것",
    },
    {
        "standard_metric": "Common Stock",
        "korean_names": ["보통주", "보통주자본", "발행 보통주", "보통주 자본금"],
        "english_synonyms": ["Common Stock", "Common Stock, Par Value", "Common Shares"],
        "sheet_hint": "Balance_Sheet",
        "caution": "'보통주자본총계(Total Common Equity)'와 구분하여 단일 'Common Stock' 행을 참조할 것",
    },
    {
        "standard_metric": "Gross Accounts Receivable / Accounts Receivable",
        "korean_names": ["매출채권", "외상매출금", "받을 어음 및 매출채권"],
        "english_synonyms": ["Accounts Receivable", "Gross Accounts Receivable", "Trade Receivables"],
        "sheet_hint": "Balance_Sheet",
        "caution": "Net Accounts Receivable 및 Allowance for Doubtful Accounts와 구분",
    },
    {
        "standard_metric": "Goodwill Net",
        "korean_names": ["영업권", "영업권 가치", "순영업권"],
        "english_synonyms": ["Goodwill", "Goodwill, Net", "Goodwill and Intangibles"],
        "sheet_hint": "Balance_Sheet",
        "caution": "NA로 표시된 Gross Goodwill 대신 실제 금액이 기재된 Goodwill / Goodwill, Net 행 참조",
    },
    {
        "standard_metric": "Deferred Tax Assets Long-Term",
        "korean_names": ["장기이연법인세자산", "장기 이연법인세자산", "이연법인세자산(비유동)"],
        "english_synonyms": ["Deferred Tax Assets Long-Term", "Non-Current Deferred Tax Assets", "Deferred Income Taxes"],
        "sheet_hint": "Balance_Sheet",
        "caution": "단기/유동 이연법인세자산과 엄격히 구분하여 Long-Term / Non-Current 항목 참조",
    },
    {
        "standard_metric": "Currency Exchange Gains (Loss)",
        "korean_names": ["환율 관련 손익", "외환손익", "외환차손익", "환율 변동 손익"],
        "english_synonyms": ["Currency Exchange Gains (Loss)", "Foreign Exchange Gain (Loss)", "FX Gain / Loss"],
        "sheet_hint": "Income_Statement",
        "caution": "단위는 백만 달러($ millions)이며 Income_Statement 영업외 손익 참조",
    },
    {
        "standard_metric": "Advertising Expense",
        "korean_names": ["광고비", "광고선전비", "광고 비용"],
        "english_synonyms": ["Advertising Expense", "Advertising & Marketing", "Advertising and Promotion"],
        "sheet_hint": "Income_Statement",
        "caution": "SG&A(판관비) 세부 항목, 단위는 백만 달러($ millions)",
    },
    {
        "standard_metric": "EBT Incl Unusual Items",
        "korean_names": ["특이항목 포함 세전이익", "세전이익", "세전손익", "법인세차감전순이익"],
        "english_synonyms": ["EBT Incl Unusual Items", "Earnings Before Taxes", "Income Before Income Taxes"],
        "sheet_hint": "Income_Statement",
        "caution": "EBT Excl Unusual Items(특이항목 제외 세전이익)와 구분",
    },
    {
        "standard_metric": "Total Assets",
        "korean_names": ["총자산", "자산총계", "자산 총계", "전체 자산"],
        "english_synonyms": ["Total Assets", "Assets Total", "Total Asset"],
        "sheet_hint": "Balance_Sheet",
    },
    {
        "standard_metric": "Total Liabilities",
        "korean_names": ["총부채", "부채총계", "부채 총계", "전체 부채"],
        "english_synonyms": ["Total Liabilities", "Liabilities Total"],
        "sheet_hint": "Balance_Sheet",
    },
    {
        "standard_metric": "Depreciation & Amortization",
        "korean_names": ["감가상각비", "감가상각", "상각비", "유무형자산상각비"],
        "english_synonyms": ["Depreciation & Amortization", "Depreciation and Amortization", "Depreciation", "Amortization"],
        "sheet_hint": "Cash_Flow",
    },
    {
        "standard_metric": "Capital Expenditures",
        "korean_names": ["자본적지출", "설비투자", "유형자산 취득", "Capex", "CAPEX"],
        "english_synonyms": ["Capital Expenditures", "Capital Expenditure", "Purchase of Property, Plant & Equipment", "CapEx"],
        "sheet_hint": "Cash_Flow",
    },
    {
        "standard_metric": "Total Stock-Based Compensation Expense",
        "korean_names": ["총주식보상비용", "주식보상비용", "주식기준보상"],
        "english_synonyms": ["Total Stock-Based Compensation Expense", "Stock-Based Compensation", "Share-Based Compensation"],
        "sheet_hint": "Income_Statement",
    },
    {
        "standard_metric": "Cash from Financing Activities",
        "korean_names": ["재무활동현금흐름", "재무활동 현금흐름", "재무현금흐름"],
        "english_synonyms": ["Cash from Financing Activities", "Financing Activities", "Cash Provided by (Used in) Financing Activities"],
        "sheet_hint": "Cash_Flow",
    },
    {
        "standard_metric": "Cash from Investing Activities",
        "korean_names": ["투자활동현금흐름", "투자활동 현금흐름", "투자현금흐름"],
        "english_synonyms": ["Cash from Investing Activities", "Investing Activities", "Cash Provided by (Used in) Investing Activities"],
        "sheet_hint": "Cash_Flow",
    },
    {
        "standard_metric": "Other Non-Current Assets",
        "korean_names": ["기타비유동자산", "기타 비유동자산", "기타 비유동 자산"],
        "english_synonyms": ["Other Non-Current Assets", "Other Assets", "Other Long-Term Assets"],
        "sheet_hint": "Balance_Sheet",
    },
    {
        "standard_metric": "Other Current Assets",
        "korean_names": ["기타유동자산", "기타 유동자산", "기타 유동 자산"],
        "english_synonyms": ["Other Current Assets"],
        "sheet_hint": "Balance_Sheet",
    },
    {
        "standard_metric": "Other Non-Current Liabilities",
        "korean_names": ["기타비유동부채", "기타 비유동부채", "기타 비유동 부채"],
        "english_synonyms": ["Other Non-Current Liabilities", "Other Long-Term Liabilities"],
        "sheet_hint": "Balance_Sheet",
    },
    {
        "standard_metric": "Current Portion of Long-Term Debt",
        "korean_names": ["유동성 장기부채", "유동성장기부채", "유동성 장기차입금"],
        "english_synonyms": ["Current Portion of Long-Term Debt", "Current Long-Term Debt", "Current Maturities of Long-Term Debt"],
        "sheet_hint": "Balance_Sheet",
    },
    {
        "standard_metric": "Cost of Revenue",
        "korean_names": ["매출원가", "매출 원가", "원가"],
        "english_synonyms": ["Cost of Revenue", "Cost of Goods Sold", "Cost of Sales", "COGS"],
        "sheet_hint": "Income_Statement",
    },
    {
        "standard_metric": "Full-Time Employees",
        "korean_names": ["정규직 직원 수", "직원 수", "임직원 수", "종업원 수", "인원 수"],
        "english_synonyms": ["Full-Time Employees", "Employees", "Number of Employees"],
        "sheet_hint": "Balance_Sheet",
    },
    {
        "standard_metric": "Market Capitalization",
        "korean_names": ["시가총액", "시총", "기업가치"],
        "english_synonyms": ["Market Capitalization", "Market Cap", "Total Market Value"],
        "sheet_hint": "Key_Stats",
    },
    {
        "standard_metric": "Common Stock Issued",
        "korean_names": ["보통주 발행액", "보통주 발행", "주식 발행액"],
        "english_synonyms": ["Common Stock Issued", "Issuance of Common Stock", "Common Shares Issued"],
        "sheet_hint": "Cash_Flow",
    },
    {
        "standard_metric": "Cash Income Taxes Paid",
        "korean_names": ["현금 법인세지급액", "법인세지급액", "납부한 법인세"],
        "english_synonyms": ["Cash Income Taxes Paid", "Income Taxes Paid", "Taxes Paid"],
        "sheet_hint": "Cash_Flow",
    },
    {
        "standard_metric": "Gain (Loss) on Sale of Assets",
        "korean_names": ["자산 처분손익", "자산처분손익", "자산 매각손익"],
        "english_synonyms": ["Gain (Loss) on Sale of Assets", "Sale of Assets", "Disposal of Assets"],
        "sheet_hint": "Income_Statement",
    },
    {
        "standard_metric": "Income from Discontinued Operations",
        "korean_names": ["중단영업이익", "중단사업손익", "중단영업손익"],
        "english_synonyms": ["Income from Discontinued Operations", "Discontinued Operations", "Gain (Loss) from Discontinued Operations"],
        "sheet_hint": "Income_Statement",
    },
    {
        "standard_metric": "Weighted Average Diluted Shares",
        "korean_names": ["가중평균 희석주식수", "희석주식수", "가중평균 주식수"],
        "english_synonyms": ["Weighted Average Diluted Shares", "Diluted Weighted Average Shares", "Diluted Shares"],
        "sheet_hint": "Income_Statement",
    },
    {
        "standard_metric": "Dividends Per Share",
        "korean_names": ["주당배당금", "주당 배당금", "DPS", "배당금"],
        "english_synonyms": ["Dividends Per Share", "DPS", "Common Dividends Per Share"],
        "sheet_hint": "Key_Stats",
    },
    {
        "standard_metric": "Net Property, Plant & Equipment",
        "korean_names": ["순유형자산", "유형자산 순액", "순 유형자산"],
        "english_synonyms": ["Net Property, Plant & Equipment", "Net PP&E", "Property, Plant & Equipment - Net"],
        "sheet_hint": "Balance_Sheet",
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

    # Check for whole-company phrases across all 4 companies
    if any(k in query for k in ["모든 회사", "전체 회사", "4개 회사", "네 회사", "전사", "각 회사", "각 사"]):
        return ["IBM", "Bistelligence", "Coldplay", "DH Innovation"]

    # Match specific company aliases
    for alias, canonical in COMPANY_ALIASES_MAP.items():
        if alias in query_lower and canonical not in found:
            found.append(canonical)

    if found:
        return found

    if default is not None:
        return default

    return ["IBM"]


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
