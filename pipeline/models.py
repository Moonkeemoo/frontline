"""Data contracts for the Frontline pipeline."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Source = Literal["huggingface_daily", "arxiv_rss", "openreview"]
Severity = Literal["high", "medium", "low"]
IssueCategory = Literal[
    "hallucination", "glossary", "why_matters", "tone", "grammar", "format"
]
Verdict = Literal["ok", "needs_review", "reject"]
Recommendation = Literal["publish", "queue_for_review", "regenerate"]


class Paper(BaseModel):
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    url: str
    submitted_at: datetime | None = None
    source: Source


class SummaryUA(BaseModel):
    title_ua: str
    tldr_ua: str
    what_they_did_ua: str
    why_matters_ua: str
    limitations_ua: list[str] = Field(min_length=1)
    tags: list[str] = Field(min_length=2, max_length=5)
    estimated_read_min: int = Field(ge=1, le=30)
    notes: str | None = None


class Issue(BaseModel):
    severity: Severity
    category: IssueCategory
    description: str
    evidence: str


class CritiqueResult(BaseModel):
    verdict: Verdict
    issues: list[Issue] = Field(default_factory=list)
    recommendation: Recommendation
    regenerate_feedback: str | None = None


class PipelineResult(BaseModel):
    """End-to-end outcome for one paper."""

    paper: Paper
    summary: SummaryUA | None = None
    critique: CritiqueResult | None = None
    error: str | None = None
    cost_usd: float = 0.0

    @property
    def published(self) -> bool:
        return (
            self.critique is not None
            and self.critique.recommendation == "publish"
        )
