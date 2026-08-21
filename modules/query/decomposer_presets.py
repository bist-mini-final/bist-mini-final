"""Forwarding presets from modules/query/decomposer.py for backwards compatibility."""

from modules.query.decomposer import (
    DECOMPOSER_PRESETS,
    LUNA_SYSTEM_PROMPT,
    LUNA_USER_TEMPLATE,
    RDB_FINANCIAL_SYSTEM_PROMPT,
    SIMPLE_SYSTEM_PROMPT,
    decomposer_config_presets,
)

__all__ = [
    "DECOMPOSER_PRESETS",
    "LUNA_SYSTEM_PROMPT",
    "LUNA_USER_TEMPLATE",
    "RDB_FINANCIAL_SYSTEM_PROMPT",
    "SIMPLE_SYSTEM_PROMPT",
    "decomposer_config_presets",
]
