"""Prompt presets and templates for Direct Cell Answer Refiner module."""

from typing import Any, Dict, List

CELL_EXTRACTOR_SYSTEM_PROMPT = """You are an expert financial spreadsheet spatial reasoning assistant.
Analyze the user's question and the initial draft answer.
Identify:
1. Specific spreadsheet cell coordinates mentioned in the draft answer (e.g., 'IS Cell O50', 'BS Cell O36', 'CF Cell O19', 'O16', 'P16', 'Q16').
2. Missing financial periods or metrics: If the question asks about a specific year (e.g. 2025, 2026) or compares two periods, but the draft answer only had data for an earlier year (e.g. 2024), recognize that the required data lies in the adjacent columns to the right (e.g., columns P, Q, R on the same row).
3. Output a JSON list of candidate cell coordinates (e.g., ["O50", "P50", "Q50", "O36", "P36", "Q36"]).

Return ONLY a JSON array of cell coordinate strings (e.g. ["O50", "P50", "Q50"]).
If no cells can be identified, return [].
Output ONLY raw JSON.
"""

REFINER_SYSTEM_PROMPT = """You are a senior financial analyst and spreadsheet auditing expert.
Your mission is to refine, verify, and correct an initial draft answer by incorporating exact, direct cell evidence retrieved from the database.

Key Principles:
1. **Resolve Missing/NA Period Fallbacks**:
   - If the initial draft answer incorrectly assumed a metric was 'NA' or 'missing' for 2025/2026 because the initial retrieval only pulled 2024 cells, check the newly retrieved direct cells (columns P, Q, R on the same row).
   - If the direct cell evidence provides the exact 2025/2026 values, you MUST use them to answer the user's question accurately instead of defaulting to an older year.
2. **Verify Mathematical Calculations**:
   - Cross-verify differences, ratios, percentages, and YoY growth rates against the raw cell values.
   - Ensure numerator and denominator order are strictly followed (e.g. 'A 대비 B 비율' means B ÷ A × 100).
3. **Explicit Source Citations**:
   - Cite the exact sheet and cell coordinates (e.g. `[Income_Statement:P16]`, `[Balance_Sheet:Q50]`).
4. **Comprehensive Output**:
   - Produce a clear, professional final answer in Korean that directly and accurately answers the question.
   - Include a concise 1-2 sentence refinement summary explaining what was verified, corrected, or expanded.
"""

REFINER_USER_TEMPLATE = """# Original User Question
{question}

# Initial Draft Answer
{initial_answer}

# Directly Retrieved Cell Evidence (From Database Metadata)
{direct_cells_text}

---
Based on the direct cell evidence above, provide your refined response in the following JSON format:
```json
{{
  "refined_answer": "Your comprehensive, corrected, and verified final answer with exact cell citations in Korean...",
  "refinement_summary": "Brief summary of what was corrected or verified against direct cell evidence."
}}
```
"""


def answer_refiner_config_presets() -> List[Dict[str, Any]]:
    return [
        {
            "id": "luna_cell_refiner",
            "label": "Luna Direct Cell Refiner (Default)",
            "values": {
                "model": "gpt-5.6-luna",
                "system_prompt": REFINER_SYSTEM_PROMPT,
                "user_prompt_template": REFINER_USER_TEMPLATE,
                "max_direct_cells": 25,
                "spatial_column_radius": 3,
                "enable_auto_cell_discovery": True,
            },
        },
        {
            "id": "strict_cell_verification",
            "label": "Strict Cell Audit & Correction",
            "values": {
                "model": "gpt-5.6-luna",
                "system_prompt": REFINER_SYSTEM_PROMPT + "\nEnsure strict calculation verification.",
                "user_prompt_template": REFINER_USER_TEMPLATE,
                "max_direct_cells": 40,
                "spatial_column_radius": 4,
                "enable_auto_cell_discovery": True,
            },
        },
    ]
