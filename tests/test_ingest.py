"""Tests for paper ingestion."""

from pytest_httpx import HTTPXMock

from pipeline.ingest import (
    ARXIV_RSS_BASE,
    HF_DAILY_URL,
    fetch_all_sources,
    fetch_arxiv_rss,
    fetch_huggingface_daily,
)

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
        arxiv_categories=("cs.LG",), hf_limit=10, arxiv_limit_per_cat=10
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
        arxiv_categories=("cs.LG",), hf_limit=10, arxiv_limit_per_cat=5
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
