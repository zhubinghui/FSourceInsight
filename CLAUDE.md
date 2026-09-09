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

Routing (`app/llm/routing.py`) orders assigned configs before defaults, then `role` (primary before fallback), `priority` (lower first), input cost and ID. Open circuits are skipped, including defaults. Each public request makes at most 3 provider attempts, with LiteLLM retries disabled and a 60-second per-request timeout. These are not an article-wide deadline or concurrent hard budget.

The strategy above describes **fresh seed defaults**. Migration `d472ac9e6102` adds compatible role/priority defaults without rewriting existing tasks or provider choices; existing installations need explicit Admin edits to adopt a new primary/fallback policy. `company_analysis` is a separate usage/contract task, inheriting insight routing only if it has no explicit assignment. Circuit breaker Redis failure recovery and single-probe half-open behavior still require hardening.

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

All prompts are in `app/llm/prompts.py`. The shared Celery/CLI pipeline (`app/llm/pipeline.py`) takes a read-only snapshot, collects model results without business writes, then applies article/company/category changes in one transaction. Only-title/empty-body articles do not generate deep insights. Company refresh happens after article commit and is currently best-effort, not an outbox.

Responses are cached in Redis for 7 days, keyed by complete effective messages, prompt/contract versions, provider/model/endpoint and generation parameters. Only validated responses are cached; malformed JSON and truncated/refused output are paid failures, not fabricated empty results. Usage/cost is committed independently to `llm_usage_log`; never call the client while holding flushed business write locks. Unknown token/cost and crash windows still need M3 reservations/reconciliation.

### Crawler System

Registry pattern: `@register_crawler('source-slug')` in `app/crawlers/sources/*.py`. Base classes `RSSCrawler` and `HTMLCrawler` handle fetching; subclasses customize parsing. `discover_crawlers()` imports all source modules to trigger registration.

M1.1 introduces `validate_recipe()` in `app/crawlers/schema.py` and immutable output contracts in `app/crawlers/contracts.py`. Recipes are bounded declarative data, not executable code or permission to fetch/publish. Results retain content level, language, evidence and UTC time without inventing missing dates. See `docs/audits/2026-09-06-m11-contracts.md` for supported fields and limits.

M1.2 adds `SafeFetcher(FetchPolicy(...))` in `app/crawlers/fetcher.py`. Reuse it within a `with` block for a single synchronous run: approved hosts, pinned public IPs with original-host TLS, robots, shared byte/request/deadline limits. RSS/HTML base fetch methods and `fetch_website_excerpt()` now use it; source classes with their own requests/cloudscraper paths and startup discovery are **not yet migrated**. Do not add direct HTTP fallbacks after a safety refusal. `document_url` is private resolution data (may contain query secrets); never log/export the whole response. HTTP tests must use the external `fetch_network` fixture, not mock our fetcher or launch an uninstrumented HTTP helper. This is locally tested, not deployed; see `docs/audits/2026-09-06-m12-safe-fetch.md` for exact coverage and limits.

