"""Tests for the published log."""

from pipeline.log import PublishedLog
from pipeline.models import PipelineResult


def test_already_seen_false_on_missing_file(tmp_path):
    log = PublishedLog(tmp_path / "log.jsonl")
    assert log.already_seen("any.id") is False


def test_record_then_already_seen(tmp_path, sample_paper, sample_summary, sample_critique_ok):
    log = PublishedLog(tmp_path / "log.jsonl")
    result = PipelineResult(
        paper=sample_paper, summary=sample_summary, critique=sample_critique_ok
    )
    log.record(result)
    assert log.already_seen(sample_paper.arxiv_id) is True
    assert log.already_seen("never.published") is False


def test_record_appends(tmp_path, sample_paper, sample_summary, sample_critique_ok):
    log = PublishedLog(tmp_path / "log.jsonl")
    result = PipelineResult(
        paper=sample_paper, summary=sample_summary, critique=sample_critique_ok
    )
    log.record(result)
    log.record(result)
    lines = log.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_corrupt_line_ignored(tmp_path, sample_paper, sample_summary, sample_critique_ok):
    log_path = tmp_path / "log.jsonl"
    log_path.write_text("not-json\n", encoding="utf-8")
    log = PublishedLog(log_path)

    # corrupt line should not crash
    assert log.already_seen("anything") is False

    # subsequent record still works
    result = PipelineResult(
        paper=sample_paper, summary=sample_summary, critique=sample_critique_ok
    )
    log.record(result)
    assert log.already_seen(sample_paper.arxiv_id) is True
