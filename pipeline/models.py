"""Data contracts for the Frontline pipeline."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Source = Literal[
    "huggingface_daily",
    "hackernews",
    "arxiv_rss",
    "iacr_eprint",
    "openreview",
]
Severity = Literal["high", "medium", "low"]
IssueCategory = Literal[
    "hallucination",
    "glossary",
    "why_matters",
    "tone",
    "grammar",
    "format",
    # Added in non-tech-friendly voice update:
    "jargon",
    "long_paragraph",
    "long_sentence",
    "missing_bold",
]
Verdict = Literal["ok", "needs_review", "reject"]
Recommendation = Literal["publish", "queue_for_review", "regenerate"]


class Paper(BaseModel):
    arxiv_id: str  # legacy field name; treats as external identifier per source
    title: str
    authors: list[str]
    abstract: str
    url: str
    submitted_at: datetime | None = None
    source: Source

    @property
    def source_label(self) -> str:
        """Display prefix like 'arXiv:2511.12345' or 'IACR:2026/123'."""
        prefix = {
            "iacr_eprint": "IACR",
            "openreview": "OpenReview",
        }.get(self.source, "arXiv")
        return f"{prefix}:{self.arxiv_id}"

    @property
    def signal_label(self) -> str:
        """Where the paper came to our attention from."""
        return {
            "huggingface_daily": "HF curated",
            "hackernews": "HN community",
            "arxiv_rss": "arXiv recency",
            "iacr_eprint": "IACR new",
            "openreview": "OpenReview",
        }.get(self.source, self.source)


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
