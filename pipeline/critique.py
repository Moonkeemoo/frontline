"""LLM-driven critique of generated UA summaries."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._llm import calc_cost, extract_text, strip_code_fence
from .glossary import Glossary
from .models import CritiqueResult, Paper, SummaryUA

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
DEFAULT_CRITIQUE_PROMPT = PROMPTS_DIR / "critique.md"
DEFAULT_MODEL = "claude-opus-4-7"


@dataclass
class CritiqueRunResult:
    critique: CritiqueResult
    cost_usd: float
    raw_response: str


async def critique_summary(
    paper: Paper,
    summary: SummaryUA,
    *,
    glossary: Glossary,
    client: Any,
    model: str = DEFAULT_MODEL,
    prompt_path: Path | None = None,
    max_tokens: int = 2048,
) -> CritiqueRunResult:
    """Run quality critique on a generated summary. Different model than
    generator is recommended (the whole point of triple-LLM gate)."""
    system_prompt = build_system_prompt(glossary, prompt_path)
    user_message = build_user_message(paper, summary)

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
            f"critique: could not parse LLM JSON response: {e}\n"
            f"Raw (first 500 chars): {raw[:500]}"
        ) from e

    critique = CritiqueResult(**data)
    cost = calc_cost(model, response.usage.input_tokens, response.usage.output_tokens)
    return CritiqueRunResult(critique=critique, cost_usd=cost, raw_response=raw)


def build_system_prompt(glossary: Glossary, prompt_path: Path | None = None) -> str:
    base = (prompt_path or DEFAULT_CRITIQUE_PROMPT).read_text(encoding="utf-8")
    return f"{base}\n\n## Glossary (live)\n\n{glossary.format_for_prompt()}"


def build_user_message(paper: Paper, summary: SummaryUA) -> str:
    return json.dumps(
        {
            "original": {
                "title": paper.title,
                "abstract": paper.abstract,
                "authors": paper.authors,
            },
            "summary_ua": summary.model_dump(),
        },
        ensure_ascii=False,
    )
