"""Shared pytest fixtures."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pipeline.models import CritiqueResult, Issue, Paper, SummaryUA

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_paper() -> Paper:
    return Paper(
        arxiv_id="2511.12345",
        title="Self-Refining Models: Iterative Critique Without RLHF",
        authors=["Jane Smith", "John Doe"],
        abstract=(
            "We introduce a simple two-pass scheme where a language model "
            "first generates an answer and then critiques and revises its "
            "own output. Across 7 reasoning benchmarks (GSM8K, MATH, etc.) "
            "we observe gains of 8-15% over the base model with no "
            "additional training data."
        ),
        url="https://arxiv.org/abs/2511.12345",
        submitted_at=datetime(2026, 5, 9, tzinfo=UTC),
        source="huggingface_daily",
    )


@pytest.fixture
def sample_summary() -> SummaryUA:
    return SummaryUA(
        title_ua="Self-refinement: коли модель редагує себе сама",
        tldr_ua=(
            "Двопрохідна схема (генерація → critique → ревізія) дає "
            "+8-15% точності на reasoning-бенчмарках без додаткових даних."
        ),
        what_they_did_ua=(
            "Автори пропонують просту схему: модель видає відповідь, потім "
            "та сама модель робить critique-розбір і пише revision. На 7 "
            "reasoning-бенчмарках (GSM8K, MATH тощо) середній приріст 8-15%."
        ),
        why_matters_ua=(
            "Для українських продуктових команд, що self-host LLM на "
            "власних GPU, це шлях вичавити більше якості без переходу на "
            "дорожчі моделі. Особливо актуально для B2B AI-асистентів і "
            "code-assist інструментів, де accuracy важливіша за latency."
        ),
        limitations_ua=[
            "Працює лише на моделях ≥7B параметрів",
            "Втричі дорожчий *inference*",
        ],
        tags=["llm", "training", "efficiency"],
        estimated_read_min=6,
    )


@pytest.fixture
def sample_critique_ok() -> CritiqueResult:
    return CritiqueResult(
        verdict="ok",
        issues=[],
        recommendation="publish",
    )


@pytest.fixture
def sample_critique_reject() -> CritiqueResult:
    return CritiqueResult(
        verdict="reject",
        issues=[
            Issue(
                severity="high",
                category="hallucination",
                description="Cited benchmark not in abstract",
                evidence="ImageNet top-1 покращення 12%",
            )
        ],
        recommendation="regenerate",
        regenerate_feedback="Remove ImageNet claim — not in source.",
    )
