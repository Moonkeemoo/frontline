"""Shared helpers for LLM stages — JSON extraction, cost calculation."""

from typing import Any

# Anthropic API pricing per 1M tokens (USD), as of 2026-05.
# Update if Anthropic changes prices.
PRICING: dict[str, tuple[float, float]] = {
    # model: (input $/Mtok, output $/Mtok)
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-7": (15.0, 75.0),
    "claude-haiku-4-5-20251001": (0.80, 4.0),
}


def calc_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return USD cost for a single LLM call. 0.0 if model unknown."""
    pricing = PRICING.get(model)
    if not pricing:
        return 0.0
    input_per_m, output_per_m = pricing
    return (input_tokens * input_per_m + output_tokens * output_per_m) / 1_000_000


def extract_text(response: Any) -> str:
    """Concatenate text blocks from an Anthropic response."""
    return "".join(
        block.text for block in response.content
        if getattr(block, "type", None) == "text"
    )


def strip_code_fence(text: str) -> str:
    """Strip ```json ... ``` or ``` ... ``` wrappers if present."""
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()
