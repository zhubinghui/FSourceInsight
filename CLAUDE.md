# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FSourceInsight is a French tech news aggregator focused on the Grenoble/AURA tech ecosystem. It crawls 15+ French news sources, processes articles through a multi-provider LLM pipeline (translation, summarization, NER, sentiment analysis, classification, insight generation), stores results in MySQL, and serves a web interface with daily email digests.

## Tech Stack

- **Backend**: Python 3.12 + Flask + SQLAlchemy + Alembic
- **Task Queue**: Celery + Redis (3 queues: crawl, llm, email)
- **LLM**: LiteLLM for multi-provider routing (DeepSeek, OpenAI, Anthropic)
- **Frontend**: Jinja2 + HTMX + Bootstrap 5
- **Database**: MySQL 8.0 (utf8mb4)
- **Deployment**: Docker Compose (6 services: web, worker, beat, redis, mysql, nginx)

## Common Commands

All commands run inside Docker unless noted. For local dev, the web container mounts the source directory so code changes take effect on restart.

```bash
# Start services (dev)
docker compose up -d

# Start services (production — no source mount, resource limits, nginx SSL-ready)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Database migrations
docker compose exec web flask db upgrade
docker compose exec web flask db migrate -m "description"

# Seed data (must run in order on fresh DB)
docker compose exec web python scripts/seed_sources.py
docker compose exec web python scripts/seed_companies.py
docker compose exec web python scripts/seed_categories.py
docker compose exec web python scripts/seed_llm_configs.py
docker compose exec web python scripts/seed_ecosystem.py
docker compose exec web python scripts/seed_grenoble_ecosystem.py

# Manual crawl
docker compose exec web python scripts/run_crawl.py --list
docker compose exec web python scripts/run_crawl.py -s frenchweb

# Manual LLM processing
docker compose exec web python scripts/run_llm_process.py -n 10
docker compose exec web python scripts/run_llm_process.py -a 42
docker compose exec web python scripts/run_llm_process.py --dry-run

# Tests (install dev deps first: pip install -r requirements/dev.txt)
pytest
pytest tests/test_crawlers/ -v

# View logs
docker compose logs -f worker
docker compose logs -f beat
```

## Architecture

### Data Flow

```
News Sources → Crawlers → MySQL → LLM Pipeline → Enriched Articles → Web UI / Email Digest
```

### Mixed LLM Provider Strategy

Cost-optimized routing across providers — configured in DB (`llm_config` table), not code:

- **DeepSeek** (cheapest): translate, digest, summarize, sentiment
- **OpenAI gpt-5.4-mini**: NER, classify, insight (needs structured JSON output / deep analysis)
- **OpenAI gpt-5.4-nano**: fallback for all simple tasks when primary provider is down
- **Anthropic Claude**: disabled premium option, enable via Admin UI

`LLMClient._get_config()` selects the cheapest active provider for each task type. Circuit breaker (`app/llm/circuit_breaker.py`) auto-opens after 5 consecutive failures per provider, recovers after 5 min. Fallback to next cheapest provider is automatic.

LLM config is managed via Admin UI (`/admin/llm-config`). API keys are stored as env var names in DB (e.g., `DEEPSEEK_API_KEY`), never raw keys.

### LLM Pipeline Per Article

Executed by `process_article_llm` Celery task (rate-limited 10/min):

1. **Title translation** (fr→zh, fr→en) — DeepSeek
2. **Content digest** (zh, en) — DeepSeek — restructured rewrite, not literal translation
3. **Summaries** (fr, zh, en) — DeepSeek
4. **Company NER** — OpenAI — returns JSON with company names, mentions, is_primary
5. **Sentiment analysis** per extracted company — DeepSeek
6. **Category classification + highlight detection** — OpenAI — local_research/investment/local_event
7. **Strategic insight** (zh, en) — OpenAI

All prompts are in `app/llm/prompts.py`. Responses cached in Redis (7 days). Usage/cost logged to `llm_usage_log` table.

### Crawler System

Registry pattern: `@register_crawler('source-slug')` in `app/crawlers/sources/*.py`. Base classes `RSSCrawler` and `HTMLCrawler` handle fetching; subclasses customize parsing. `discover_crawlers()` imports all source modules to trigger registration.

### Celery Configuration

`celery_app.py` — three queues (crawl, llm, email) with explicit task routing. Task modules must be in the `include` list or they won't be discovered by workers. Beat schedule: crawl check every 60s, digest at 7:00 AM Paris, health check every 6h.

### Key Design Decisions

- **LLM config in DB, not code** — switch providers/models from Admin UI without deploys
- **`response_format: {"type": "json_object"}`** used for NER/sentiment/classify — DeepSeek sometimes wraps JSON in markdown code blocks, so `LLMClient._extract_json()` strips them
- **`_link_companies` deduplication** — checks both in-memory set and DB to prevent duplicate `article_company` rows from partial retry
- **Docker port mapping** — dev uses non-standard ports (8001/8080/6380) to avoid conflicts; prod override resets nginx to 80/443 and hides internal service ports

### Adding a New News Source

1. Create `app/crawlers/sources/new_source.py`
2. Subclass `RSSCrawler` or `HTMLCrawler`, decorate with `@register_crawler('slug')`
3. Add import in `app/crawlers/sources/__init__.py`
4. Add entry in `scripts/seed_sources.py` and run it

## Implementation Discipline

When executing a written implementation plan (e.g., a deployment in `docs/superpowers/specs/`):

- If reality diverges from the plan — a step fails, a precondition turns out wrong, the environment differs from what the spec assumed — **update the plan first, then act**.
- The plan is the source of truth for what we're doing and why. A plan that no longer matches what's happening is worse than no plan.
- Specifically: edit the relevant spec/plan file in `docs/superpowers/specs/` (or the in-session task list) to record the change and the reason, then continue. Don't silently work around the discrepancy.

### Production Deployment

```bash
# One-command deployment on fresh Ubuntu/Debian server
sudo ./scripts/deploy.sh

# Or manually:
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose exec web flask db upgrade
# Then seed scripts, create admin at /auth/setup

# MySQL backup (daily cron at 2 AM)
./scripts/backup_mysql.sh
```

### Monitoring

- `GET /health` — DB + Redis check (200/503)
- `GET /health/detail` — crawl stats, pipeline queue depth, LLM failure rate
- Admin dashboard at `/admin` — article counts, today's LLM cost, crawl logs
- `LLM_DAILY_BUDGET_USD` env var caps daily LLM spend
- Optional Sentry: set `SENTRY_DSN` env var
