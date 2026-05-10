"""Orchestrator: ingest → generate → critique → publish/queue/reject."""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic
from dotenv import load_dotenv

from .critique import DEFAULT_MODEL as DEFAULT_CRITIQUE_MODEL
from .critique import critique_summary
from .generate import DEFAULT_MODEL as DEFAULT_GENERATE_MODEL
from .generate import generate_summary
from .glossary import Glossary
from .ingest import fetch_huggingface_daily
from .log import PublishedLog
from .models import PipelineResult
from .publish import post_to_telegram, render_telegram_message, write_post

log = logging.getLogger(__name__)


async def run_pipeline(
    *,
    output_dir: Path,
    queue_dir: Path,
    log_path: Path,
    daily_limit: int = 10,
    cost_cap_usd: float = 1.0,
    generate_model: str = DEFAULT_GENERATE_MODEL,
    critique_model: str = DEFAULT_CRITIQUE_MODEL,
    dry_run: bool = False,
    telegram_bot_token: str | None = None,
    telegram_channel_id: str | None = None,
    site_url_template: str | None = None,
    client: Any | None = None,
) -> dict:
    """Run end-to-end pipeline. Returns stats dict."""
    glossary = Glossary.load()
    client = client or AsyncAnthropic()
    pub_log = PublishedLog(log_path)

    papers = await fetch_huggingface_daily(limit=daily_limit)
    log.info("Fetched %d papers from HuggingFace daily", len(papers))

    fresh = [p for p in papers if not pub_log.already_seen(p.arxiv_id)]
    log.info("%d are new (not in log)", len(fresh))

    stats: dict[str, Any] = {
        "fetched": len(papers),
        "fresh": len(fresh),
        "published": 0,
        "queued": 0,
        "rejected": 0,
        "errors": 0,
        "total_cost_usd": 0.0,
    }

    for paper in fresh:
        if stats["total_cost_usd"] >= cost_cap_usd:
            log.warning(
                "Cost cap reached: $%.4f >= $%.4f. Stopping early.",
                stats["total_cost_usd"], cost_cap_usd,
            )
            stats["cost_cap_hit"] = True
            break

        result = PipelineResult(paper=paper)
        post_path: Path | None = None

        try:
            log.info("Processing %s: %s", paper.arxiv_id, paper.title[:60])

            gen = await generate_summary(
                paper, glossary=glossary, client=client, model=generate_model
            )
            result.summary = gen.summary
            result.cost_usd += gen.cost_usd
            stats["total_cost_usd"] += gen.cost_usd

            crit = await critique_summary(
                paper, gen.summary, glossary=glossary, client=client, model=critique_model
            )
            result.critique = crit.critique
            result.cost_usd += crit.cost_usd
            stats["total_cost_usd"] += crit.cost_usd

            log.info(
                "  → verdict=%s recommendation=%s cost=$%.4f",
                crit.critique.verdict, crit.critique.recommendation, result.cost_usd,
            )

            if crit.critique.recommendation == "publish":
                if not dry_run:
                    post_path = write_post(paper, gen.summary, output_dir=output_dir)
                    if telegram_bot_token and telegram_channel_id:
                        site_url = (
                            site_url_template.format(slug=post_path.stem)
                            if site_url_template else None
                        )
                        msg = render_telegram_message(paper, gen.summary, site_url=site_url)
                        await post_to_telegram(
                            msg,
                            bot_token=telegram_bot_token,
                            channel_id=telegram_channel_id,
                        )
                stats["published"] += 1
            elif crit.critique.recommendation == "queue_for_review":
                if not dry_run:
                    post_path = write_post(paper, gen.summary, output_dir=queue_dir)
                stats["queued"] += 1
            else:  # regenerate / reject
                stats["rejected"] += 1

            pub_log.record(result, post_path=post_path)

        except Exception as e:
            log.exception("Error processing %s", paper.arxiv_id)
            result.error = str(e)
            stats["errors"] += 1
            pub_log.record(result)

    return stats


def main(argv: list[str] | None = None) -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(prog="frontline", description="Frontline pipeline")
    parser.add_argument("--output-dir", type=Path, default=Path("site/src/content/posts"))
    parser.add_argument("--queue-dir", type=Path, default=Path(".runs/queue"))
    parser.add_argument(
        "--log-path", type=Path, default=Path("pipeline/data/published.jsonl")
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.getenv("FRONTLINE_DAILY_PAPER_LIMIT", "10")),
    )
    parser.add_argument(
        "--cost-cap",
        type=float,
        default=float(os.getenv("FRONTLINE_DAILY_COST_CAP_USD", "1.0")),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=os.getenv("FRONTLINE_DRY_RUN") == "true",
    )
    parser.add_argument(
        "--generate-model",
        default=os.getenv("FRONTLINE_MODEL_GENERATE", DEFAULT_GENERATE_MODEL),
    )
    parser.add_argument(
        "--critique-model",
        default=os.getenv("FRONTLINE_MODEL_CRITIQUE", DEFAULT_CRITIQUE_MODEL),
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set in env", file=sys.stderr)
        return 1

    stats = asyncio.run(
        run_pipeline(
            output_dir=args.output_dir,
            queue_dir=args.queue_dir,
            log_path=args.log_path,
            daily_limit=args.limit,
            cost_cap_usd=args.cost_cap,
            generate_model=args.generate_model,
            critique_model=args.critique_model,
            dry_run=args.dry_run,
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            telegram_channel_id=os.getenv("TELEGRAM_CHANNEL_ID"),
        )
    )

    print("\n=== Pipeline complete ===")
    for k, v in stats.items():
        formatted = f"${v:.4f}" if isinstance(v, float) and "cost" in k else v
        print(f"  {k}: {formatted}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
