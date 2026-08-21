from __future__ import annotations

"""Forwarding presets from modules/reader/reader.py for backwards compatibility."""

from modules.reader.reader import (
    READER_PRESETS,
    READER_SYSTEM_PROMPT,
    READER_USER_TEMPLATE,
    STRICT_CITATION_SYSTEM_PROMPT,
    reader_config_presets,
)

__all__ = [
    "READER_PRESETS",
    "READER_SYSTEM_PROMPT",
    "READER_USER_TEMPLATE",
    "STRICT_CITATION_SYSTEM_PROMPT",
    "reader_config_presets",
]
