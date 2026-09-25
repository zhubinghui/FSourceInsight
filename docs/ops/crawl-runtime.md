# Crawl runtime: schedule, claims, recipe activation and article LLM jobs

Design: [M2 activation/routing spec](../superpowers/specs/2026-09-25-m2-activation-routing-design.md).
Implementation plan: [plan](../superpowers/plans/2026-09-25-m2-activation-routing.md).

## Schedule

Beat runs `app.crawlers.tasks.dispatch_due_crawls` every 60 seconds. It gives every active source a
`crawl_source_state` row, claims at most 4 due sources (twice the production crawl concurrency; the spec's cap is 50) and sends `crawl_source(source_id, claim_id)`. At the daily anchor the sources are therefore worked through over several minutes instead of being claimed at once, so queued claims do not outlive their lease.

One rule decides the next due time (`app/crawlers/schedule.py`):

| Result | Next due |
|---|---|
| success / no change / partial | the earlier of *start + frequency* and the first daily anchor more than 30 minutes after the start |
| timeout, network, 5xx, 429, database error | *end + min(frequency, 15 min × 2^(n−1))*, or Retry-After (at most 24 h) |
| forbidden, robots, TLS, unsafe URL, other HTTP 4xx, `schema_stale`, `policy_unavailable`, `invalid_schema` | *end + 24 h*, and the source is flagged for attention |
| empty extraction, low quality, parser errors | normal schedule; flagged after 3 consecutive failures |

- The daily anchor is `crawl_daily_hour` in `crawl_timezone` (Admin settings; default 01:00 Europe/Paris).
  An invalid value falls back to the default. A repeated autumn hour runs once; a skipped spring hour moves
  to the first instant after the gap.
- Frequencies below 15 minutes (including 0 or empty) count as 15 minutes.
- `crawl_check_interval_hours` is retired; the old `daily-crawl-all` and `crawl-frequency-check` beat
  entries are gone, and their task names only return `skipped`.

## Claims and leases

A claim increments the source's `fence`, sets a 15-minute lease and opens a `crawl_log` row. The worker
writes articles, their LLM jobs, the log outcome and the next due time in one transaction, and only if
the claim, fence, lease and activation generation are unchanged. A late worker whose lease expired, or
whose source was approved/rolled back/retired meanwhile, writes nothing (`outcome = stale`).
`crawl_source` has a 600 s soft / 660 s hard time limit, below the lease. Leases are logical: they do
not kill a stuck process.

Manual crawls (`Crawl now`, `Crawl all now`, `scripts/run_crawl.py`) go through the same claims.
While a source runs, a manual request only reports "already running".

## Pause versus disable

To stop crawling a source for a while, use **Pause** on the source list (migration `c2e8a4f6b917`). A paused
source is skipped by the dispatcher, "Crawl now" and `scripts/run_crawl.py`; a run already in progress finishes.
Pausing changes nothing else, so its source policy, preview evidence and approved recipe stay valid, and
**Resume** makes it crawlable again (immediately if it is already due).

**Disable** (the On/Off toggle) is for retiring a source: the enabled flag is part of the source's configuration,
so toggling it makes its policy, previews and approved recipe stale (`schema_stale`), and they must be reviewed and
approved again.

## Attention

The source list shows the route, the next due time and an attention badge:

- `forbidden`, `robots_*`, `tls_error`, `http_error`, `unsafe_url`: check the site; the source will not
  work until the site or its policy changes. Consider disabling it.
- `extraction_failed`: fix the recipe or the legacy crawler.
- `schema_stale`, `policy_unavailable`, `invalid_schema`: re-approve a recipe or return to the legacy crawler.

A success clears the badge.

## Recipe activation

On a candidate's page, **Approve** needs a saved, effective source policy and evidence:

- a learned candidate: its holdout validation must currently be `passed`;
- a hand-written candidate: a `ready` preview under the saved policy, less than 24 hours old and still
  current (no source or policy change since).

Approval makes the source due immediately. The crawl configuration page offers **Roll back to previous
version** (only if the source is unchanged since that version was approved) and **Return to legacy
crawler** (always). Every decision is recorded with its actor and evidence. A source routed to a recipe
never falls back to its legacy crawler: problems block it and flag it for attention.

## Article LLM jobs

Every new or upgraded article gets an `article_llm_job` in the same transaction. The llm worker claims a
job before any model call, so duplicate messages never pay twice. `app.llm.article_tasks.recover` runs
every 60 s: it re-sends queued jobs with a spacing that grows with the job's age (121 s, then roughly doubling, at most 1 h), expires jobs queued for more than 24 h and
closes jobs running for more than 30 min as `failed (interrupted)` without paying again.

If an article's content changes while its job runs (for example a metadata-only article upgraded to full text), the job closes as `input_changed` and a fresh job is queued for the new content. Other failed jobs are not retried automatically. Use **LLM reprocess** on the dashboard (unprocessed articles
without an active job) or **Reprocess with LLM** on an article. `scripts/run_llm_process.py` calls the
pipeline directly and bypasses job claims; use it only when no llm worker is consuming the same articles.

## Release notes

1. Back up; stop beat; wait for the `crawl` and `llm` queues to drain; stop the old workers. Never run old
   and new workers together.
2. `flask db upgrade` (revision `b9d4f6a2c813`, expand-only).
3. `python scripts/backfill_article_jobs.py` (dry run), then `--apply`.
4. Start the new workers, then beat. With no approved recipe, every source still uses its legacy crawler,
   now under the new schedule and outbox.
5. Check: `dispatch_due_crawls` and `app.llm.article_tasks.recover` succeed every minute, the first due
   sources are claimed and finish, and new articles' jobs reach `done`.

Rollback: redeploy the previous image pin after the same drain. The new tables and columns stay and are
ignored by old code, which resumes its own schedule and unprocessed-article scan; queued jobs stay inert.
