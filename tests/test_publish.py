"""Tests for markdown rendering and Telegram message rendering."""

from datetime import datetime

import frontmatter
import pytest
from pytest_httpx import HTTPXMock

from pipeline.publish import (
    MAX_TELEGRAM_LEN,
    post_filename,
    post_to_telegram,
    render_post_markdown,
    render_telegram_message,
    slugify,
    write_post,
)


def test_render_post_markdown_has_all_sections(sample_paper, sample_summary):
    md = render_post_markdown(sample_paper, sample_summary)
    assert "## Що зробили" in md
    assert "## Чому це важливо для UA IT" in md
    assert "## Обмеження" in md
    assert "## Першоджерело" in md
    assert sample_paper.url in md
    assert sample_paper.arxiv_id in md


def test_render_post_markdown_has_valid_frontmatter(sample_paper, sample_summary):
    md = render_post_markdown(sample_paper, sample_summary)
    parsed = frontmatter.loads(md)
    assert parsed["title"] == sample_summary.title_ua
    assert parsed["arxiv_id"] == sample_paper.arxiv_id
    assert parsed["tags"] == sample_summary.tags


def test_render_post_lists_all_limitations(sample_paper, sample_summary):
    md = render_post_markdown(sample_paper, sample_summary)
    for limit in sample_summary.limitations_ua:
        assert limit in md


def test_slugify_handles_cyrillic():
    s = slugify("Self-refinement: коли модель редагує себе сама")
    assert s == "self-refinement-коли-модель-редагує-себе-сама"


def test_slugify_truncates():
    long_title = "a" * 200
    assert len(slugify(long_title, max_len=50)) == 50


def test_post_filename_format(sample_paper, sample_summary):
    today = datetime(2026, 5, 9)
    fn = post_filename(sample_paper, sample_summary, today=today)
    assert fn.startswith("2026-05-09-2511.12345-")
    assert fn.endswith(".md")


def test_write_post_creates_file(tmp_path, sample_paper, sample_summary):
    out = tmp_path / "posts"
    path = write_post(sample_paper, sample_summary, output_dir=out)
    assert path.exists()
    assert path.parent == out
    assert "## Що зробили" in path.read_text(encoding="utf-8")


def test_telegram_message_includes_essentials(sample_paper, sample_summary):
    msg = render_telegram_message(sample_paper, sample_summary)
    assert sample_summary.title_ua in msg
    assert sample_summary.tldr_ua in msg
    assert sample_paper.url in msg
    assert "#llm" in msg
    assert sample_paper.arxiv_id in msg


def test_telegram_message_includes_site_url_if_provided(sample_paper, sample_summary):
    msg = render_telegram_message(
        sample_paper, sample_summary, site_url="https://frontline.ua/posts/x"
    )
    assert "frontline.ua/posts/x" in msg


def test_telegram_message_under_limit(sample_paper, sample_summary):
    msg = render_telegram_message(sample_paper, sample_summary)
    assert len(msg) <= MAX_TELEGRAM_LEN


def test_telegram_message_html_escapes(sample_paper, sample_summary):
    sample_summary.tldr_ua = "Test <script>alert(1)</script> & more"
    msg = render_telegram_message(sample_paper, sample_summary)
    assert "<script>" not in msg
    assert "&lt;script&gt;" in msg
    assert "&amp;" in msg


async def test_post_to_telegram_calls_api(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.telegram.org/botABC/sendMessage",
        json={"ok": True, "result": {"message_id": 1}},
    )
    result = await post_to_telegram(
        "hello", bot_token="ABC", channel_id="@chan"
    )
    assert result["ok"] is True
