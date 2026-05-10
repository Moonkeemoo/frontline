"""Regenerate existing post markdown files using the current prompts.

Reads each .md file's frontmatter, fetches the original abstract from
arXiv API, runs generate + critique pipeline with the LATEST prompts,
overwrites the file. Original publish_date is preserved.

Usage:
    uv run python -m pipeline.regenerate              # all posts
    uv run python -m pipeline.regenerate --paper ID   # one paper
    uv run python -m pipeline.regenerate --dry-run    # preview only

IACR-sourced posts are skipped (no batch API for historical eprints).
"""

import argparse
import asyncio
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

import feedparser
import frontmatter
import httpx
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

from .critique import critique_summary
from .generate import generate_summary
from .glossary import Glossary
from .ingest import ARXIV_API_URL
from .models import Paper
from .publish import render_post_markdown

log = logging.getLogger(__name__)

ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,5}$")


async def fetch_arxiv_paper(
    arxiv_id: str, client: httpx.AsyncClient
) -> Paper | None:
    """Fetch with rate-limit-aware retry. arXiv asks for ≤1 req/3s."""
    for attempt in range(4):
        if attempt > 0:
            await asyncio.sleep(5 * attempt)  # 5, 10, 15s backoff
        resp = await client.get(
            ARXIV_API_URL,
            params={"id_list": arxiv_id, "max_results": "1"},
        )
        if resp.status_code == 429:
            log.warning("arXiv 429 for %s, backing off (attempt %d)", arxiv_id, attempt + 1)
            continue
        resp.raise_for_status()
        break
    else:
        return None
    feed = feedparser.parse(resp.text)
    if not feed.entries:
        return None
    entry = feed.entries[0]

    title = re.sub(r"\s+", " ", entry.get("title", "")).strip()
    abstract = re.sub(r"\s+", " ", entry.get("summary", "")).strip()
    authors = [
        a.get("name", "")
        for a in entry.get("authors", [])
        if isinstance(a, dict) and a.get("name")
    ]
    return Paper(
        arxiv_id=arxiv_id,
        title=title,
        authors=authors or ["Unknown"],
        abstract=abstract,
        url=f"https://arxiv.org/abs/{arxiv_id}",
        source="arxiv_rss",  # placeholder; original source preserved by caller
    )


async def regenerate_one(
    md_path: Path,
    *,
    glossary: Glossary,
    client: Any,
    http_client: httpx.AsyncClient,
    dry_run: bool = False,
) -> dict:
    post = frontmatter.load(md_path)
    arxiv_id = str(post.metadata.get("arxiv_id", "")).strip()
    source = str(post.metadata.get("source", "arxiv_rss"))
    publish_date = post.metadata.get("publish_date")

    if source == "iacr_eprint":
        return {"skipped": True, "reason": "IACR (no batch API for historical)"}

    if not ARXIV_ID_RE.match(arxiv_id):
        return {"skipped": True, "reason": f"unrecognized arxiv_id: {arxiv_id!r}"}

    paper = await fetch_arxiv_paper(arxiv_id, http_client)
    if not paper:
        return {"skipped": True, "reason": "arXiv API returned empty"}
    paper.source = source  # preserve original

    gen = await generate_summary(paper, glossary=glossary, client=client)
    crit = await critique_summary(
        paper, gen.summary, glossary=glossary, client=client
    )
    cost = gen.cost_usd + crit.cost_usd

    rec = crit.critique.recommendation
    if rec == "regenerate":
        return {
            "skipped": True,
            "reason": f"critique rejected (verdict={crit.critique.verdict})",
            "cost_usd": cost,
        }

    if not dry_run:
        new_md = render_post_markdown(paper, gen.summary)
        new_post = frontmatter.loads(new_md)
        if publish_date:
            new_post["publish_date"] = publish_date
        md_path.write_text(frontmatter.dumps(new_post), encoding="utf-8")

    return {
        "ok": True,
        "verdict": crit.critique.verdict,
        "recommendation": rec,
        "issues": len(crit.critique.issues),
        "cost_usd": cost,
    }


def main(argv: list[str] | None = None) -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(prog="frontline-regenerate")
    parser.add_argument(
        "--posts-dir", type=Path, default=Path("site/src/content/posts")
    )
    parser.add_argument(
        "--paper", help="Regenerate one paper by arxiv_id substring match"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 1

    files = sorted(args.posts_dir.glob("*.md"))
    if args.paper:
        files = [f for f in files if args.paper in f.name]
        if not files:
            print(f"No file matching {args.paper!r}", file=sys.stderr)
            return 1

    print(f"Found {len(files)} posts to process")

    async def runner() -> dict:
        glossary = Glossary.load()
        client = AsyncAnthropic()
        stats = {"ok": 0, "queued": 0, "skipped": 0, "cost": 0.0}
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as http:
            for i, path in enumerate(files):
                if i > 0:
                    await asyncio.sleep(3.5)  # arXiv rate-limit etiquette
                short = path.name[:80]
                try:
                    result = await regenerate_one(
                        path,
                        glossary=glossary,
                        client=client,
                        http_client=http,
                        dry_run=args.dry_run,
                    )
                except Exception as e:
                    log.exception("Failed %s", path.name)
                    print(f"  ERR  {short}: {e}")
                    continue

                stats["cost"] += result.get("cost_usd", 0) or 0
                if result.get("skipped"):
                    print(f"  SKIP {short}: {result['reason']}")
                    stats["skipped"] += 1
                elif result.get("recommendation") == "queue_for_review":
                    print(
                        f"  QUEUE {short}: {result['issues']} issues "
                        f"(overwrote anyway; review at /queue/ vibes)"
                    )
                    stats["queued"] += 1
                else:
                    print(f"  OK   {short}")
                    stats["ok"] += 1
        return stats

    stats = asyncio.run(runner())

    print()
    print("=== Summary ===")
    print(f"  Regenerated (clean): {stats['ok']}")
    print(f"  Regenerated (queue): {stats['queued']}")
    print(f"  Skipped:             {stats['skipped']}")
    print(f"  Total cost:          ${stats['cost']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
