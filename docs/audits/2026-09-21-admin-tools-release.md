# Admin System Health, article management and merge fix (2026-09-21 23:14 UTC)

Owner-authorized ("commit, merge, deploy"). Application `768e7ee` → `927dfe9`; schema unchanged (`c7f21a9d680e`).

## Contents
- `9c42e18` System Health page (`/admin/monitoring`, `app/monitoring.py`): stale sources, failed crawls with untruncated errors,
  queue depth that degrades to "unavailable" when the broker does not answer, LLM failure rate and today's cost against the budget.
  Also records the verified backup cron run and restore drill (`docs/audits/2026-09-21-backup-verification.md`).
- `baa7473` merge fix: when both companies link the same article, the richer link survives (sentiment, score, mention count,
  primary flag) instead of being deleted. This was the remaining lossy part of the audited merge defect.
- `927dfe9` article management (`/admin/articles`, detail, single-article reprocess): the largest admin gap in the audit.

## Evidence
Local 1109 passed / 23 skipped. CI 35662958299, 35663977890 and 35665194204 all succeeded, each including the disposable-MySQL tests.
A self-inflicted defect was caught by strengthening a test rather than by review: the detail page referenced a non-existent
relationship, so the "companies" row rendered silently empty until a test seeded a linked company.

## Procedure (web only, as on 2026-09-20)
Delta versus the deployed commit was exactly `app/monitoring.py`, `app/web/views/admin.py`, four admin templates, four docs and four
test files — no worker, model, Celery or migration change — so only `web` was rebuilt and recreated. Guards in the uploaded script:
clean VPS tree, master containing the running commit, fast-forward only, expected commit `927dfe9`, delta limited to the paths above
(widened for `app/monitoring.py` before the run, after printing the file list), and the candidate reporting `c7f21a9d680e (head)`.
Backup `~/fsourceinsight-backups/adm2-20260921231438/database.sql.gz` (0600, verified); new pin layer in the same directory is a copy
of the previous one with only the web image replaced (`candidate-adm2-20260921231438`).

## Post-deploy
Health ok locally and publicly; worker, worker_fast and beat container ids and start times identical before/after (M3 paid workers
untouched, still on their own images); web 512MiB, restarts 0; no error lines in web logs; map 200, anonymous `/admin/` redirects;
`/admin/articles`, its detail and reprocess routes and `/admin/monitoring` all registered.
Not done: MySQL/broker gates inside the candidate image; browser check of the new pages.
Rollback: `up -d --no-deps web` with `nav-20260920210050/candidate.compose.json`.
