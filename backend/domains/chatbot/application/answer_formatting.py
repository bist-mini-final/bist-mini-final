"""Pure transformations for user-facing chatbot answers."""

from __future__ import annotations

import re
from typing import Any


def reader_answer(run: Any) -> str | None:
    """Read the normalized answer text from a completed workflow run."""
    output = run.nodes.get("read").output if run.nodes.get("read") else None
    if not isinstance(output, dict):
        return None
    answer = (
        output.get("answer_json", {}).get("answer")
        if isinstance(output.get("answer_json"), dict)
        else None
    )
    return answer if isinstance(answer, str) and answer.strip() else None


def repair_inline_markdown_tables(answer: str) -> str:
    """Restore a GFM table when a model emits all of its rows on one line."""
    repaired_lines: list[str] = []
    for line in re.sub(r"\\+\|", "|", answer).splitlines():
        separator_start = line.find("|---")
        table_start = line.find("|")
        if separator_start < 0 or table_start < 0 or table_start >= separator_start:
            repaired_lines.append(line)
            continue

        header_cells = [
            cell.strip() for cell in line[table_start:separator_start].split("|") if cell.strip()
        ]
        following_cells = [
            cell.strip() for cell in line[separator_start:].split("|") if cell.strip()
        ]
        separator_cells = following_cells[: len(header_cells)]
        data_cells = following_cells[len(header_cells) :]
        is_separator = all(re.fullmatch(r":?-{3,}:?", cell) for cell in separator_cells)
        row_count = len(data_cells) // len(header_cells)
        if len(header_cells) < 3 or not is_separator or not row_count:
            repaired_lines.append(line)
            continue

        rows = [
            data_cells[index : index + len(header_cells)]
            for index in range(0, row_count * len(header_cells), len(header_cells))
        ]
        table = [
            f"| {' | '.join(header_cells)} |",
            f"| {' | '.join(separator_cells)} |",
            *(f"| {' | '.join(row)} |" for row in rows),
        ]
        remainder = " | ".join(data_cells[row_count * len(header_cells) :]).strip()
        table_str = "\n".join(table)
        suffix = f"\n{remainder}" if remainder else ""
        repaired_lines.append(f"{line[:table_start]}{table_str}{suffix}")
    return "\n".join(repaired_lines)


def format_user_facing_answer(answer: str) -> str:
    """Keep missing-evidence disclosures while replacing raw source-system labels."""
    cleaned = repair_inline_markdown_tables(answer)
    cleaned = re.sub(
        r"(?<![A-Za-z])NA(?![A-Za-z])\s*로?\s*근거가 부족(?:합니다|해요)?",
        "확인 가능한 근거가 부족해 요약에서 제외했습니다",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"(?<![A-Za-z])NA(?![A-Za-z])\s*로 표시되어 있어",
        "확인 가능한 값이 없어",
        cleaned,
        flags=re.IGNORECASE,
    )
    return re.sub(
        r"\s*[;\uff1b]\s*(?=(?:\*\*)?[^\n]*확인 가능한 근거가 부족)",
        "\n\n",
        cleaned,
    )


def with_company_intro(answer: str, company: str | None, question: str) -> str:
    """Add a stable, context-aware company introduction when the model omitted one."""
    if not company:
        return answer
    short_name = company.split("(", 1)[0].strip()
    period = re.search(r"(20\d{2})년", question)
    lowered = question.casefold()
    if "현금흐름" in question or "cash flow" in lowered or "fcf" in lowered:
        topic = "현금흐름 추이"
    elif "총자산" in question and "총부채" in question:
        topic = "총자산과 총부채"
    elif "실적" in question:
        topic = f"{period.group(1)}년 최신 실적" if period else "최신 실적"
    elif "매출" in question:
        topic = "매출"
    else:
        topic = "재무 현황"
    intro = f"{company.strip()}의 {topic}는 다음과 같습니다."
    generic_intro = re.compile(
        rf"{re.escape(short_name)}(?:\s*\([^)]*\))?의\s*질문하신 항목은 다음과 같습니다\.",
        flags=re.IGNORECASE,
    )
    if generic_intro.search(answer[:240]):
        return generic_intro.sub(intro, answer, count=1)
    if short_name.casefold() in answer[:240].casefold():
        return answer
    return f"{intro}\n\n{answer}"


def visualization_card_id(question: str) -> str:
    lowered = question.lower()
    if "매출" in lowered:
        return "revenue_growth"
    if "마진" in lowered or "이익률" in lowered:
        return "profitability"
    if "현금흐름" in lowered or "fcf" in lowered:
        return "cash_flow"
    if "자산" in lowered or "부채" in lowered or "자본" in lowered:
        return "financial_scale"
    return "stability"


__all__ = [
    "format_user_facing_answer",
    "reader_answer",
    "repair_inline_markdown_tables",
    "visualization_card_id",
    "with_company_intro",
]
