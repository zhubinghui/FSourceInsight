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

Responses are cached in Redis for 7 days, keyed by complete effective messages, prompt/contract versions, provider/model/endpoint and generation parameters. Only validated responses are cached; malformed JSON and truncated/refused output are paid failures, not fabricated empty results. Usage/cost is committed independently to `llm_usage_log`; never call the client while holding flushed business write locks. M3.1a now adds **local-only, not deployed** DB-backed pre-call reservations and immutable Admin reconciliation (`app/llm/budget.py`, migration `a8d31c5e7902`). Each config needs explicitly reviewed billable input/output token ceilings plus prices; existing configs remain NULL and new paid calls are refused until reviewed. Unknown/in-flight costs retain reservations across days; settlement failure never triggers paid fallback. A supplier violating its declared billing caps can still overcharge: the app records/blocks overruns, not guarantees external invoices. Do not deploy this as a transparent upgrade or mix old/new paid workers. M3.1b now adds local-only learning session/Agent/source budgets and the candidate workflow described below; independent holdouts and full worker/fault validation remain pending. See `docs/ops/llm-budget-accounting.md` and `docs/audits/2026-09-19-m31a-budget-accounting.md`: 729 offline passed, 18 dedicated-MySQL skipped (including 2 new); no new real MySQL/image/deployment evidence.

### Crawler System

M3.1b is **local-only, disabled by default, not deployed** (`c4e92f7a610b`): explicit Admin start/status/cancel from a retained preview, current persistent policy/history/evidence checks, DB-owned session/attempt identity and pre-call exposure fingerprints, explicit `crawl_schema` routing, bounded offline training replay and candidate-only results. Limits: 3 rounds, $0.20/session, $1/Agent/day and $1/source/day (UTC), 20,000 cumulative billable tokens; all reservations share the global admission transaction. The 180s deadline is cooperative, not an external hard kill. `queued` persists dispatch intent; enabled beat recovers it on `crawl_learn`, while expired running/unknown work is blocked rather than paid again. Learning does not use the response cache. `awaiting_validation` is NOT independent validation or approval. No Article writes/activation. Later local slices below add restricted holdouts, cooldown/safe retry, worker configuration and startup-discovery queuing. Current production evidence remains web-only; general exposure/holdout coverage, true broker/MySQL crash gates and measured worker capacity remain pending. Historical 1b local tests: 768 passed / 19 MySQL skipped; no new real MySQL/production evidence. See `docs/audits/2026-09-19-m31b-learning-sessions.md` and `docs/ops/crawl-learning.md`. Do not enable or deploy this unfinished M3 as a transparent upgrade.

Registry pattern: `@register_crawler('source-slug')` in `app/crawlers/sources/*.py`. Base classes `RSSCrawler` and `HTMLCrawler` handle fetching; subclasses customize parsing. `discover_crawlers()` imports all source modules to trigger registration.

M1.1 introduces `validate_recipe()` in `app/crawlers/schema.py` and immutable output contracts in `app/crawlers/contracts.py`. Recipes are bounded declarative data, not executable code or permission to fetch/publish. Results retain content level, language, evidence and UTC time without inventing missing dates. See `docs/audits/2026-09-06-m11-contracts.md` for supported fields and limits.

M1.2 adds `SafeFetcher(FetchPolicy(...))` in `app/crawlers/fetcher.py`. Reuse it within a `with` block for a single synchronous run: approved hosts, pinned public IPs with original-host TLS, robots, shared byte/request/deadline limits. RSS/HTML base fetch methods and `fetch_website_excerpt()` now use it; source classes with their own requests/cloudscraper paths are **not yet migrated**. Startup discovery now reuses this boundary in local-only M3.4b below; its legacy directory parser is not the M1 quality engine or a supervised parsing sandbox. Do not add direct HTTP fallbacks after a safety refusal. `document_url` is private resolution data (may contain query secrets); never log/export the whole response. HTTP tests must use the external `fetch_network` fixture, not mock our fetcher or launch an uninstrumented HTTP helper. This is locally tested, not deployed; see `docs/audits/2026-09-06-m12-safe-fetch.md` for exact coverage and limits.

