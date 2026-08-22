from typing import Any

MAX_COLLECTION_PREVIEW = 8
MAX_VECTOR_PREVIEW = 12


def compact_history_value(value: Any, depth: int = 0) -> Any:
    """Keep run history inspectable without duplicating large vectors and document arrays."""

    if depth >= 6:
        return {"_summary": "maximum preview depth reached"}
    if isinstance(value, dict):
        return {
            key: compact_history_value(item, depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, list):
        if value and all(isinstance(item, (int, float)) for item in value):
            if len(value) <= MAX_VECTOR_PREVIEW:
                return value
            return {
                "_summary": "numeric vector",
                "length": len(value),
                "sample": value[:MAX_VECTOR_PREVIEW],
            }
        if len(value) <= MAX_COLLECTION_PREVIEW:
            return [compact_history_value(item, depth + 1) for item in value]
        return {
            "_summary": "collection preview",
            "count": len(value),
            "items": [
                compact_history_value(item, depth + 1)
                for item in value[:MAX_COLLECTION_PREVIEW]
            ],
        }
    if isinstance(value, str) and len(value) > 20_000:
        return {
            "_summary": "long text",
            "characters": len(value),
            "preview": value[:2_000],
        }
    return value
