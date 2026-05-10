"""Tests for paper ingestion."""

import re

from pytest_httpx import HTTPXMock

from pipeline.ingest import (
    ARXIV_RSS_BASE,
    HF_DAILY_URL,
    HN_SEARCH_URL,
    IACR_RSS_URL,
    fetch_all_sources,
    fetch_arxiv_rss,
    fetch_hackernews_papers,
    fetch_huggingface_daily,
    fetch_iacr_eprint,
    select_with_quotas,
)
from pipeline.models import Paper

HF_RESPONSE = [
    {
        "paper": {
            "id": "2511.12345",
            "title": "Self-Refining Models",
            "authors": [{"name": "Jane Smith"}, {"name": "John Doe"}],
            "summary": "We introduce a two-pass scheme...",
            "publishedAt": "2026-05-09T00:00:00.000Z",
            "upvotes": 42,
        }
    },
    {
        "paper": {
            "id": "2511.99999",
            "title": "Another Paper",
            "authors": [{"name": "Alice"}],
            "summary": "Another abstract.",
            "publishedAt": "2026-05-09T00:00:00.000Z",
            "upvotes": 10,
        }
    },
]


ARXIV_RSS_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
<channel>
  <title>cs.LG updates</title>
  <item>
    <title>Sample Paper Title</title>
    <link>http://arxiv.org/abs/2511.54321v1</link>
    <description>&lt;p&gt;Authors: A. A.&lt;/p&gt;&lt;p&gt;abstract body.&lt;/p&gt;</description>
    <author>A. Author, B. Author</author>
    <pubDate>Fri, 09 May 2026 00:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Second Paper</title>
    <link>http://arxiv.org/abs/2511.00001v2</link>
    <description>&lt;p&gt;Another abstract.&lt;/p&gt;</description>
    <author>Carol</author>
  </item>
</channel>
</rss>"""


async def test_huggingface_daily_parses_papers(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=HF_DAILY_URL, json=HF_RESPONSE)
    papers = await fetch_huggingface_daily(limit=10)
    assert len(papers) == 2
    assert papers[0].arxiv_id == "2511.12345"
    assert papers[0].source == "huggingface_daily"
    assert papers[0].url == "https://arxiv.org/abs/2511.12345"
    assert "Jane Smith" in papers[0].authors
    assert "John Doe" in papers[0].authors


async def test_huggingface_daily_respects_limit(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=HF_DAILY_URL, json=HF_RESPONSE)
    papers = await fetch_huggingface_daily(limit=1)
    assert len(papers) == 1
    assert papers[0].arxiv_id == "2511.12345"


async def test_huggingface_daily_skips_malformed(httpx_mock: HTTPXMock):
    response = [
        {"paper": {"id": "ok.123", "title": "T", "authors": [{"name": "A"}], "summary": "x"}},
        {"paper": {}},  # missing id — should be skipped
        {},  # no paper key
    ]
    httpx_mock.add_response(url=HF_DAILY_URL, json=response)
    papers = await fetch_huggingface_daily()
    assert len(papers) == 1
    assert papers[0].arxiv_id == "ok.123"


async def test_arxiv_rss_parses_entries(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{ARXIV_RSS_BASE}/cs.LG",
        content=ARXIV_RSS_XML.encode(),
    )
    papers = await fetch_arxiv_rss("cs.LG")
    assert len(papers) == 2

    first = papers[0]
    assert first.arxiv_id == "2511.54321"
    assert first.source == "arxiv_rss"
    assert "<p>" not in first.abstract  # HTML stripped
    assert "abstract body" in first.abstract
    assert "A. Author" in first.authors


IACR_RSS_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
<channel>
  <title>Cryptology ePrint Archive</title>
  <item>
    <title>A New Lattice-Based Signature Scheme</title>
    <link>https://eprint.iacr.org/2026/0501</link>
    <description>We propose a new signature scheme.</description>
    <author>Alice, Bob, Carol</author>
    <pubDate>Fri, 09 May 2026 00:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Improved SNARK Construction</title>
    <link>https://eprint.iacr.org/2026/0502</link>
    <description>Reduces proof size by 40%.</description>
    <author>Dave</author>
  </item>
</channel>
</rss>"""


async def test_iacr_eprint_parses_entries(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=IACR_RSS_URL, content=IACR_RSS_XML.encode())
    papers = await fetch_iacr_eprint(limit=10)
    assert len(papers) == 2

    first = papers[0]
    assert first.arxiv_id == "2026/0501"
    assert first.source == "iacr_eprint"
    assert first.url == "https://eprint.iacr.org/2026/0501"
    assert "Alice" in first.authors
    assert first.source_label == "IACR:2026/0501"


