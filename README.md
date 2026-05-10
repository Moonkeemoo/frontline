# Frontline

> Свіжі AI/ML дослідження українською — TL;DR, контекст для UA IT, лінк на оригінал.

Автоматичний агрегатор, що збирає свіжі дослідження з arXiv та HuggingFace Papers, генерує українською мовою структуровані резюме (з акцентом на «що це означає для UA IT-екосистеми»), і публікує на сайт + у Telegram-канал.

## Статус

**Phase 0 — scaffold.** Pipeline не запущено публічно. Збираємо prompts, glossary, базову структуру.

## Roadmap

- **Phase 1** (MVP) — AI/ML research: arXiv `cs.LG`/`cs.AI`/`cs.CL`/`cs.CV` + HuggingFace Papers + OpenReview. Сайт + Telegram-канал.
- **Phase 2** — вся CS: + USENIX, IACR, ACL Anthology, CVF.
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

## Local dev (TBD)

```bash
# coming after pipeline modules land
uv sync
cp .env.example .env  # додати ANTHROPIC_API_KEY
uv run python -m pipeline.run --dry-run
```

## Принципи

- **Англомовні терміни залишаються англійською**, коли немає усталеного UA-аналога. Glossary — джерело істини.
- **Auto-publish + community feedback.** Помилки виправляються через issues / форму на сайті.
- **Triple-LLM gate.** Generate → critique → publish/queue. Краще тиша, ніж лажа.
- **Local-first.** Усе можна прогнати локально перед deploy.

## Ліцензія

TBD.
