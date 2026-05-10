# Frontline

> Свіжі AI/ML дослідження українською — TL;DR, контекст для UA IT, лінк на оригінал.

Автоматичний агрегатор, що збирає свіжі дослідження з arXiv та HuggingFace Papers, генерує українською мовою структуровані резюме (з акцентом на «що це означає для UA IT-екосистеми»), і публікує на сайт + у Telegram-канал.

## Статус

**Phase 0 — scaffold.** Pipeline не запущено публічно. Збираємо prompts, glossary, базову структуру.

## Roadmap

- ✅ **Phase 1** (MVP) — AI/ML research: arXiv `cs.LG`/`cs.AI`/`cs.CL`/`cs.CV` + HuggingFace Papers. Сайт + Telegram.
- 🚧 **Phase 2** — вся CS: ✅ 28 arXiv-категорій (AI/ML, systems, SE, security, theory, robotics, HCI, …) + ✅ IACR ePrint (crypto). USENIX/ACL/CVF/OpenReview — потребують batch-mode (раз на конференцію), відкладено.
- **Phase 3** — + research-блоги корпорацій (Anthropic/Google/Meta/Apple/MSR) + великі OSS-релізи.
- **Phase 4** — + regulatory (EU AI Act) + open-data ініціативи.

## Архітектура (Phase 1)

```
HF Papers / arXiv  →  generate (Sonnet)  →  critique (Opus)  →  publish/queue
                              ↓                      ↓
                         glossary.yaml         glossary.yaml
                              ↓                      ↓
                         prompts/generate.md   prompts/critique.md
```

Деталі — `docs/ARCHITECTURE.md`.

## Local dev

```bash
uv sync                                    # install deps + create venv
cp .env.example .env                       # додати ANTHROPIC_API_KEY (мін.)
uv run python -m pipeline.run --dry-run    # прогнати без публікації
uv run python -m pytest                    # запустити тести (47/47)
uv run ruff check pipeline/ tests/         # лінт
```

Для повного запуску з публікацією на сайт + Telegram потрібні також:
- `TELEGRAM_BOT_TOKEN` (від @BotFather)
- `TELEGRAM_CHANNEL_ID` (`@your_channel` або numeric `-100...`)

## Deploy

### Pipeline (GitHub Actions)

- **Daily cron** `06:00 UTC` (`.github/workflows/daily.yml`) — fetches HF Papers, generates+critiques, commits new posts back to repo
- **CI on PR** (`.github/workflows/ci.yml`) — lint + tests

Required GitHub secrets: `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`.

При фейлі pipeline-у автоматично створюється issue з лінком на failed run.

### Site (Cloudflare Pages)

```bash
cd site && npm run build  # вивід у site/dist/
```

Cloudflare Pages → Connect to Git → repo `Moonkeemoo/frontline`:
- **Build command:** `cd site && npm install && npm run build`
- **Output directory:** `site/dist`
- **Root directory:** `/` (project root, not `site/`)

### Voting backend (Cloudflare KV)

Голоси зберігаються в Cloudflare KV namespace через Pages Functions у `site/functions/api/`.

**One-time setup:**
1. Cloudflare Dashboard → Workers & Pages → KV → Create namespace `FRONTLINE_VOTES`
2. Pages project → Settings → Functions → KV namespace bindings:
   - Variable name: `FRONTLINE_VOTES`
   - KV namespace: оберіть створений
3. Redeploy (Pages → Deployments → Retry build)

Без цього кроку сайт працює, але голосування fallback-ить на localStorage (per-device only). API endpoints повертають `configured: false`.

Дедуплікація: SHA-256(IP + User-Agent), TTL 1 рік. Free tier KV (100k reads + 1k writes/day) комфортно покриває старт.

## Принципи

- **Англомовні терміни залишаються англійською**, коли немає усталеного UA-аналога. Glossary — джерело істини.
- **Auto-publish + community feedback.** Помилки виправляються через issues / форму на сайті.
- **Triple-LLM gate.** Generate → critique → publish/queue. Краще тиша, ніж лажа.
- **Local-first.** Усе можна прогнати локально перед deploy.

## Ліцензія

TBD.
