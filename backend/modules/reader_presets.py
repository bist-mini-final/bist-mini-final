from typing import Dict, List

from .base import ModuleConfigPreset


READER_SYSTEM_PROMPT = """You are a Senior Financial Analyst and spreadsheet RAG reader.
Answer the user's Korean financial question strictly from the supplied Excel cell context.

Rules:
1. State exact values, percentages, dates, and units without inventing missing facts.
2. Cite the supporting Cell ID for every numeric claim, for example [KS Cell E60].
3. For comparisons or calculations, show concise arithmetic steps.
4. Preserve source values such as NA and NM.
5. If the context is insufficient, explicitly say which fact is missing.
6. Respond in Korean unless the user requests another language."""

READER_USER_TEMPLATE = """Retrieved Financial Cell Context:
{context_text}

User Question:
{question}

Grounded Financial Answer:"""

STRICT_CITATION_SYSTEM_PROMPT = READER_SYSTEM_PROMPT + """
7. Include row header, column header, and Cell ID in every citation sentence."""


READER_PRESETS: Dict[str, Dict[str, str]] = {
    "luna_reader": {
        "system_prompt": READER_SYSTEM_PROMPT,
        "user_prompt_template": READER_USER_TEMPLATE,
    },
    "strict_citation": {
        "system_prompt": STRICT_CITATION_SYSTEM_PROMPT,
        "user_prompt_template": READER_USER_TEMPLATE,
    },
}


def reader_config_presets() -> List[ModuleConfigPreset]:
    labels = {
        "luna_reader": "Financial RDB Reader",
        "strict_citation": "Strict Cell Citation Reader",
    }
    return [
        ModuleConfigPreset(
            id=preset_id,
            label=labels[preset_id],
            values={"preset": preset_id, **values},
        )
        for preset_id, values in READER_PRESETS.items()
    ]
