"""Ingest papers from HuggingFace Papers daily and arXiv RSS feeds."""

import asyncio
import logging
import re
from datetime import UTC, datetime

import feedparser
import httpx

from .models import Paper

HF_DAILY_URL = "https://huggingface.co/api/daily_papers"
ARXIV_RSS_BASE = "http://export.arxiv.org/rss"
ARXIV_API_URL = "http://export.arxiv.org/api/query"
IACR_RSS_URL = "https://eprint.iacr.org/rss/rss.xml"
HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"

# Regex to extract an arXiv ID from any arxiv.org URL pattern
ARXIV_ID_RE = re.compile(
    r"arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})", re.IGNORECASE
)

# arXiv categories — Phase 2 covers broad CS, not just AI/ML.
# Grouped by cluster for review:
DEFAULT_ARXIV_CATEGORIES = (
    # AI / ML / NLP / vision
    "cs.LG", "cs.AI", "cs.CL", "cs.CV", "cs.NE", "stat.ML",
    # Systems / infra / networking
    "cs.DC", "cs.OS", "cs.AR", "cs.PF", "cs.NI",
    # Software engineering / languages / theory
    "cs.SE", "cs.PL", "cs.LO", "cs.FL",
    # Data / information retrieval / structures
    "cs.DB", "cs.IR", "cs.DS",
    # Security / cryptography / information theory
    "cs.CR", "cs.IT",
    # Applications: robotics, graphics, HCI, sound, multi-agent
    "cs.RO", "cs.GR", "cs.HC", "cs.SD", "cs.MA",
    # Theory: complexity, geometry, game theory
    "cs.CC", "cs.CG", "cs.GT",
)

log = logging.getLogger(__name__)


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
            a["name"]
            for a in paper_data.get("authors", [])
            if isinstance(a, dict) and a.get("name")
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


async def fetch_hackernews_papers(
    *,
    client: httpx.AsyncClient | None = None,
    min_points: int = 30,
    since_hours: int = 72,
    limit: int = 15,
) -> list[Paper]:
    """Fetch papers (arxiv-linked stories) from Hacker News with min_points
    in the past `since_hours`. Resolves full metadata via arXiv API.

    This is a high-signal source: stories that gain HN traction are
    typically broadly interesting across CS, not just AI/ML — making it
    the natural antidote to AI-bubble in our pipeline.
    """
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=30)
    try:
        cutoff_ts = int(
            datetime.now(UTC).timestamp() - since_hours * 3600
        )
        params = {
            "query": "arxiv.org",
            "tags": "story",
            "numericFilters": f"points>{min_points},created_at_i>{cutoff_ts}",
            "hitsPerPage": str(min(limit * 3, 50)),  # over-fetch (some hits aren't papers)
        }
        resp = await client.get(HN_SEARCH_URL, params=params)
        resp.raise_for_status()
        hits = resp.json().get("hits", [])

        # Extract unique arXiv IDs with their HN points (for ranking later)
        candidates: list[tuple[str, int, int]] = []  # (id, points, created_ts)
        seen: set[str] = set()
        for hit in hits:
            url = hit.get("url") or ""
            m = ARXIV_ID_RE.search(url)
            if not m:
                continue
            aid = m.group(1)
            if aid in seen:
                continue
            seen.add(aid)
            candidates.append(
                (aid, int(hit.get("points") or 0), int(hit.get("created_at_i") or 0))
            )
            if len(candidates) >= limit:
                break

        if not candidates:
            return []

        # Resolve metadata via arXiv API (batch by id_list)
        id_list = ",".join(aid for aid, _, _ in candidates)
        meta_resp = await client.get(
            ARXIV_API_URL,
            params={"id_list": id_list, "max_results": str(len(candidates))},
        )
        meta_resp.raise_for_status()
        feed = feedparser.parse(meta_resp.text)

        meta_by_id: dict[str, tuple[str, str, list[str]]] = {}
        for entry in feed.entries:
            link = entry.get("id", "")
            m = ARXIV_ID_RE.search(link)
            if not m:
                continue
            aid = m.group(1)
            authors = [
                a.get("name", "")
                for a in entry.get("authors", [])
                if isinstance(a, dict) and a.get("name")
            ]
            title = re.sub(r"\s+", " ", entry.get("title", "")).strip()
            abstract = re.sub(r"\s+", " ", entry.get("summary", "")).strip()
            meta_by_id[aid] = (title, abstract, authors)

        papers: list[Paper] = []
        for aid, _points, ts in sorted(candidates, key=lambda c: c[1], reverse=True):
            meta = meta_by_id.get(aid)
            if not meta:
                continue
            title, abstract, authors = meta
            try:
                papers.append(
                    Paper(
                        arxiv_id=aid,
                        title=title,
                        authors=authors or ["Unknown"],
                        abstract=abstract,
                        url=f"https://arxiv.org/abs/{aid}",
                        submitted_at=datetime.fromtimestamp(ts, tz=UTC) if ts else None,
                        source="hackernews",
                    )
                )
            except Exception as e:
                log.debug("Skipped HN paper %s: %s", aid, e)
        return papers
    finally:
        if owns_client:
            await client.aclose()


