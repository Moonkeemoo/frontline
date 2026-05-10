"""Append-only log of pipeline outcomes — used for idempotency and audit."""

import json
from datetime import datetime, timezone
from pathlib import Path

from .models import PipelineResult


class PublishedLog:
    """Append-only JSONL log keyed by arxiv_id."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def already_seen(self, arxiv_id: str) -> bool:
        if not self.path.exists():
            return False
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("arxiv_id") == arxiv_id:
                return True
        return False

    def record(self, result: PipelineResult, *, post_path: Path | None = None) -> None:
        entry = {
            "arxiv_id": result.paper.arxiv_id,
            "title": result.paper.title,
            "verdict": result.critique.verdict if result.critique else None,
            "recommendation": (
                result.critique.recommendation if result.critique else None
            ),
            "published": result.published,
            "logged_at": datetime.now(timezone.utc).isoformat(),
            "post_path": str(post_path) if post_path else None,
            "cost_usd": result.cost_usd,
            "error": result.error,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
