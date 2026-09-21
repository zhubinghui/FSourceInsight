# Daily backup: cron firing and restore drill verified (2026-09-21)

Follow-up to `docs/audits/2026-09-20-ecosystem-ops-followup.md`, where the reinstalled wrapper had only been run by hand.

- **Cron firing**: `/var/log/fsourceinsight-backup.log` records an unattended run at 2026-09-21 02:00:01 UTC, finished 02:00:05,
  producing `fsourceinsight_20260921_020001.sql.gz` (20M, 0600). The `not found` lines in that log all predate the reinstall
  (last one 2026-09-20 02:00); an earlier session note claiming the fix had failed was a misreading of log order and is withdrawn.
- **Restore drill** (`~/fsourceinsight-backups/restore_drill.sh`, reusable): the latest daily dump was restored into a disposable
  `mysql:8.0` container with no network and a tmpfs datadir, then compared with production over a read-only transaction.
  Production was never written to; the container was removed afterwards (host check: no drill containers, disk unchanged).

  | | restored | production |
  |---|---|---|
  | article / company / llm_usage_log | 10842 / 7845 / 177811 | 10888 / 7889 / 178314 |
  | map entries / news_source / user | 329 / 38 / 3 | 329 / 38 / 3 |
  | alembic head | c7f21a9d680e | c7f21a9d680e |

  30 tables restored. The three growing counts differ because the dump is ~20h old; stable data matches exactly.
- Drill gotcha: the MySQL image runs a temporary init server that answers `mysqladmin ping` but refuses connections, so the script
  waits for "ready for connections" on port 3306 *and* a successful query before importing.
- Still unverified: restoring into a full application stack (the drill checks data, not that the app boots against it) and
  off-host copies of the backups — everything lives on the same VPS disk.
