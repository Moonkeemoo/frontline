"""LLM-driven generation of Ukrainian summaries from paper abstracts."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._llm import calc_cost, extract_text, strip_code_fence
from .glossary import Glossary
from .models import Paper, SummaryUA

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
DEFAULT_GENERATE_PROMPT = PROMPTS_DIR / "generate.md"
DEFAULT_MODEL = "claude-sonnet-4-6"


@dataclass
class GenerateResult:
    summary: SummaryUA
    cost_usd: float
    raw_response: str


async def generate_summary(
    paper: Paper,
    *,
    glossary: Glossary,
    client: Any,
    model: str = DEFAULT_MODEL,
    prompt_path: Path | None = None,
    max_tokens: int = 2048,
) -> GenerateResult:
    """Generate a UA summary for a paper using an LLM.

    `client` must be an AsyncAnthropic-compatible client (or a mock with the
    same `.messages.create()` async interface).
    """
    system_prompt = build_system_prompt(glossary, prompt_path)
    user_message = build_user_message(paper)

    response = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = extract_text(response)
    cleaned = strip_code_fence(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"generate: could not parse LLM JSON response: {e}\n"
            f"Raw (first 500 chars): {raw[:500]}"
        ) from e

    summary = SummaryUA(**data)
    cost = calc_cost(model, response.usage.input_tokens, response.usage.output_tokens)
    return GenerateResult(summary=summary, cost_usd=cost, raw_response=raw)


def build_system_prompt(glossary: Glossary, prompt_path: Path | None = None) -> str:
    base = (prompt_path or DEFAULT_GENERATE_PROMPT).read_text(encoding="utf-8")
    return f"{base}\n\n## Glossary (live)\n\n{glossary.format_for_prompt()}"


def build_user_message(paper: Paper) -> str:
    return json.dumps(
        {
            "title": paper.title,
            "authors": paper.authors,
            "abstract": paper.abstract,
            "arxiv_id": paper.arxiv_id,
            "url": paper.url,
        },
        ensure_ascii=False,
    )