M1.3/M1.4 add `CrawlEngine.preview()` / `run()` and `scripts/run_recipe.py` (default preview, explicit `--apply`). `run()` owns independent transactions and never commits the caller's session; use a fresh transaction to observe its committed rows under MySQL REPEATABLE READ. Only the new engine uses the complete quality gate; automatic registry/Celery schema routing remains M2. The legacy adapter translates exact RSS/HTML base configuration, never runs custom legacy Python. Parsing uses a separately supervised, network-disabled helper; neither helper is an OS/filesystem sandbox. Replay is preview-only, raw snapshots are sensitive and opt-in, and recipe validity is not publication approval. Bump execution/prompt versions when interpretation changes. Article migration `e6a91f4c820d` is expand-only: nullable quality/language/provenance markers, no legacy full/fr backfill. Marked metadata/excerpts never generate digest/insight; old NULL behavior remains compatible. Whole M1 is deployed at application `1052edf` / schema `e6a91f4c820d`: offline 459 passed, CI and both real candidates' 12 MySQL tests passed. See `docs/audits/2026-09-07-m1-release.md` for release/rollback evidence and remaining validation limits. M2-A/B1 are local-only: source list → Crawl config → immutable-by-HTTP candidates → explicitly authorized M1 preview. Saving never fetches; preview never ingests, dispatches LLM work or approves a candidate. Default reports retain at most 5 bounded samples and hash references, not raw snapshots; at most 20 per candidate. Optional B2a evidence is described below and is not approval. Admin source-input changes advance generation, excluding ordinary crawl timestamps/name/frequency; changed inputs stale reports. The 20s/6-request engine budget is not an HTTP/DB hard deadline or global lease. Migrations `a731c9e25d80` and `b6c2a4d9e710` add isolated storage; production remains M1/e6. B2a now adds opt-in private raw evidence and real offline replay: an explicitly configured `CRAWL_EVIDENCE_DIR` outside the checkout, owned by the app UID with 0700 permissions, random 0600 files, 6 documents/2MiB body/3MiB bundle, 32 files/64MiB total, 24h expiry and explicit/opportunistic cleanup under nonblocking POSIX flock. Default previews still store no raw pages. File/DB/capture bindings and current inputs must match; missing/expired/unsafe files fail closed, replay never fetches missing pages or grants ingestion/publication authority. Raw evidence is sensitive, not encrypted, and not automatically physically deleted on expiry; do not serve the directory or log payloads. No new DDL in B2a. Persistent policy/independent validation/active publication, approval, routing, lease/outbox and M3/M4 remain pending. See `docs/audits/2026-09-08-m2b2a-private-evidence.md`; all M2 changes remain local/unsubmitted, production M1 is unchanged.

### Celery Configuration

`celery_app.py` — three queues (crawl, llm, email) with explicit task routing. Task modules must be in the `include` list or they won't be discovered by workers. Beat schedule: crawl check every 600s (the task additionally has a default six-hour Redis gate), daily crawl at 01:00 Paris with a DB-hour check, digest at 07:00 Paris, health check every 6h. Unified next-due scheduling remains M2.

### Key Design Decisions

- **LLM config in DB, not code** — switch providers/models from Admin UI without deploys
- **Structured responses** — NER/sentiment/classify/company_analysis request JSON objects; `app/llm/contracts.py` accepts fenced JSON but validates exact structure/types/ranges before caching or business writes.
- **Relation idempotency** — pipeline application deduplicates company/category links, tolerates historical partial retries and preserves manual company sentiment. MySQL final row locking prevents duplicate application of an already processed article, but does not prevent duplicate paid calls (leases remain future work).
- **Docker port mapping** — dev uses non-standard ports (8001/8080/6380) to avoid conflicts; prod override resets nginx to 80/443 and hides internal service ports

### Adding a New News Source

1. Create `app/crawlers/sources/new_source.py`
2. Subclass `RSSCrawler` or `HTMLCrawler`, decorate with `@register_crawler('slug')`
3. Add import in `app/crawlers/sources/__init__.py`
4. Add entry in `scripts/seed_sources.py` and run it

## Implementation Discipline

### Test-driven development (required)

- For subsequent features and bug fixes, use TDD: agree the public behavior, add a failing regression, make the smallest implementation change, then rerun the affected and full suites.
- Work in small vertical slices; do not replace correctness assertions with tests that merely reproduce known defects.
- M2's primary agreed seam is real admin HTTP: simulate normal user actions and inspect pages/reports. Do not add test-only APIs or ask the user to approve internal helper tests. Keep existing Alembic/isolated-DB checks for migration semantics.
- Use synthetic data and isolated services. MySQL integration tests under `tests/integration/` require an explicitly provisioned disposable `m0-mysql` server and `fsource_m0_validation` database; never target production with destructive fixtures.
- Production SQL inspection is read-only until validation passes and a backed-up deployment is authorized. Do not print credentials or commit database dumps.


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
