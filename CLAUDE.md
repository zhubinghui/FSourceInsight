# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FSourceInsight is a French tech news aggregator web application that crawls news from French sources (especially Grenoble area), processes them with configurable LLMs (translation, summarization, NER, sentiment analysis), stores in MySQL, and provides a web interface with daily email digests.

## Tech Stack

- **Backend**: Python 3.12 + Flask + SQLAlchemy + Alembic
- **Task Queue**: Celery + Redis (3 queues: crawl, llm, email)
- **LLM**: LiteLLM for multi-provider routing (OpenAI, Anthropic, etc.)
- **Frontend**: Jinja2 + HTMX + Bootstrap 5
- **Database**: MySQL 8.0 (utf8mb4)
- **Deployment**: Docker Compose (web, worker, beat, redis, mysql, nginx)

## Common Commands

```bash
# Start all services
docker-compose up -d

# Run database migrations
flask db upgrade

# Create a new migration after model changes
flask db migrate -m "description"

# Seed initial data (run in order)
python scripts/seed_sources.py
python scripts/seed_companies.py
python scripts/seed_categories.py
python scripts/seed_llm_configs.py

# Manual crawl (all sources or specific)
python scripts/run_crawl.py
python scripts/run_crawl.py -s usine-digitale
python scripts/run_crawl.py --list

# Manual LLM processing
python scripts/run_llm_process.py -n 10        # Process 10 unprocessed articles
python scripts/run_llm_process.py -a 42         # Process specific article
python scripts/run_llm_process.py --dry-run     # Preview without processing

# Run tests
pytest
pytest tests/test_crawlers/ -v

# Install dependencies (development)
pip install -r requirements/dev.txt
```

## Architecture

### Data Flow
```
News Sources → Crawlers → MySQL → LLM Pipeline → Translated/Enriched Articles → Web UI / Email
```

### Key Modules

- `app/crawlers/` — BaseCrawler → RSSCrawler/HTMLCrawler → source-specific parsers. Registry pattern maps source slugs to crawler classes via `@register_crawler` decorator.
- `app/llm/client.py` — LLMClient facade using LiteLLM. Config stored in DB (`llm_config` table), not code. Each task (translate/summarize/ner/sentiment/classify) can use a different model.
- `app/llm/tasks.py` — Celery task chain: translate → summarize → NER → sentiment → classify. Rate-limited to 10/min.
- `app/email/` — Daily digest builder + keyword alert matching. Runs via Celery Beat at 7:00 AM Paris time.
- `app/web/views/` — Six Flask Blueprints: news, company, admin, subscription, auth, api.
- `app/api/v1/routes.py` — REST API for news/companies/sources (JSON, CSRF-exempt).
- `app/models/` — SQLAlchemy models. Article is the central model; ArticleCompany carries sentiment data.

### Adding a New News Source

1. Create `app/crawlers/sources/new_source.py`
2. Subclass `RSSCrawler` (if RSS) or `HTMLCrawler` (if scraping)
3. Decorate with `@register_crawler('source-slug')`
4. Add import in `app/crawlers/sources/__init__.py`
5. Add entry in `scripts/seed_sources.py` and run it

### LLM Provider Configuration

LLM config lives in the `llm_config` database table. API keys are stored as environment variable names (never raw keys in DB). To switch providers, update the DB record via Admin UI (`/admin/llm-config`) — no code changes needed.

### LLM Architecture

- `app/llm/client.py` — LLMClient facade with caching, usage tracking, and circuit breaker
- `app/llm/prompts.py` — All prompt templates centralized here. Modify prompts without touching client logic.
- `app/llm/circuit_breaker.py` — Per-provider circuit breaker (Redis-backed). Opens after 5 failures, recovers after 5 min. Falls back to alternative provider automatically.
- Admin UI at `/admin/llm-config` for CRUD; `/admin/llm-usage` for cost/token dashboard.

### Web Interface

- HTMX-powered live search on news and company list pages (no full reload)
- News filtering: source, category, company, date range, keyword search — all via HTMX
- Company detail: Chart.js stacked bar chart for sentiment trend over time
- Admin: full CRUD for sources, companies, LLM configs; company merge tool; crawl-now button
- Auth: Flask-Login with `@login_required` on admin routes; first-time `/auth/setup` creates admin

### REST API

Base URL: `/api/v1/`. CSRF-exempt. Returns JSON.
- `GET /api/v1/news` — paginated articles (filter: source_id, company_id, q, date_from, date_to)
- `GET /api/v1/news/<id>` — full article with companies and categories
- `GET /api/v1/companies` — paginated companies (filter: q, sector, grenoble)
- `GET /api/v1/companies/<slug>` — company with recent articles
- `GET /api/v1/sources` — active news sources

### Monitoring & Health

- `GET /health` — basic health (DB + Redis connectivity), returns 200/503
- `GET /health/detail` — detailed: crawl stats, pipeline queue, LLM failure rate
- Sentry integration: set `SENTRY_DSN` env var to enable (Flask + Celery + SQLAlchemy)
- Structured logging: `LOG_FORMAT=json` for production, rotating file handler
- Crawl health check: Celery Beat task every 6h, logs warnings for stale/failing sources
- LLM daily budget: `LLM_DAILY_BUDGET_USD` env var, checked before each API call

### Production Deployment

```bash
# Production with resource limits and SSL-ready nginx
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# MySQL backup (set up as daily cron)
./scripts/backup_mysql.sh
```