M1.3/M1.4 add `CrawlEngine.preview()` / `run()` and `scripts/run_recipe.py` (default preview, explicit `--apply`). `run()` owns independent transactions and never commits the caller's session; use a fresh transaction to observe its committed rows under MySQL REPEATABLE READ. Only the new engine uses the complete quality gate; automatic registry/Celery schema routing remains M2. The legacy adapter translates exact RSS/HTML base configuration, never runs custom legacy Python. Parsing uses a separately supervised, network-disabled helper; neither helper is an OS/filesystem sandbox. Replay is preview-only, raw snapshots are sensitive and opt-in, and recipe validity is not publication approval. Bump execution/prompt versions when interpretation changes. Article migration `e6a91f4c820d` is expand-only: nullable quality/language/provenance markers, no legacy full/fr backfill. Marked metadata/excerpts never generate digest/insight; old NULL behavior remains compatible. M1 was released at application `1052edf` / schema `e6a91f4c820d`: offline 459 passed, CI and both real candidates' 12 MySQL tests passed. See `docs/audits/2026-09-07-m1-release.md` for release/rollback evidence and remaining validation limits. M2-A/B1 provide: source list → Crawl config → immutable-by-HTTP candidates → explicitly authorized M1 preview. Saving never fetches; preview never ingests, dispatches LLM work or approves a candidate. Default reports retain at most 5 bounded samples and hash references, not raw snapshots; at most 20 per candidate. Optional B2a evidence is described below and is not approval. Admin source-input changes advance generation, excluding ordinary crawl timestamps/name/frequency; changed inputs stale reports. The 20s/6-request engine budget is not an HTTP/DB hard deadline or global lease. Migrations `a731c9e25d80` and `b6c2a4d9e710` add isolated storage; the first M2 release reached b6, followed by c9 in the policy release below. B2a now adds opt-in private raw evidence and real offline replay: an explicitly configured `CRAWL_EVIDENCE_DIR` outside the checkout, owned by the app UID with 0700 permissions, random 0600 files, 6 documents/2MiB body/3MiB bundle, 32 files/64MiB total, 24h expiry and explicit/opportunistic cleanup under nonblocking POSIX flock. Default previews still store no raw pages. File/DB/capture bindings and current inputs must match; missing/expired/unsafe files fail closed, replay never fetches missing pages or grants ingestion/publication authority. Raw evidence is sensitive, not encrypted, and not automatically physically deleted on expiry; do not serve the directory or log payloads. No new DDL in B2a. Persistent policy/revocation (B2b.1) is now deployed, as described below; independent validation/active publication, approval, routing, lease/outbox and M3/M4 remain pending. See `docs/audits/2026-09-08-m2b2a-private-evidence.md`; M2-A/B1/B2a are committed on master in `90c94b6`, with CI `34356717036` passing 574 offline tests and all 14 disposable-MySQL tests. After separate deployment authorization, A/B1/B2a are now deployed at application `22c098c` / schema `b6c2a4d9e710`: local 576 passed, CI34367023823 and both actual candidates' 14 MySQL tests passed. Production additionally uses `docker-compose.evidence.yml` AFTER prod/caddy: web-only external private volume, explicitly initialized for the actual app UID (currently 0), directory0700/files0600. Keep this layer on later web recreation; no cleanup cron was added. See `docs/audits/2026-09-09-m2-partial-release.md` and `docs/ops/private-crawl-evidence.md`. This does not complete all M2 or replace the legacy daily crawler route.

M3.3a is **local-only, not independent validation** (`d9b72a6e410c`): the controlled-learning history now has global session/exposure sequences, coverage counters and input/document integrity hashes, checked at start/claim/paid admission/candidate persistence. Protocol `crawl-learning.v2` adds bounded normalized paragraph-text fingerprints alongside raw-byte/URL hashes. This recognizes some rewrapped copies, not semantic duplication or all model exposure. Legacy sessions/attempts/learning money history are not silently certified; missing/corrupt history blocks learning without releasing incurred costs. `CRAWL_LEARNING_HISTORY_SCAN_LIMIT` is 1–4096 (default4096); at capacity refuse new records, never reset/prune or sample-certify history. Hashes are not signatures or protection against whole-database rollback. Version any normalization changes. Historical 3a tests: 797 passed / 19 MySQL skipped. The scoped HTML selection/report path is described below; service gates remain pending. See `docs/audits/2026-09-19-m33a-exposure-history.md`.

