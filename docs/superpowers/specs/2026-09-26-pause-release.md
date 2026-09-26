# Release plan: crawl pause (2026-09-26)

Owner-authorized ("现在发布"). Branch `crawl-pause` fast-forwarded into master at `9491927` (release head; this plan
is committed with the release record so the tested commit is exactly what ships). Production runs `f0312b2` /
schema `b9d4f6a2c813`, pin `~/fsourceinsight-backups/m2-20260925094001/candidate.compose.json`.

## What changes

- Admin source list gets **Pause / Resume**; paused sources are skipped by the dispatcher, "Crawl now" and
  `scripts/run_crawl.py`, without invalidating policy, previews or approved recipes. A running claim finishes.
- Migration `c2e8a4f6b917`: nullable `crawl_source_state.paused_at` (expand-only; old code ignores it).
- Delta versus `f0312b2`: `app/`, one migration, `scripts/run_crawl.py`, tests, docs. No `requirements/`, `docker/`
  or Compose change.

## Gates

- Local full suite on the release tree: 1237 passed, 26 skipped.
- Master CI green on `9491927`, including `mysql-integration` and the worker lifecycle gate.

## Script (`~/.cache/fsi-release/pause_release.sh`, run on the VPS with the expected head)

Same guarded steps as the M2 release (lock, clean checkout containing `f0312b2`, m2 images running, no infra
delta, identical runtime, pin with only images changed, drain, verified backup, migrate, registration, beat last,
auto-restore of the m2 pin on failure), with three differences:

1. The ledger snapshot is taken **after** the workers are drained and stopped: production now processes LLM jobs,
   and in-flight jobs settling during the drain must not count as a change.
2. If the llm queue still held messages at the stop, the new worker legitimately processes them before beat starts;
   the pre-beat ledger comparison then only warns instead of aborting.
3. Migration check: `paused_at` exists and is nullable, and no row is paused; there is no backfill step.

## Rollback

Stop beat, drain, then recreate web/worker/worker_fast/beat with base + prod + caddy + evidence +
`~/fsourceinsight-backups/m2-20260925094001/candidate.compose.json`. The column stays; old code ignores it (a paused
source would be crawled again by the old code).
