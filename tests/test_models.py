"""Validation tests for pydantic data contracts."""

import pytest
from pydantic import ValidationError

from pipeline.models import PipelineResult, SummaryUA


def test_summary_requires_at_least_one_limitation():
    with pytest.raises(ValidationError):
        SummaryUA(
            title_ua="t",
            tldr_ua="x",
            what_they_did_ua="x",
            why_matters_ua="x",
            limitations_ua=[],
            tags=["a", "b"],
            estimated_read_min=3,
        )


def test_summary_tag_count_bounds():
    base = dict(
        title_ua="t",
        tldr_ua="x",
        what_they_did_ua="x",
        why_matters_ua="x",
        limitations_ua=["limit"],
        estimated_read_min=3,
    )
    with pytest.raises(ValidationError):
        SummaryUA(**base, tags=["a"])
    with pytest.raises(ValidationError):
        SummaryUA(**base, tags=["a", "b", "c", "d", "e", "f"])
    SummaryUA(**base, tags=["a", "b"])  # 2 — ok
    SummaryUA(**base, tags=["a", "b", "c", "d", "e"])  # 5 — ok


def test_summary_read_min_range():
    base = dict(
        title_ua="t",
        tldr_ua="x",
        what_they_did_ua="x",
        why_matters_ua="x",
        limitations_ua=["limit"],
        tags=["a", "b"],
    )
    with pytest.raises(ValidationError):
        SummaryUA(**base, estimated_read_min=0)
    with pytest.raises(ValidationError):
        SummaryUA(**base, estimated_read_min=31)


def test_pipeline_result_published_only_when_recommendation_publish(
    sample_paper, sample_summary, sample_critique_ok, sample_critique_reject
):
    ok = PipelineResult(
        paper=sample_paper, summary=sample_summary, critique=sample_critique_ok
    )
    assert ok.published is True

    reject = PipelineResult(
        paper=sample_paper, summary=sample_summary, critique=sample_critique_reject
    )
    assert reject.published is False

    pending = PipelineResult(paper=sample_paper, summary=sample_summary)
    assert pending.published is False