M3.3b is **local-only, restricted holdout validation, NOT publication** (`e1c73d9b502a`): `crawl-learning.v3` atomically freezes a validation record for each generated candidate. Admin validation pins the first base-recipe capture saved after that freeze, never cherry-picks later good evidence. It performs offline M1 inventory/candidate checks: one non-paginated HTML list, at least three distinct full-content details and every declared detail template. RSS/multiple lists/pagination/insufficient inventory do not receive passes. Training exposures and earlier validation selections are excluded using URL/raw/normalized-text fingerprints across the controlled workflow. Selection sequence/actor/deadline and result hashes are checked; missing validation history also blocks paid learning. Later exposure, expired/missing evidence or stale authority invalidates current passes. Two engine runs share a 20s checkpoint budget, with a <=30s persistent deadline; enabled recovery expires interrupted runs, never reselects/retries them. These are not HTTP/DB hard deadlines or a complete lease protocol. Dates bound into hashes are normalized to whole seconds before persistence, not merely when hashing. Historical learning execution and current validation status are separate; all candidates remain unpublished. Historical 3b local tests: 839 passed / 19 actual-MySQL skipped. No real validation-flow/broker/process-kill evidence. The subsequent lifecycle, worker configuration and discovery queue slices are described below; actual worker/shared-evidence/capacity gates, complete recovery and general holdout coverage remain pending. See `docs/audits/2026-09-19-m33b-holdout-validation.md` and `docs/ops/crawl-learning.md`.

M2-B2b.1 (**deployed at `14dc6f1` / `c9e41a7b620f`**): `/admin/sources/<id>/crawl-config/policies` maintains immutable grant/revoke decisions for admin preview/replay. Once configured, inline host/quality overrides are forbidden; revocation or source-input changes invalidate prior reports/replay without restoring old permits after ABA. The latest decision generation must agree with `CrawlSourceProfile.policy_generation`; missing/reverted markers or missing/bad decisions fail closed, never fall back to B1. `source_generation` tracks source-input changes separately from overall generation. Policy/quality snapshots are revalidated against current system limits; hashes do not grant authority. New expand-only migration `c9e41a7b620f` adds these markers and policy history without granting legacy sources permission. Release tests: local 639 passed / 15 dedicated-MySQL skips; CI34443459274 succeeded, and actual web/worker images each passed 15 isolated-MySQL tests both before and after deployment. See `docs/audits/2026-09-10-m2-policy-release.md`. The previous fast worker had a confirmed MEMCG child kill despite restart0; production fast is now limited to 1GiB and beat to 384MiB as bounded mitigation, not proof of the memory-growth root cause or long-term capacity. Old registry/CLI behavior is unchanged; independent validation/recipe approval remains future work. Older application rollback does not enforce this new policy model: retain tables but plan restricted admin crawling and fresh policy review on return. See `docs/audits/2026-09-09-m2b2b-policy.md`.

M2-B2b.2a (**deployed at `330d50b` / `f2a67b904d31`**): saved Admin previews now append fingerprint-only `CrawlCaptureManifest` records independently of the 20-report pruning/24h raw retention. New migration `f2a67b904d31` adds `capture_generation` and `capture_history_complete`; existing profiles/old-app inserts stay incomplete, new ORM profiles start tracked. Count/sequence/current-report coverage plus a counter CAS guard persistence; document shape/hash/input bindings are checked separately. This tracks this Admin preview workflow only, not every crawler/CLI/model exposure, and is not independent validation or approval. Local 673 passed / 16 dedicated-MySQL skips; release CI34580807525 succeeded including all 16 MySQL tests and real broker recycling. Actual web/worker images each passed 16 isolated-MySQL tests before and after deployment; four applications updated, worker limits/commands and private volume preserved. Old web rollback must restrict preview writes so it cannot silently bypass tracking. See `docs/audits/2026-09-11-capture-ledger-release.md`; the prior local-only audit remains historical.

M3.2c is **local-only, safe zero-admission retry, NOT paid-work takeover** (`f8b64d2c901e`): failed/cancelled learning sets a >=6h source cooldown; new captures cannot bypass it. Blocked sessions may receive an audited Admin retry only before their original deadline/round limit and only if the entire session has NEVER had a provider reservation, including settled/reconciled/zero-cost ones. Original identity, exposure, money, limits, cooldown and deadlines persist. Retry counter/sequence/input-bound hashes participate in bounded history checks. Tasks preallocate attempt identities before claim COMMIT; error handling fences acquired attempts so stale or unclaimed messages cannot stop a newer running owner. Post-model checks precede parser startup; recovery closes calling attempts without releasing holds or retrying paid uncertainty. Migration adds two session columns and one audit table, conservatively quarantining old failures from migration time without inventing completion timestamps. Historical 2c offline suite: 878 passed / 19 real-MySQL skips, 205 ASTs / 48 templates. Real service/fault/capacity gates and the remaining M3 items above are still pending. See `docs/audits/2026-09-19-m32c-learning-lifecycle.md`.

