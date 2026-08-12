from typing import Dict, Any, Tuple, Optional

# Official OpenAI Pricing per 1 Million Tokens (USD)
# (input_rate, cached_input_rate, output_rate)
OPENAI_PRICING_MAP: Dict[str, Tuple[float, float, float]] = {
    "gpt-4o-mini": (0.15, 0.075, 0.60),
    "gpt-4o": (2.50, 1.25, 10.00),
    "gpt-4.5": (75.00, 37.50, 150.00),
    "o1": (15.00, 7.50, 60.00),
    "o3-mini": (1.10, 0.55, 4.40),
    "text-embedding-3-large": (0.13, 0.13, 0.00),
    "text-embedding-3-small": (0.02, 0.02, 0.00),
}


def calculate_openai_cost(
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int = 0,
    cached_tokens: int = 0,
) -> float:
    """Calculate USD cost for an OpenAI API call using official pricing."""
    clean_model = (model_name or "").lower().strip()

    pricing: Optional[Tuple[float, float, float]] = None
    for key, rate_tuple in OPENAI_PRICING_MAP.items():
        if key in clean_model:
            pricing = rate_tuple
            break

    if pricing is None:
        # Default fallback to gpt-4o-mini pricing
        pricing = (0.15, 0.075, 0.60)

    input_rate, cached_rate, output_rate = pricing
    regular_prompt = max(0, prompt_tokens - cached_tokens)

    cost = (
        (regular_prompt / 1_000_000.0) * input_rate
        + (cached_tokens / 1_000_000.0) * cached_rate
        + (completion_tokens / 1_000_000.0) * output_rate
    )
    return round(cost, 6)
