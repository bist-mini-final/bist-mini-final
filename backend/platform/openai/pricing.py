"""Current OpenAI token pricing used for execution telemetry."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenRates:
    input_per_million: float
    cached_input_per_million: float
    output_per_million: float


MODEL_RATES: dict[str, TokenRates] = {
    "gpt-5.6-sol": TokenRates(5.00, 0.50, 30.00),
    "gpt-5.6-terra": TokenRates(2.00, 0.20, 12.00),
    "gpt-5.6-luna": TokenRates(0.20, 0.02, 1.20),
    "text-embedding-3-large": TokenRates(0.13, 0.13, 0.00),
    "text-embedding-3-small": TokenRates(0.02, 0.02, 0.00),
}


def calculate_openai_cost(
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int = 0,
    cached_tokens: int = 0,
) -> float:
    """Estimate USD cost without inventing a fallback rate for unknown models."""

    normalized = model_name.casefold().strip()
    if normalized == "gpt-5.6":
        normalized = "gpt-5.6-sol"
    matched_model = next(
        (model for model in MODEL_RATES if model in normalized),
        None,
    )
    if matched_model is None:
        return 0.0
    rates = MODEL_RATES[matched_model]

    cached = min(max(0, cached_tokens), max(0, prompt_tokens))
    uncached = max(0, prompt_tokens - cached)
    is_generation_model = not matched_model.startswith("text-embedding-")
    input_multiplier = (
        2.0 if is_generation_model and prompt_tokens > 272_000 else 1.0
    )
    output_multiplier = (
        1.5 if is_generation_model and prompt_tokens > 272_000 else 1.0
    )
    cost = (
        uncached * rates.input_per_million * input_multiplier
        + cached * rates.cached_input_per_million * input_multiplier
        + max(0, completion_tokens) * rates.output_per_million * output_multiplier
    ) / 1_000_000.0
    return round(cost, 8)
