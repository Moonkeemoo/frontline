"""End-to-end orchestrator tests with all external calls mocked."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from pipeline.models import Paper
from pipeline.run import run_pipeline


def _fake_response(text: str, in_tok: int = 1000, out_tok: int = 500):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=in_tok, output_tokens=out_tok),
    )


def _gen_text(title: str = "T") -> str:
    return json.dumps(
        {
            "title_ua": title,
            "tldr_ua": "x",
            "what_they_did_ua": "x",
            "why_matters_ua": "x",
            "limitations_ua": ["limit"],
            "tags": ["llm", "test"],
            "estimated_read_min": 3,
        }
    )


def _crit_text(verdict: str = "ok", rec: str = "publish") -> str:
    return json.dumps(
        {"verdict": verdict, "issues": [], "recommendation": rec}
    )


def _fake_client(responses: list[str]):
    """Build a client whose .messages.create returns the given texts in order."""
    fake_responses = [_fake_response(t) for t in responses]
    client = SimpleNamespace()
    client.messages = SimpleNamespace(create=AsyncMock(side_effect=fake_responses))
    return client


@pytest.fixture
def two_papers(sample_paper) -> list[Paper]:
    return [
        sample_paper,
        sample_paper.model_copy(update={"arxiv_id": "2511.99999", "title": "Other"}),
    ]


async def test_run_pipeline_publishes_clean_summaries(
    tmp_path, two_papers, monkeypatch
):
    monkeypatch.setattr(
        "pipeline.run.fetch_all_sources", AsyncMock(return_value=two_papers)
    )
    client = _fake_client(
        [_gen_text("Один"), _crit_text(), _gen_text("Два"), _crit_text()]
    )

    stats = await run_pipeline(
        output_dir=tmp_path / "posts",
        queue_dir=tmp_path / "queue",
        log_path=tmp_path / "log.jsonl",
        client=client,
    )

    assert stats["fetched"] == 2
    assert stats["fresh"] == 2
    assert stats["published"] == 2
    assert stats["queued"] == 0
    assert stats["rejected"] == 0
    md_files = list((tmp_path / "posts").glob("*.md"))
    assert len(md_files) == 2


async def test_run_pipeline_routes_queue_and_reject(
    tmp_path, two_papers, monkeypatch
):
    monkeypatch.setattr(
        "pipeline.run.fetch_all_sources", AsyncMock(return_value=two_papers)
    )
    # Paper 1: queue. Paper 2: reject.
    client = _fake_client(
        [
            _gen_text("Один"),
            _crit_text(verdict="needs_review", rec="queue_for_review"),
            _gen_text("Два"),
            _crit_text(verdict="reject", rec="regenerate"),
        ]
    )

    stats = await run_pipeline(
        output_dir=tmp_path / "posts",
        queue_dir=tmp_path / "queue",
        log_path=tmp_path / "log.jsonl",
        client=client,
    )

    assert stats["published"] == 0
    assert stats["queued"] == 1
    assert stats["rejected"] == 1
    assert not (tmp_path / "posts").exists() or not list(
        (tmp_path / "posts").glob("*.md")
    )
    queue_files = list((tmp_path / "queue").glob("*.md"))
    assert len(queue_files) == 1


async def test_run_pipeline_skips_already_seen(
    tmp_path, two_papers, monkeypatch
):
    log_path = tmp_path / "log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        json.dumps({"arxiv_id": two_papers[0].arxiv_id, "title": "old"}) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "pipeline.run.fetch_all_sources", AsyncMock(return_value=two_papers)
    )
    client = _fake_client([_gen_text(), _crit_text()])

    stats = await run_pipeline(
        output_dir=tmp_path / "posts",
        queue_dir=tmp_path / "queue",
        log_path=log_path,
        client=client,
    )

    assert stats["fetched"] == 2
    assert stats["fresh"] == 1
    assert stats["published"] == 1


async def test_run_pipeline_respects_cost_cap(
    tmp_path, two_papers, monkeypatch
):
    monkeypatch.setattr(
        "pipeline.run.fetch_all_sources", AsyncMock(return_value=two_papers)
    )
    client = _fake_client(
        [_gen_text("Один"), _crit_text(), _gen_text("Два"), _crit_text()]
    )

    # gen+crit per paper ≈ $0.063 (sonnet $0.0105 + opus $0.0525). Cap blocks 2nd.
    stats = await run_pipeline(
        output_dir=tmp_path / "posts",
        queue_dir=tmp_path / "queue",
        log_path=tmp_path / "log.jsonl",
        cost_cap_usd=0.05,
        client=client,
    )

    assert stats["published"] == 1
    assert stats.get("cost_cap_hit") is True


async def test_run_pipeline_dry_run_writes_nothing(
    tmp_path, two_papers, monkeypatch
):
    monkeypatch.setattr(
        "pipeline.run.fetch_all_sources", AsyncMock(return_value=two_papers)
    )
    client = _fake_client(
        [_gen_text("Один"), _crit_text(), _gen_text("Два"), _crit_text()]
    )

    stats = await run_pipeline(
        output_dir=tmp_path / "posts",
        queue_dir=tmp_path / "queue",
        log_path=tmp_path / "log.jsonl",
        dry_run=True,
        client=client,
    )

    assert stats["published"] == 2  # stat counts but no files
    assert not (tmp_path / "posts").exists() or not list(
        (tmp_path / "posts").glob("*.md")
    )


async def test_run_pipeline_handles_llm_error_gracefully(
    tmp_path, two_papers, monkeypatch
):
    monkeypatch.setattr(
        "pipeline.run.fetch_all_sources", AsyncMock(return_value=two_papers)
    )

    client = SimpleNamespace()
    client.messages = SimpleNamespace(
        create=AsyncMock(side_effect=RuntimeError("API down"))
    )

    stats = await run_pipeline(
        output_dir=tmp_path / "posts",
        queue_dir=tmp_path / "queue",
        log_path=tmp_path / "log.jsonl",
        client=client,
    )

    # Both fail individually but pipeline doesn't crash
    assert stats["errors"] == 2
    assert stats["published"] == 0