async def test_iacr_eprint_respects_limit(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=IACR_RSS_URL, content=IACR_RSS_XML.encode())
    papers = await fetch_iacr_eprint(limit=1)
    assert len(papers) == 1


async def test_fetch_all_sources_includes_iacr(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=HF_DAILY_URL, json=HF_RESPONSE)
    httpx_mock.add_response(
        url=f"{ARXIV_RSS_BASE}/cs.LG", content=ARXIV_RSS_XML.encode()
    )
    httpx_mock.add_response(url=IACR_RSS_URL, content=IACR_RSS_XML.encode())

    papers = await fetch_all_sources(
        arxiv_categories=("cs.LG",),
        hf_limit=10,
        arxiv_limit_per_cat=10,
        iacr_limit=10,
        include_iacr=True,
        include_hn=False,
    )

    sources = {p.source for p in papers}
    assert "huggingface_daily" in sources
    assert "arxiv_rss" in sources
    assert "iacr_eprint" in sources

    iacr_papers = [p for p in papers if p.source == "iacr_eprint"]
    assert len(iacr_papers) == 2


async def test_fetch_all_sources_can_skip_iacr(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=HF_DAILY_URL, json=HF_RESPONSE)
    httpx_mock.add_response(
        url=f"{ARXIV_RSS_BASE}/cs.LG", content=ARXIV_RSS_XML.encode()
    )
    # IACR not mocked — would fail if called

    papers = await fetch_all_sources(
        arxiv_categories=("cs.LG",),
        hf_limit=10,
        arxiv_limit_per_cat=10,
        include_iacr=False,
        include_hn=False,
    )
    assert all(p.source != "iacr_eprint" for p in papers)


async def test_fetch_all_sources_deduplicates_across_sources(httpx_mock: HTTPXMock):
    """If the same arxiv_id appears in HF and arXiv RSS, dedup keeps HF version."""
    # HF returns 2511.54321 (also in arXiv RSS below) + 2511.99999 (HF only)
    hf_with_overlap = [
        {
            "paper": {
                "id": "2511.54321",
                "title": "From HF",
                "authors": [{"name": "Same Paper"}],
                "summary": "HF version",
            }
        },
        {
            "paper": {
                "id": "2511.99999",
                "title": "HF Only",
                "authors": [{"name": "Bob"}],
                "summary": "Only in HF",
            }
        },
    ]
    httpx_mock.add_response(url=HF_DAILY_URL, json=hf_with_overlap)
    httpx_mock.add_response(
        url=f"{ARXIV_RSS_BASE}/cs.LG", content=ARXIV_RSS_XML.encode()
    )

    papers = await fetch_all_sources(
        arxiv_categories=("cs.LG",),
        hf_limit=10,
        arxiv_limit_per_cat=10,
        include_iacr=False,
        include_hn=False,
    )

    ids = [p.arxiv_id for p in papers]
    # 2511.54321 is in both sources but should appear once, from HF (first source)
    assert ids.count("2511.54321") == 1
    assert ids[0] == "2511.54321"  # HF first
    assert papers[0].source == "huggingface_daily"
    # arXiv-only paper from RSS feed should be present
    assert "2511.00001" in ids


async def test_fetch_all_sources_tolerates_one_source_failure(httpx_mock: HTTPXMock):
    """If arXiv RSS fails, HF papers still come through."""
    httpx_mock.add_response(url=HF_DAILY_URL, json=HF_RESPONSE)
    httpx_mock.add_response(url=f"{ARXIV_RSS_BASE}/cs.LG", status_code=500)

    papers = await fetch_all_sources(
        arxiv_categories=("cs.LG",),
        hf_limit=10,
        arxiv_limit_per_cat=5,
        include_iacr=False,
        include_hn=False,
    )
    assert len(papers) == 2  # 2 from HF, 0 from broken arXiv
    assert all(p.source == "huggingface_daily" for p in papers)


async def test_arxiv_rss_strips_version_suffix(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{ARXIV_RSS_BASE}/cs.LG",
        content=ARXIV_RSS_XML.encode(),
    )
    papers = await fetch_arxiv_rss("cs.LG")
    # Second entry has v2 suffix — must be stripped
    assert any(p.arxiv_id == "2511.00001" for p in papers)


# === Hacker News tests ====================================================

HN_SEARCH_RESPONSE = {
    "hits": [
        {
            "url": "https://arxiv.org/abs/2511.12345",
            "title": "Cool paper 1",
            "points": 200,
            "created_at_i": 1700000000,
        },
        {
            "url": "https://github.com/foo/bar",  # not arxiv — skipped
            "title": "Some repo",
            "points": 100,
            "created_at_i": 1700001000,
        },
        {
            "url": "https://arxiv.org/pdf/2511.99999",
            "title": "Cool paper 2",
            "points": 50,
            "created_at_i": 1700002000,
        },
    ]
}