M3.4a is **local-only configuration/CLI, NOT live worker or capacity validation**: optional `docker-compose.learning.yml` follows prod/(caddy)/evidence. `crawl-learning` profile plus the separate default-off learning flag are required; the layer gives only `worker_learn` an RO/nocopy view of web's external private evidence volume. Existing workers remain unchanged. New worker: prefork1/prefetch1, 50-task/393216KiB post-task recycling, soft180/hard195, provisional 1GiB/1CPU/PIDs64, RO root/64MiB tmpfs/cap-drop/init. `scripts/learning_worker.py run` checks enabled/0700 UID-owned RO evidence/current schema before executing only its reviewed command; `check` queries this learn node's registered tasks, actual queue/routing/exchange/pool/prefetch/recycling/timeouts, without business dispatch. Snapshot success is explicitly not live readiness. This does not verify provider pricing, source authority, actual cgroups/capacity, all other workers, beat health or exact-once recovery. Historical 4a offline suite: 924 passed / 19 actual-MySQL skips; 209 ASTs/48 templates, real Compose offline merge. No daemon/build/start, actual RO mount or prefork/timeout/fault/capacity proof. The 4a milestone had schema f8b64d2c901e; 4b/2d below advance it. Full recovery, service gates and general holdout coverage remain pending. See `docs/audits/2026-09-19-m34a-learning-worker.md` and `docs/ops/learning-worker.md`.

M3.4b is **local-only initial enterprise analysis queuing, NOT full recovery or deployment readiness** (`a2f6d9b3107c`): new Company + source-owned `StartupAnalysisJob` commit atomically; existing companies/aliases are not reassigned or automatically reanalyzed and failure counters are not reset. `app.llm.startup_tasks` consumes job IDs on `llm`; the crawl producer never invokes the model. Frozen inputs, ORM source/company generations, claim ownership, prompt/configuration checks and global reservation associations fence duplicates, ABA, manual edits, unknown costs and late results. Cache hits remain free but need a current job/input; at most three suppliers, no automatic paid takeover. Queued intent lasts 24h, execution at most180s logically; 60s recovery scans at most50 due records with >=120s durable redispatch spacing. Final deadline checks follow locking reads, but are not SQL/SDK hard deadlines. Directory SafeFetcher is limited to its configured host, 30s/6 requests/512KiB page/2MiB total; scans cap at50 sources/20 new companies per source/1000 extracted entries/4096 alias rows. No homepage fetch, private learning-volume access, Article writes or recipe activation. Source flags/ordinary company routing apply independently of `CRAWL_LEARNING_ENABLED`. Existing manual/article refresh and complete exposure coverage are not migrated. Admin lists bounded historical status or an exact job via accounting links; metadata/fees persist beyond queue expiry. Migration preserves old data/unknown charges and creates no legacy jobs; mixed old writers/bulk SQL/rollback do not enforce the new generation model. Historical 4b full local suite: **988 passed / 20 actual-MySQL skips**, 64 new offline tests, 218 ASTs/48 templates. No actual MySQL/broker/kill/capacity/deployment evidence. See `docs/ops/startup-analysis.md` and `docs/audits/2026-09-19-m34b-startup-analysis.md`.

M3.2d is **local-only learning delivery fencing, NOT paid takeover or real broker validation** (`b5d81e6a430f`, parent `a2f6d9b3107c`): `learning-delivery.v1` messages carry session ID and a key binding input hash, consumed rounds and retry count. Replayed old messages cannot claim a valid newer phase; unclaimed old errors cannot close it. Known corrupt history is still quarantined. Only an acknowledged rejected-round commit returns a continuation key; lost ACK leaves the current queued phase for recovery. A nullable `dispatch_due_at` and index reserve publication slots before broker I/O, at least30 seconds from recorded UTC admission time; slow COMMIT/RPC can outlive the interval, so this is not physical send-rate control or a publisher lease. Recovery selects at most50 due queued/expired or unconfigured active rows, never repays running uncertainty. Legacy NULL rows get no fabricated delivery permission and old single-argument messages are ignored; terminal candidate/history reads remain compatible. Final claim/admission deadline checks follow expensive reads; no SQL/SDK hard deadline or deadline extension. Admin displays eligibility, not a broker receipt or authorization. Historical 2d full local suite: **1019 passed / 20 actual-MySQL skips**, 31 new offline tests, 223 ASTs/48 templates. No actual services/capacity, commit or deployment; M3 remains incomplete. See `docs/audits/2026-09-19-m32d-learning-dispatch.md` and `docs/ops/crawl-learning.md`. Coordinate stopping all old paid callers before any separately authorized migration/rollback; old code does not enforce this fence.

