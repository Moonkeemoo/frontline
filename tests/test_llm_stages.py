"""Tests for generate and critique stages with a mocked Anthropic client."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from pipeline._llm import calc_cost, strip_code_fence
from pipeline.critique import critique_summary
from pipeline.generate import generate_summary
from pipeline.glossary import Glossary


def _fake_anthropic_response(text: str, input_tokens: int = 1000, output_tokens: int = 500):
    """Build a mock Anthropic message response with one text block + usage."""
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def _fake_client(response_text: str, **usage):
    response = _fake_anthropic_response(response_text, **usage)
    client = SimpleNamespace()
    client.messages = SimpleNamespace(create=AsyncMock(return_value=response))
    return client


# --- generate ---


async def test_generate_summary_parses_response(sample_paper):
    glossary = Glossary.load()
    valid_json = json.dumps(
        {
            "title_ua": "Український заголовок",
            "tldr_ua": "Резюме на 2 речення.",
            "what_they_did_ua": "Опис методу.",
            "why_matters_ua": "Конкретні UA-IT use-cases.",
            "limitations_ua": ["обмеження 1"],
            "tags": ["llm", "test"],
            "estimated_read_min": 5,
        }
    )
    client = _fake_client(valid_json)
    result = await generate_summary(sample_paper, glossary=glossary, client=client)

    assert result.summary.title_ua == "Український заголовок"
    assert result.summary.tags == ["llm", "test"]
    assert result.cost_usd > 0
    client.messages.create.assert_awaited_once()


async def test_generate_summary_strips_code_fence(sample_paper):
    glossary = Glossary.load()
    valid_json = json.dumps(
        {
            "title_ua": "T",
            "tldr_ua": "x",
            "what_they_did_ua": "x",
            "why_matters_ua": "x",
            "limitations_ua": ["l"],
            "tags": ["a", "b"],
            "estimated_read_min": 3,
        }
    )
    fenced = f"```json\n{valid_json}\n```"
    client = _fake_client(fenced)

    result = await generate_summary(sample_paper, glossary=glossary, client=client)
    assert result.summary.title_ua == "T"


async def test_generate_summary_raises_on_invalid_json(sample_paper):
    glossary = Glossary.load()
    client = _fake_client("not valid json {{{")
    with pytest.raises(ValueError, match="could not parse"):
        await generate_summary(sample_paper, glossary=glossary, client=client)


# --- critique ---


async def test_critique_returns_ok_for_clean_summary(sample_paper, sample_summary):
    glossary = Glossary.load()
    response_json = json.dumps(
        {
            "verdict": "ok",
            "issues": [],
            "recommendation": "publish",
        }
    )
    client = _fake_client(response_json)

    result = await critique_summary(
        sample_paper, sample_summary, glossary=glossary, client=client
    )
    assert result.critique.verdict == "ok"
    assert result.critique.recommendation == "publish"
    assert len(result.critique.issues) == 0


async def test_critique_returns_reject_with_issues(sample_paper, sample_summary):
    glossary = Glossary.load()
    response_json = json.dumps(
        {
            "verdict": "reject",
            "issues": [
                {
                    "severity": "high",
                    "category": "hallucination",
                    "description": "Cites benchmark not in abstract",
                    "evidence": "ImageNet 12% improvement",
                }
            ],
            "recommendation": "regenerate",
            "regenerate_feedback": "Remove ImageNet claim.",
        }
    )
    client = _fake_client(response_json)

    result = await critique_summary(
        sample_paper, sample_summary, glossary=glossary, client=client
    )
    assert result.critique.verdict == "reject"
    assert len(result.critique.issues) == 1
    assert result.critique.issues[0].severity == "high"
    assert result.critique.regenerate_feedback is not None


# --- _llm helpers ---


def test_calc_cost_known_model():
    # Sonnet: input $3/M, output $15/M
    # 1000 input + 500 output → 0.003 + 0.0075 = 0.0105
    cost = calc_cost("claude-sonnet-4-6", 1000, 500)
    assert abs(cost - 0.0105) < 1e-9


def test_calc_cost_unknown_model_returns_zero():
    assert calc_cost("imaginary-model", 1000, 500) == 0.0


def test_strip_code_fence_handles_json_fence():
    inp = '```json\n{"a": 1}\n```'
    assert strip_code_fence(inp) == '{"a": 1}'


def test_strip_code_fence_handles_plain_fence():
    inp = "```\n{\"a\": 1}\n```"
    assert strip_code_fence(inp) == '{"a": 1}'


def test_strip_code_fence_no_fence_passthrough():
    assert strip_code_fence('{"a": 1}') == '{"a": 1}'
