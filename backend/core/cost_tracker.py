"""Cost tracking and token usage estimation utilities."""

from typing import Dict

EMBEDDING_PRICING_PER_MILLION: Dict[str, float] = {
    "text-embedding-3-small": 0.02,  # $0.02 per 1M tokens
    "text-embedding-3-large": 0.13,  # $0.13 per 1M tokens
    "text-embedding-ada-002": 0.10,  # $0.10 per 1M tokens
    "BAAI/bge-m3": 0.0,  # Open source local
    "BAAI/bge-large-en-v1.5": 0.0,
}

USD_TO_KRW_RATE: float = 1380.0


def calculate_embedding_cost(model_name: str, total_tokens: int) -> Dict[str, float]:
    """Calculate USD and KRW cost for embedding token usage."""
    rate = EMBEDDING_PRICING_PER_MILLION.get(model_name, 0.0)
    cost_usd = round((total_tokens / 1_000_000.0) * rate, 6)
    cost_krw = round(cost_usd * USD_TO_KRW_RATE, 2)
    return {
        "cost_usd": cost_usd,
        "cost_krw": cost_krw,
    }
