# Frontline — Architecture (Phase 1)

## Pipeline overview

```
                    ┌──────────────────────────┐
                    │  GitHub Actions cron     │
                    │  06:00 UTC daily         │
                    └──────────────┬───────────┘
                                   │
                                   ▼
   ┌─────────────────────────────────────────────────────────────┐
   │  STAGE 1: INGEST                                            │
   │  - HuggingFace Papers daily API → top ~10                   │
   │  - Fallback: arXiv RSS (cs.LG/AI/CL/CV) sorted by recency   │
   │  - Filter: skip if arxiv_id already in published log        │
   └─────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
   ┌─────────────────────────────────────────────────────────────┐
   │  STAGE 2: GENERATE                                          │
   │  Model: claude-sonnet-4-6 (configurable via env)            │
   │  Input: paper metadata + abstract + glossary.yaml           │
   │  Prompt: prompts/generate.md                                │
   │  Output: structured JSON (title_ua, tldr_ua, ...)           │
   └─────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
   ┌─────────────────────────────────────────────────────────────┐
   │  STAGE 3: CRITIQUE                                          │
   │  Model: claude-opus-4-7 (different from generator)          │
   │  Input: original abstract + summary_ua + glossary           │
   │  Prompt: prompts/critique.md                                │
   │  Output: {verdict, issues[], recommendation}                │
   └─────────────────────────────────────────────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
        verdict=ok        verdict=needs_review   verdict=reject
              │                    │                    │
              ▼                    ▼                    ▼
   ┌──────────────────┐  ┌─────────────────┐  ┌────────────────┐
   │  STAGE 4a:       │  │  STAGE 4b:      │  │  STAGE 4c:     │
   │  PUBLISH         │  │  QUEUE          │  │  REJECT        │
   │  - markdown to   │  │  - .runs/queue/ │  │  - log only,   │
   │    site/content/ │  │  - email alert  │  │    no email    │
   │  - Telegram post │  │    weekly if    │  │  - issue body  │
   │  - update        │  │    backlog>5    │  │    saved for   │
   │    published log │  │                 │  │    diagnosis   │
   └──────────────────┘  └─────────────────┘  └────────────────┘
```

## Reliability gates

- **Cost cap:** якщо денний spend > `FRONTLINE_DAILY_COST_CAP_USD` (default $1) — pipeline зупиняється на половині, лог + email.
- **Empty-day fallback:** якщо за 7 днів нічого не опубліковано (всі rejects) — alert.
- **Action failure:** GitHub Actions auto-retries × 2; після 3 фейлів підряд — auto-issue в репо.
- **Glossary diff:** будь-яка зміна `pipeline/glossary.yaml` = git commit = можна reverse.

## Module boundaries (Phase 1)

```
pipeline/
├── ingest.py       # fetch_huggingface_daily(), fetch_arxiv_recent(); pure functions, async httpx
├── generate.py     # async generate_summary(paper, glossary, prompt) -> SummaryUA
├── critique.py     # async critique_summary(paper, summary, glossary, prompt) -> CritiqueResult
├── publish.py      # write_markdown(summary), post_telegram(summary)
├── models.py       # pydantic: Paper, SummaryUA, CritiqueResult, Verdict
├── glossary.py     # load(), format_for_prompt()
├── log.py          # PublishedLog: avoid re-processing
└── run.py          # orchestrator: ingest -> for each paper: generate -> critique -> publish/queue
```

Кожен модуль має 1 чітку відповідальність + тести в `tests/`.

## Data contracts

### Paper (input)
```python
class Paper(BaseModel):
    arxiv_id: str        # "2511.12345"
    title: str
    authors: list[str]
    abstract: str
    url: str             # https://arxiv.org/abs/2511.12345
    submitted_at: datetime
    source: Literal["huggingface_daily", "arxiv_rss"]
```

### SummaryUA (generate output)
```python
class SummaryUA(BaseModel):
    title_ua: str
    tldr_ua: str
    what_they_did_ua: str
    why_matters_ua: str
    limitations_ua: list[str]
    tags: list[str]
    estimated_read_min: int
    notes: str | None = None
```

### CritiqueResult
```python
class CritiqueResult(BaseModel):
    verdict: Literal["ok", "needs_review", "reject"]
    issues: list[Issue]
    recommendation: Literal["publish", "queue_for_review", "regenerate"]
    regenerate_feedback: str | None
```

## Outputs

- **Markdown post:** `site/content/posts/2026-05-09-self-refining-models.md` (Astro-friendly frontmatter + body)
- **Telegram post:** ~1500 chars, lead з TL;DR, лінк на сайт + arXiv
- **Published log:** `pipeline/data/published.jsonl` — append-only, для idempotency

## Site (Phase 1.5+)

Astro static site, deployed to Cloudflare Pages.
Build triggered on git push to `main`.
RSS auto-generated.
Forma «повідомити про неточність» — проста Cloudflare Form або external (Tally).
