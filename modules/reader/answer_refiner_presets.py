from __future__ import annotations

"""Forwarding presets from modules/reader/answer_refiner.py for backwards compatibility."""

from modules.reader.answer_refiner import (
    CELL_EXTRACTOR_SYSTEM_PROMPT,
    REFINER_SYSTEM_PROMPT,
    REFINER_USER_TEMPLATE,
    answer_refiner_config_presets,
)

__all__ = [
    "CELL_EXTRACTOR_SYSTEM_PROMPT",
    "REFINER_SYSTEM_PROMPT",
    "REFINER_USER_TEMPLATE",
    "answer_refiner_config_presets",
]
