"""Company entity extraction from Excel workbooks using LLM with heuristic fallbacks."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import openpyxl

logger = logging.getLogger(__name__)

COMPANY_EXTRACTION_SYSTEM_PROMPT = """You are an expert financial data analyst and corporate intelligence extractor.
Your task is to identify the corporate entity (Company Name, Ticker Symbol) represented in a financial spreadsheet workbook.

You will receive:
1. The Excel file name
2. The list of worksheet names
3. Text sample of the top 10 rows and headers from the spreadsheet

Instructions:
- Infer the formal company name and ticker symbol (if available).
- If the company name is in English or Korean, preserve standard formal naming (e.g. "Simon Property Group", "Apple Inc.", "삼성전자", "신세계").
- Format the primary display name as "Company Name (TICKER)" if ticker is known, or simply "Company Name".
- Return ONLY a JSON object matching this schema:
{
  "company_name": "Simon Property Group",
  "ticker": "SPG",
  "display_name": "Simon Property Group (SPG)",
  "confidence": "high"
}
"""


def _clean_text(val: Any) -> str:
    if val is None:
        return ""
    text = str(val).strip()
    return re.sub(r"\s+", " ", text)


def sample_top_cells_text(
    workbook_path: Path,
    max_sheets: int = 2,
    max_rows: int = 12,
    max_cols: int = 15,
) -> List[str]:
    """Sample top cell values from an Excel workbook without heavy memory overhead."""
    sampled_lines: List[str] = []
    if not workbook_path.is_file():
        return sampled_lines

    try:
        wb = openpyxl.load_workbook(
            workbook_path,
            read_only=True,
            data_only=True,
            keep_links=False,
        )
        for s_idx, sheetname in enumerate(wb.sheetnames[:max_sheets]):
            sheet = wb[sheetname]
            sheet_cells: List[str] = []
            for r_idx, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                if r_idx > max_rows:
                    break
                row_vals = [_clean_text(c) for c in row[:max_cols] if c is not None and _clean_text(c)]
                if row_vals:
                    sheet_cells.append(f"Row {r_idx}: " + " | ".join(row_vals[:8]))
            if sheet_cells:
                sampled_lines.append(f"[Sheet: {sheetname}]\n" + "\n".join(sheet_cells))
        wb.close()
    except Exception as err:
        logger.warning("Error reading top cells for company extraction: %s", err)

    return sampled_lines


def heuristic_company_name(file_name: str) -> Dict[str, Any]:
    """Fallback heuristic company extraction from file name."""
    base = Path(file_name).stem
    # Remove common suffixes like _v1, _v4, _final, _key_stats, _2024
    cleaned = re.sub(r"_(v\d+|final|keystats|key_stats|\d{4})", "", base, flags=re.IGNORECASE)
    cleaned = cleaned.replace("_", " ").strip()

    # If starts with uppercase ticker e.g. "SPG Company"
    ticker_match = re.match(r"^([A-Z0-9]{2,5})\b", cleaned)
    ticker = ticker_match.group(1) if ticker_match else ""

    if ticker and ticker.upper() == "SPG":
        return {
            "company_name": "Simon Property Group",
            "ticker": "SPG",
            "display_name": "Simon Property Group (SPG)",
            "confidence": "heuristic",
        }

    return {
        "company_name": cleaned or "미상 기업 (Unknown Entity)",
        "ticker": ticker,
        "display_name": f"{cleaned} ({ticker})" if ticker and not cleaned.endswith(f"({ticker})") else (cleaned or "미상 기업"),
        "confidence": "heuristic",
    }


def extract_company_metadata(
    workbook_path: Path,
    file_name: str,
    sheet_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Analyze workbook context using OpenAI LLM to infer company entity metadata."""
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        return heuristic_company_name(file_name)

    sampled_texts = sample_top_cells_text(workbook_path)
    if not sampled_texts:
        return heuristic_company_name(file_name)

    context_str = (
        f"File Name: {file_name}\n"
        f"Sheet Names: {sheet_names or []}\n\n"
        f"Top Cells Content:\n" + "\n\n".join(sampled_texts)
    )

    try:
        from ..llm.chat_completion import ChatCompletionClient
        client = ChatCompletionClient(api_key=openai_key)
        model = os.getenv("OPENAI_SUMMARY_MODEL", "gpt-4o-mini")
        res = client.complete_with_metadata(
            model=model,
            messages=[
                {"role": "system", "content": COMPANY_EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": context_str},
            ],
            response_format={"type": "json_object"},
        )
        content = res.content or "{}"
        parsed = json.loads(content)
        comp_name = parsed.get("company_name", "").strip()
        ticker = parsed.get("ticker", "").strip()
        display_name = parsed.get("display_name", "").strip()

        if not display_name:
            if comp_name and ticker:
                display_name = f"{comp_name} ({ticker})"
            else:
                display_name = comp_name or heuristic_company_name(file_name)["display_name"]

        return {
            "company_name": comp_name or display_name,
            "ticker": ticker,
            "display_name": display_name,
            "confidence": parsed.get("confidence", "high"),
        }
    except Exception as err:
        logger.warning("LLM company extraction failed, falling back to heuristic: %s", err)
        return heuristic_company_name(file_name)