Ecosystem map quality (**deployed at `b08fb8d` / `b3d5e8a1c407`**): map scope is the Isère département. `Company.review_status` (pending/approved/rejected) gates the public map; discovery creates `pending` rows, never scans `research_lab` sources, uses free-text extraction only as a fallback, and reads postcode/organisation type from member-directory detail pages through SafeFetcher. Rejected rows are kept on purpose: their slug blocks rediscovery, so reject instead of deleting junk. `entity_type` drives the Schools & Research and collapsed Ecosystem support groups. Admin: review tabs/approve/reject on `/admin/companies`, `/admin/companies/duplicates`, field-preserving merge. Reviewed bulk corrections go through `scripts/apply_ecosystem_review.py` (dry run by default, slug + exact-name guard). The fixture seed no longer re-flags `is_grenoble`. Sector inference is unchanged; a tie-break hypothesis was tested against Minalogic themes and rejected. See `docs/audits/2026-09-19-ecosystem-map-validation.md` and `docs/audits/2026-09-20-ecosystem-map-release.md`.

### Current release integration (not yet deployed)

M3 base is committed on `release/m3-bounded-learning-20260919` as `751ac51`; ecosystem `23de19e` and its release evidence were merged without overwriting them. Candidate `7f6e9f8` passed CI35510122656 (1060 offline, 22 actual MySQL tests and real broker/prefork recycling). Subsequent Admin safety `e6469ba` and M3 reservation/audit-actor deletion guards are merged in `1becae8`: CI35517521638 passed 1075 offline tests, all 22 actual MySQL tests (including extended deletion/accounting checks), and real broker/prefork recycling. Actual deployable-image gates and the production billing decision are still pending. Unique candidate schema `c7f21a9d680e` merges `b3d5e8a1c407` and `b5d81e6a430f` without rewriting either history. Discovery keeps pending review, rejected tombstones, no lab scanning and bounded same-host directory facts outside write transactions. `startup-analysis.v2` additionally binds review/geography fields and their ORM generations; old v1 jobs are not re-signed. Reviewed billing ceilings (or explicit acceptance of paused new paid calls), coordinated old-caller shutdown, backup and actual-image gates remain release prerequisites. Learning stays disabled, M3 remains incomplete, and production has not switched. See `docs/superpowers/specs/2026-09-19-m3-current-release.md` for authoritative progress and failures.

### Celery Configuration

`celery_app.py` — three queues (crawl, llm, email) with explicit task routing. Task modules must be in the `include` list or they won't be discovered by workers. Local M3.4b adds `app.llm.startup_tasks` on `llm` and a 60s recovery schedule; it does not add worker capacity or migrate every company-refresh path. Beat schedule: crawl check every 600s (the task additionally has a default six-hour Redis gate), hourly daily-crawl offers with an exact DB-configured local-hour check (default 01:00 Paris), digest at 07:00 Paris, health check every 6h. Unified next-due scheduling remains M2.

Production worker capacity is set in `docker-compose.prod.yml`: LLM concurrency 2 (development remains 4), fast concurrency 2; both prefork pools recycle after 50 completed attempts or a task-completion RSS high-water mark above 393216KiB. This is not an in-task memory limit or OOM recovery. See [worker capacity operations](docs/ops/worker-capacity.md) for isolated broker validation and configuration-only rollback. Released as configuration `81135d8` using the unchanged `14dc6f1` images/schema c9; only two workers were recreated and the original beat resumed. CI now runs a bounded real Admin/Redis/prefork recycling gate in addition to MySQL. See [release evidence](docs/audits/2026-09-10-worker-recycling-release.md), including the initial command-format gate rollback; this is not full M2 delivery/recovery or a long-term capacity test.

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
