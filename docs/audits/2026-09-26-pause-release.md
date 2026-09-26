# Crawl pause release (2026-09-26 13:32 UTC)

Owner-authorized ("现在发布"). Plan: [2026-09-26-pause-release.md](../superpowers/specs/2026-09-26-pause-release.md).
Feature: Admin **Pause / Resume** stops scheduling a source without invalidating its policy, previews or approved
recipe ([operations](../ops/crawl-runtime.md#pause-versus-disable)).

## Evidence before release

- Local full suite on the release tree: 1237 passed, 26 skipped; 8 new tests (Admin HTTP and migration) watched
  RED first.
- Master CI run 36233568504 on `9491927`: offline 1237 passed / 26 skipped; 26 real-MySQL tests OK; worker
  lifecycle gate `WORKER_LIFECYCLE_OK`.

## Run (owner via `!`, `~/pause_release.sh 9491927…`, tag `pause-20260926133110`)

| Time (UTC) | Step |
|---|---|
| 13:31:11 | Guards passed; checkout `f0312b2` → `9491927` |
| 13:31:22 | Images built; runtime identical to the running containers; pin differs only in images |
| 13:31:50 | Beat stopped; both workers drained (0 active/reserved); all queues 0; workers and web stopped |
| 13:31:56 | Ledger after quiesce: 4000 settled reservations (396.708192 reserved / 1.188628 actual USD); 90 usage rows today |
| 13:31:56 | Backup `pause-20260926133110/database.sql.gz`, 20770821 bytes, SHA-256 `c805be5a…56a7`, verified |
| 13:32:00 | Migration `b9d4f6a2c813` → `c2e8a4f6b917`; `paused_at` present and nullable; 0 paused rows |
| 13:32:51 | New apps up, tasks registered on llm and fast workers; ledger unchanged; beat started last |
| 13:34:02 | Dispatcher and article recovery succeeded; 34/34 active sources have state rows; 0 paused |
| 13:34:03 | `RELEASE_OK`; 0 restarts, no OOM, no error lines, public health ok |

Service interruption about one minute. The two script changes from the M2 release (ledger after the drain,
queue-aware pre-beat comparison) did not trigger: the llm queue was empty and the ledger unchanged.

## Rollback

Stop beat, drain, then recreate with base + prod + caddy + evidence +
`~/fsourceinsight-backups/m2-20260925094001/candidate.compose.json`. The column stays; old code ignores it.