async def fetch_iacr_eprint(
    *,
    client: httpx.AsyncClient | None = None,
    limit: int = 10,
) -> list[Paper]:
    """Fetch recent IACR ePrint Archive submissions (cryptography)."""
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=30)
    try:
        resp = await client.get(IACR_RSS_URL)
        resp.raise_for_status()
        body = resp.text
    finally:
        if owns_client:
            await client.aclose()

    feed = feedparser.parse(body)
    papers: list[Paper] = []
    for entry in feed.entries[:limit]:
        link = entry.get("link", "")
        m = re.search(r"eprint\.iacr\.org/(\d{4}/\d+)", link)
        if not m:
            continue
        eprint_id = m.group(1)  # "2026/123"
        title = re.sub(r"<[^>]+>", "", entry.get("title", "")).strip()
        abstract = re.sub(r"<[^>]+>", "", entry.get("summary", "")).strip()
        authors_raw = entry.get("author", "")
        authors = [a.strip() for a in authors_raw.split(",") if a.strip()] or [
            "Unknown"
        ]
        try:
            papers.append(
                Paper(
                    arxiv_id=eprint_id,
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    url=link,
                    submitted_at=_parse_struct(entry.get("published_parsed")),
                    source="iacr_eprint",
                )
            )
        except Exception:
            continue
    return papers


async def fetch_all_sources(
    *,
    client: httpx.AsyncClient | None = None,
    arxiv_categories: tuple[str, ...] = DEFAULT_ARXIV_CATEGORIES,
    hf_limit: int = 10,
    hn_limit: int = 15,
    hn_min_points: int = 30,
    arxiv_limit_per_cat: int = 2,
    iacr_limit: int = 5,
    include_hn: bool = True,
    include_iacr: bool = True,
) -> list[Paper]:
    """Aggregate papers from all configured sources.

    Order in returned list reflects signal priority:
    1. HuggingFace Daily — human-curated AI/ML
    2. Hacker News — community-validated, broad CS coverage
    3. arXiv RSS — chronological fallback, all 28 cs.* categories
    4. IACR ePrint — daily cryptography preprints

    Returns deduplicated list (by arxiv_id). Source failures are logged
    but partial results still returned — never crashes.
    """
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=30)
    try:
        tasks: list = [fetch_huggingface_daily(client=client, limit=hf_limit)]
        labels: list[str] = ["huggingface_daily"]
        if include_hn:
            tasks.append(
                fetch_hackernews_papers(
                    client=client, limit=hn_limit, min_points=hn_min_points
                )
            )
            labels.append("hackernews")
        for cat in arxiv_categories:
            tasks.append(
                fetch_arxiv_rss(cat, client=client, limit=arxiv_limit_per_cat)
            )
            labels.append(cat)
        if include_iacr:
            tasks.append(fetch_iacr_eprint(client=client, limit=iacr_limit))
            labels.append("iacr_eprint")

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_papers: list[Paper] = []
        seen: set[str] = set()
        for source_label, result in zip(labels, results, strict=False):
            if isinstance(result, BaseException):
                log.warning("Source %s failed: %s", source_label, result)
                continue
            for paper in result:
                if paper.arxiv_id in seen:
                    continue
                seen.add(paper.arxiv_id)
                all_papers.append(paper)
        return all_papers
    finally:
        if owns_client:
            await client.aclose()


# Default per-source quotas for select_with_quotas (sums to 10 = daily_limit).
DEFAULT_QUOTAS: dict[str, int] = {
    "huggingface_daily": 4,  # AI curated
    "hackernews": 4,  # broad CS, community-validated
    "iacr_eprint": 1,  # daily crypto
    # Remaining 1 slot fills from overflow (other arxiv RSS) if any
}


def select_with_quotas(
    papers: list[Paper],
    limit: int,
    *,
    quotas: dict[str, int] | None = None,
) -> list[Paper]:
    """Select up to `limit` papers respecting per-source quotas.

    Algorithm:
    1. Take up to `quotas[source]` papers from each priority source
    2. Fill remaining slots from leftovers + overflow (other sources)
       in original order (which is already source-priority).

    This ensures non-AI sources (HN, IACR, arXiv overflow) actually
    reach the LLM stage, instead of being eaten by HuggingFace Daily.
    """
    q = quotas or DEFAULT_QUOTAS
    by_source: dict[str, list[Paper]] = {s: [] for s in q}
    overflow: list[Paper] = []
    for p in papers:
        if p.source in by_source:
            by_source[p.source].append(p)
        else:
            overflow.append(p)

    selected: list[Paper] = []
    leftovers: list[Paper] = []
    for source, quota in q.items():
        bucket = by_source[source]
        selected.extend(bucket[:quota])
        leftovers.extend(bucket[quota:])

    # Fill remaining slots: leftovers from quota'd sources first, then overflow.
    fillers = leftovers + overflow
    while len(selected) < limit and fillers:
        selected.append(fillers.pop(0))

    return selected[:limit]


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
        return datetime(*value[:6], tzinfo=UTC)
    except Exception:
        return None