ARXIV_API_RESPONSE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2511.12345v1</id>
    <title>Cool paper 1 — official title</title>
    <summary>This is the abstract of paper 1.</summary>
    <author><name>Alice</name></author>
    <author><name>Bob</name></author>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2511.99999v1</id>
    <title>Cool paper 2 — official title</title>
    <summary>This is the abstract of paper 2.</summary>
    <author><name>Carol</name></author>
  </entry>
</feed>"""


async def test_hackernews_fetches_arxiv_papers(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=re.compile(rf"^{re.escape(HN_SEARCH_URL)}\?"),
        json=HN_SEARCH_RESPONSE,
    )
    httpx_mock.add_response(
        url=re.compile(r"^http://export\.arxiv\.org/api/query\?"),
        content=ARXIV_API_RESPONSE.encode(),
    )

    papers = await fetch_hackernews_papers(min_points=10, limit=10)

    assert len(papers) == 2
    # Sorted by HN points desc — paper with 200 first
    assert papers[0].arxiv_id == "2511.12345"
    assert papers[0].source == "hackernews"
    assert "Alice" in papers[0].authors
    assert papers[1].arxiv_id == "2511.99999"


async def test_hackernews_skips_non_arxiv_urls(httpx_mock: HTTPXMock):
    response = {
        "hits": [
            {"url": "https://github.com/foo", "title": "x", "points": 100, "created_at_i": 1},
            {"url": "https://example.com/blog", "title": "y", "points": 200, "created_at_i": 2},
        ]
    }
    httpx_mock.add_response(
        url=re.compile(rf"^{re.escape(HN_SEARCH_URL)}\?"), json=response
    )
    papers = await fetch_hackernews_papers()
    assert papers == []


# === select_with_quotas tests =============================================


def _paper(arxiv_id: str, source: str) -> Paper:
    return Paper(
        arxiv_id=arxiv_id,
        title=f"Title {arxiv_id}",
        authors=["A"],
        abstract="abs",
        url=f"https://arxiv.org/abs/{arxiv_id}",
        source=source,  # type: ignore
    )


def test_select_with_quotas_respects_per_source_caps():
    papers = (
        [_paper(f"hf.{i}", "huggingface_daily") for i in range(8)]
        + [_paper(f"hn.{i}", "hackernews") for i in range(8)]
        + [_paper(f"ic.{i}", "iacr_eprint") for i in range(3)]
    )
    selected = select_with_quotas(papers, limit=10)
    by_source: dict[str, int] = {}
    for p in selected:
        by_source[p.source] = by_source.get(p.source, 0) + 1
    # Defaults: HF=4, HN=4, IACR=1 = 9 selected. +1 from leftover (HF first
    # in dict-iteration order) → HF=5, HN=4, IACR=1, total=10.
    assert by_source["huggingface_daily"] == 5
    assert by_source["hackernews"] == 4
    assert by_source["iacr_eprint"] == 1
    assert len(selected) == 10


def test_select_with_quotas_falls_back_when_source_thin():
    """If HN has only 1 paper, the spare 3 slots should fill from elsewhere."""
    papers = (
        [_paper(f"hf.{i}", "huggingface_daily") for i in range(10)]
        + [_paper("hn.1", "hackernews")]
        + [_paper("ic.1", "iacr_eprint")]
    )
    selected = select_with_quotas(papers, limit=10)
    by_source: dict[str, int] = {}
    for p in selected:
        by_source[p.source] = by_source.get(p.source, 0) + 1
    # HN had only 1, so HF gets 4 + 3 leftover overflow = 7 (or so)
    assert by_source["hackernews"] == 1
    assert by_source["iacr_eprint"] == 1
    assert by_source["huggingface_daily"] == 8
    assert len(selected) == 10


def test_select_with_quotas_handles_unknown_source():
    """Papers from sources not in quotas (e.g. arxiv_rss) go to overflow."""
    papers = (
        [_paper("hf.1", "huggingface_daily")]
        + [_paper(f"ax.{i}", "arxiv_rss") for i in range(5)]
    )
    selected = select_with_quotas(papers, limit=10)
    # HF: 1 (its quota allowed 4). Arxiv overflow fills rest.
    assert any(p.source == "huggingface_daily" for p in selected)
    arxiv_count = sum(1 for p in selected if p.source == "arxiv_rss")
    assert arxiv_count == 5
