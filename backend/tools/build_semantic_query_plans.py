"""Build the LLM-free semantic decomposition catalog from the 86-case gold set."""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
GOLDSET = ROOT.parent / "rag-semantic-query-matching" / "api" / "rag_common" / "goldset.py"
OUT = ROOT / "data" / "semantic_query_plans.json"
LEGACY = ROOT.parent.parent / "data" / "semantic_query_examples.json"
SHEET = {"KS": "Key_Stats", "IS": "Income_Statement", "BS": "Balance_Sheet", "CF": "Cash_Flow", "RAT": "Ratios", "CAP": "Capitalization", "DO": "Detailed_Ownership", "SUM": "Summary"}
METRICS = (
    ("희석 EPS", "Diluted EPS"), ("DPS", "Dividends per Share"), ("주당배당", "Dividends per Share"),
    ("현금 및 단기", "Cash and Short-Term Investments"), ("총자산", "Total Assets"),
    ("총부채", "Total Liabilities"), ("장기부채", "Long-Term Debt"), ("단기부채", "Total Debt Current"),
    ("영업현금흐름", "Cash from Ops."), ("CAPEX", "Capital Expenditure"), ("자본지출", "Capital Expenditure"),
    ("매출총이익", "Gross Profit"), ("매출", "Total Revenue"), ("EBITDA", "EBITDA"),
    ("영업이익", "Operating Income"), ("순이익", "Net Income"), ("시가총액", "Market Capitalization"),
    ("TEV", "Total Enterprise Value"), ("유동비율", "Current Ratio"), ("ROE", "Return on Equity"),
    ("ROA", "Return on Assets"), ("종가", "Close Price"), ("발행주식", "Shares Outstanding"),
)

def period(question: str) -> str:
    if "LTM" in question: return "LTM"
    year = re.search(r"20(2[1-8])", question)
    if year:
        return f"FY{year.group(0)}"
    if "최근 3년" in question: return "FY2023"
    if "최근 4년" in question: return "FY2022"
    if "최근 5년" in question or "2021년부터" in question: return "FY2021"
    return "FY2025"

def plan(case) -> list[str]:
    found = [english for korean, english in METRICS if korean.lower() in case.question.lower()]
    if not found: found = ["?"]
    years = [period(case.question)]
    if "추이" in case.question or "CAGR" in case.question or "YoY" in case.question:
        start = int(years[0][-4:]) if years[0].startswith("FY") else 2021
        years = [f"FY{year}" for year in range(start, 2026)]
    return [f"Sheet: ? | Row Header: {metric} | Column Header: {year} | Cell Value: ?" for metric in dict.fromkeys(found) for year in years]

def plan_id_for_variant(question: str) -> int | None:
    """Attach legacy SQM wording variants to a gold-set decomposition plan."""
    rules = (
        (("eps", "dps", "주당배당", "희석"), 4),
        (("현금", "단기투자"), 5), (("총자산", "총부채"), 6),
        (("영업현금", "capex"), 7), (("배당금",), 8),
        (("부채비율", "debt/equity"), 11), (("최대주주", "holder"), 13),
        (("ceo",), 15), (("tev", "시가총액"), 1), (("시가총액",), 19),
        (("tev",), 20), (("ebitda",), 22), (("순이익",), 23),
        (("장기부채",), 25), (("영업현금",), 26), (("capex", "자본지출"), 27),
        (("매출", "revenue"), 21),
    )
    lowered = question.casefold()
    for terms, case_id in rules:
        # Multi-metric plans require every named metric; a single-metric
        # synonym (for example "EPS" or "매출") is enough for its plan.
        matched = all(term.casefold() in lowered for term in terms) if case_id in {1, 5, 6, 7} else any(term.casefold() in lowered for term in terms)
        if matched:
            return case_id
    return None

def main() -> None:
    spec = importlib.util.spec_from_file_location("goldset", GOLDSET)
    module = importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(module)
    cases = {case.case_id: case for case in module.GOLD_CASES}
    rows = [{"id": f"gold-{case.case_id}", "question": case.question, "target": "get_ibm_key_financials",
             "metadata": {"query_type": case.query_type, "sheets": [SHEET[s] for s in case.sheets]},
             "decomposition": {"subqueries": plan(case)}} for case in module.GOLD_CASES]
    # Preserve SQM's existing paraphrase bank. IBM variants that can be mapped
    # deterministically inherit the gold-set plan; other-company examples stay
    # route-only and retain their legacy metadata.
    for raw in json.loads(LEGACY.read_text(encoding="utf-8")):
        case_id = plan_id_for_variant(str(raw.get("question", "")))
        if raw.get("target") == "get_ibm_key_financials" and case_id in cases:
            case = cases[case_id]
            rows.append({"id": f"variant-{raw['id']}", "question": raw["question"], "target": raw["target"],
                         "metadata": {"query_type": case.query_type, "sheets": [SHEET[s] for s in case.sheets], "plan_id": case_id},
                         "decomposition": {"subqueries": plan(case)}})
        else:
            rows.append(raw)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__": main()
