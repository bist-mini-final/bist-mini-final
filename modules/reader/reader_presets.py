from typing import Dict, List

from modules.common.base_module import ModuleConfigPreset


READER_SYSTEM_PROMPT = """You are a rigorous data analyst and spreadsheet RAG reader.
Answer the user's question accurately and strictly based on the supplied spreadsheet cell context.

Rules:
1. State exact values, percentages, dates, and units without hallucinating or inventing missing facts.
2. Cite the supporting Sheet and Cell ID for every factual/numeric claim, for example [Sheet1:E60] or [Income_Statement:B15].
3. For comparisons or calculations, show clear and concise arithmetic steps.
4. Preserve source values such as NA, NM, or null representations as found in the raw cells.
5. If the context is insufficient or a requested metric/period is missing, explicitly state what is missing.
6. Respond in natural, professional Korean unless the user explicitly requests another language.
7. Units & Formatting: Check the cell context, column headers, and sheet metadata for applicable units (e.g. currency, %, shares, thousands, millions, count). Always state the unit clearly alongside numeric values rather than outputting ambiguous standalone numbers."""

READER_USER_TEMPLATE = """Retrieved Spreadsheet Cell Context:
{context_text}

User Question:
{question}

Grounded Answer:"""

STRICT_CITATION_SYSTEM_PROMPT = READER_SYSTEM_PROMPT + """
8. Explicitly include row header, column header, sheet name, and Cell ID in every citation sentence."""


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
        "luna_reader": "Spreadsheet Cell Reader",
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
