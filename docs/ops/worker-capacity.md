# Production worker capacity and recycling

## Configuration

Use the production overlay (and the Caddy/private-evidence layers where deployed):

| Service | Concurrency | Container RAM cap | Completed attempts per child | Child RSS threshold |
|---|---:|---:|---:|---:|
| worker (llm) | 2 | 1GiB | 50 | 393216KiB = 384MiB |
| worker_fast (crawl,email) | 2 | 1GiB | 50 | 393216KiB = 384MiB |
| beat | not a worker pool | 384MiB | — | — |

Both task workers explicitly use prefork. Development base remains llm=4,
fast=2, without recycling overrides. Queues/names, LLM 10/min rate limit,
acknowledgements, retries, database/model routing and web concurrency do not change.

Celery/billiard returns the task result before recycling. The limit counts
completed **attempts**, including failures/retries, not successfully enriched
articles. On the deployed Linux implementation, RSS uses `ru_maxrss` (process
high-water mark): even memory freed before task completion can trigger recycling.
There is no periodic idle-child memory check. RSS counts shared pages and is not
PSS, nor a reservation from the container's 1GiB budget.

These are initial operating values, not an optimum proven by throughput tests.
The threshold leaves roughly 90MiB above previously observed child RSS; the count
bounds long-lived retention without forking after every normal task. Lower LLM
concurrency may increase queue latency; it does not lower the per-article model
cost. Parent-worker or beat memory growth is not repaired by child recycling.

**Not an in-task memory ceiling.** A large/hung task can still hit the container
limit before completing. This does not implement reliable delivery, outbox,
exactly-once effects or OOM recovery, and does not resolve the old fast task's
memory-growth root cause. No new hard task timeout is introduced.

## Validation

1. `tests/test_ops/test_production_config.py` runs real Docker Compose config,
   without resolving `.env`, for development/production/Caddy/evidence combinations.
2. CI exports **only** merged worker command arrays as an artifact. The isolated
   MySQL/Redis job runs `tests/integration/check_worker_lifecycle.py --commands
   worker-commands.json` after the existing MySQL suite.
3. The lifecycle gate starts the real app/tasks with the exported commands:
   - LLM pool really starts with two processes and max 50 attempts.
   - Real Admin POSTs publish existing inactive-source crawl tasks to Redis;
     no child retires before 49 total completions, and at least one retires by 100.
   - A **fresh** fast pool executes an existing active RSS crawl. At the external
     Popen boundary the fixture touches 192MiB and holds the task above the RSS
     threshold. The child must remain alive until release, return success, then
     disappear; its parent survives and a subsequent task succeeds.
   - Fresh pool distinguishes memory-triggered from count-triggered retirement.
     Article API remains empty; no test task/API or paid model call is introduced.
4. `tests/support/worker_environment.py` is test-only, not copied into production
   images. Only disposable `m0-mysql`/`worker-redis` sockets are allowed; fetched
   content uses the existing synthetic DNS/socket/TLS helper. The explicit gate
   destroys only the guarded disposable database, never a deployment database.

This is a bounded broker/prefork lifecycle check, **not** general M2 lease/outbox,
crash recovery, throughput, night-load or long-term RSS verification. LLM tasks do
not call actual models in this gate. CI Python/installed dependencies and real
production images remain separate evidence; check both before release.

## Deployment and monitoring

Recheck capacity and take a new verified backup/rollback point. For this
configuration-only change, preserve exact existing images after verifying the
runtime source is identical; no database migration or rebuild is needed. Record
**configuration commit vs image application commit** separately. Pause beat,
inspect active/reserved/scheduled tasks on both workers, warm-stop, recreate only
the two workers using the four Compose layers, validate, then resume the original
beat. Web/private evidence/MySQL/Redis/Caddy/other projects need no restart.

Rollback must pin both old images **and old commands**; pinning just the image
would keep the new production command overrides. Never downgrade schema or restore
the whole database for this change. Do not reuse a historical fixed-SHA activate
script. If a worker cannot drain, stop and investigate rather than force-killing
an active task to satisfy a deployment timer.

Watch cgroup `memory.current`, `memory.peak`, `memory.events` (especially oom_kill),
parent/PSS, task failure rate and queue latency, not just container restart count.
The immediate post-restart memory decrease is partly a fresh-process effect,
not proof of a lasting improvement. Suggested host alert levels: MemAvailable
below 1.5GiB for five minutes, or below 1GiB immediately. Other projects/Redis
currently lack cgroup RAM caps; this is not whole-host worst-case isolation.

Background: [read-only server capacity review](../audits/2026-09-10-server-capacity.md).
