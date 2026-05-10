"""Ingest papers from HuggingFace Papers daily and arXiv RSS feeds."""

import re
from datetime import datetime, timezone

import feedparser
import httpx

from .models import Paper

HF_DAILY_URL = "https://huggingface.co/api/daily_papers"
ARXIV_RSS_BASE = "http://export.arxiv.org/rss"


async def fetch_huggingface_daily(
    *,
    client: httpx.AsyncClient | None = None,
    limit: int = 10,
) -> list[Paper]:
    """Fetch HuggingFace daily-curated papers, sorted by their default order
    (typically upvotes). Returns up to `limit` papers."""
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=30)
    try:
        resp = await client.get(HF_DAILY_URL)
        resp.raise_for_status()
        items = resp.json()
    finally:
        if owns_client:
            await client.aclose()

    papers: list[Paper] = []
    for item in items[:limit]:
        paper_data = item.get("paper") or {}
        arxiv_id = paper_data.get("id")
        if not arxiv_id:
            continue
        authors = [
            a["name"] for a in paper_data.get("authors", []) if isinstance(a, dict) and a.get("name")
        ]
        try:
            papers.append(
                Paper(
                    arxiv_id=arxiv_id,
                    title=(paper_data.get("title") or "").strip(),
                    authors=authors or ["Unknown"],
                    abstract=(paper_data.get("summary") or "").strip(),
                    url=f"https://arxiv.org/abs/{arxiv_id}",
                    submitted_at=_parse_iso(paper_data.get("publishedAt")),
                    source="huggingface_daily",
                )
            )
        except Exception:
            continue
    return papers


async def fetch_arxiv_rss(
    category: str = "cs.LG",
    *,
    client: httpx.AsyncClient | None = None,
    limit: int = 20,
) -> list[Paper]:
    """Fetch recent papers from arXiv RSS feed for a given category."""
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=30)
    try:
        url = f"{ARXIV_RSS_BASE}/{category}"
        resp = await client.get(url)
        resp.raise_for_status()
        body = resp.text
    finally:
        if owns_client:
            await client.aclose()

    feed = feedparser.parse(body)
    papers: list[Paper] = []
    for entry in feed.entries[:limit]:
        link = entry.get("link", "")
        m = re.search(r"abs/([\w.]+?)(?:v\d+)?/?$", link)
        if not m:
            continue
        arxiv_id = m.group(1)
        raw_summary = entry.get("summary", "")
        clean_abstract = re.sub(r"<[^>]+>", "", raw_summary).strip()
        title = re.sub(r"<[^>]+>", "", entry.get("title", "")).strip()

        authors_raw = entry.get("author", "")
        authors = [a.strip() for a in authors_raw.split(",") if a.strip()] or ["Unknown"]

        try:
            papers.append(
                Paper(
                    arxiv_id=arxiv_id,
                    title=title,
                    authors=authors,
                    abstract=clean_abstract,
                    url=f"https://arxiv.org/abs/{arxiv_id}",
                    submitted_at=_parse_struct(entry.get("published_parsed")),
                    source="arxiv_rss",
                )
            )
        except Exception:
            continue
    return papers


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _parse_struct(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime(*value[:6], tzinfo=timezone.utc)
    except Exception:
        return None
