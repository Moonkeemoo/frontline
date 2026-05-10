"""Render summaries as markdown posts and Telegram messages."""

import re
from datetime import datetime
from pathlib import Path

import frontmatter
import httpx

from .models import CritiqueResult, Paper, SummaryUA

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_TELEGRAM_LEN = 4096


def render_post_markdown(
    paper: Paper,
    summary: SummaryUA,
    *,
    critique: CritiqueResult | None = None,
) -> str:
    """Render an Astro-compatible markdown post with frontmatter.

    If `critique` is passed, it is embedded under a `critique:` key — used
    for queue items so reviewers can see what the critic flagged.
    """
    fm: dict = {
        "title": summary.title_ua,
        "tldr": summary.tldr_ua,
        "tags": summary.tags,
        "read_min": summary.estimated_read_min,
        "arxiv_id": paper.arxiv_id,
        "arxiv_url": paper.url,
        "authors": paper.authors,
        "source": paper.source,
        "publish_date": datetime.now().date().isoformat(),
    }
    if paper.submitted_at:
        fm["submitted_at"] = paper.submitted_at.isoformat()
    if critique is not None:
        fm["critique"] = critique.model_dump()

    parts: list[str] = [
        "## Що зробили",
        "",
        summary.what_they_did_ua,
        "",
        "## Чому це важливо для UA IT",
        "",
        summary.why_matters_ua,
        "",
        "## Обмеження",
        "",
    ]
    parts.extend(f"- {limit}" for limit in summary.limitations_ua)
    parts.extend(
        [
            "",
            "## Першоджерело",
            "",
            f"- Paper: <https://arxiv.org/pdf/{paper.arxiv_id}>",
            f"- arXiv abstract: <{paper.url}>",
            f"- Authors: {', '.join(paper.authors)}",
        ]
    )
    body = "\n".join(parts)

    post = frontmatter.Post(content=body, **fm)
    return frontmatter.dumps(post)


_SLUG_RE = re.compile(r"[^\w\s-]", flags=re.UNICODE)
_SLUG_SPACE_RE = re.compile(r"[\s_]+")


def slugify(text: str, max_len: int = 60) -> str:
    """Slugify supporting Cyrillic — lowercase, keep alphanumerics, replace spaces."""
    text = text.lower()
    text = _SLUG_RE.sub("", text)
    text = _SLUG_SPACE_RE.sub("-", text)
    return text.strip("-")[:max_len].rstrip("-")


def post_filename(paper: Paper, summary: SummaryUA, *, today: datetime | None = None) -> str:
    today = today or datetime.now()
    return f"{today:%Y-%m-%d}-{paper.arxiv_id}-{slugify(summary.title_ua)}.md"


def write_post(
    paper: Paper,
    summary: SummaryUA,
    *,
    output_dir: Path,
    today: datetime | None = None,
    critique: CritiqueResult | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / post_filename(paper, summary, today=today)
    path.write_text(
        render_post_markdown(paper, summary, critique=critique),
        encoding="utf-8",
    )
    return path


def render_telegram_message(
    paper: Paper, summary: SummaryUA, *, site_url: str | None = None
) -> str:
    """Render a compact Telegram message (HTML parse mode)."""
    lines: list[str] = [
        f"<b>{_html_escape(summary.title_ua)}</b>",
        "",
        f"<i>arXiv:{paper.arxiv_id}</i> · {summary.estimated_read_min} хв читання",
        "",
        _html_escape(summary.tldr_ua),
        "",
    ]
    if site_url:
        lines.append(f'📖 <a href="{site_url}">Повний пост</a>')
    lines.append(f'📄 <a href="{paper.url}">Оригінал на arXiv</a>')
    lines.append("")
    lines.append(" ".join(f"#{t}" for t in summary.tags))

    text = "\n".join(lines)
    if len(text) > MAX_TELEGRAM_LEN:
        text = text[: MAX_TELEGRAM_LEN - 1] + "…"
    return text


async def post_to_telegram(
    text: str,
    *,
    bot_token: str,
    channel_id: str,
    client: httpx.AsyncClient | None = None,
) -> dict:
    """POST to Telegram sendMessage. Raises on HTTP error."""
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=30)
    try:
        resp = await client.post(
            TELEGRAM_API.format(token=bot_token),
            json={
                "chat_id": channel_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
        )
        resp.raise_for_status()
        return resp.json()
    finally:
        if owns_client:
            await client.aclose()


def _html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
