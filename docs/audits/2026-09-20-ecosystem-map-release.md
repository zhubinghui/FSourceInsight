# Ecosystem map quality release (2026-09-19 22:07 UTC)

Owner-authorized direct release (single-user system): application `b08fb8d`, schema `b3d5e8a1c407`.

## Evidence
- Local: 705 passed / 16 dedicated-MySQL skipped. Intermediate commits' affected suites passed.
- CI 35471455364 failed only because `tests/integration/test_mysql_m0.py` pinned the old head; the other 15 MySQL tests
  (including empty-database upgrade = current models and legacy company data) passed. After `b08fb8d`, CI 35471857683 succeeded:
  offline suite and all 16 disposable-MySQL tests.
- Not done, unlike earlier releases: MySQL tests inside the actual candidate images, broker recycling gate on the candidates,
  browser check of the new admin pages.

## Procedure
Backup `~/fsourceinsight-backups/eco-20260919220547/database.sql.gz` (0600, gzip and dump trailer verified) → `git pull --ff-only` →
four images built while the old containers kept running, tagged `candidate-eco-20260919220547`, pinned in `candidate.compose.json` in the
same directory → beat stopped, workers stopped with a 120s grace, web stopped → `flask db upgrade` f2a67b904d31 → b3d5e8a1c407 with
the new web image → `up -d --no-build` with prod + caddy + evidence + the new pin layer.
A first attempt piped the script over SSH stdin; `docker compose exec` consumed the rest of the script, so only a backup
(`eco-20260919220505`) was taken and production was unchanged. The script was then uploaded and run as a file.
No worker drain inspection (active/reserved/scheduled) was performed before stopping, unlike the 2026-09-11 release.

## Post-deploy
Health ok (local and public); web 512MiB, llm worker 1GiB `-c 2`, fast worker 1GiB, beat 384MiB, recycling flags and the
web-only evidence volume preserved; restarts 0; fast worker ready; beat started. Map rendered 746 cards before data correction.

## Data correction
`scripts/apply_ecosystem_review.py` dry run on production: 610 rows, 0 skipped, counts as expected. Applied the 596 evidence-based rows:
199 rejected (kept as tombstones), 232 unflagged (registered outside Isère), 165 given entity type/postcode/city. Second dry run: no changes.
Public map: 746 → 315 entries; junk fragments and EURONEXT no longer shown; Schools & Research 9, Ecosystem support 13 (collapsed).
The 14 `flag` rows (Isère entities missing from the map; locations from general knowledge, not external evidence) were held for the owner, confirmed, then applied on 2026-09-20: Inovallée, SPINTEC, Institut Néel, Clinatec, Fonds Clinatec, TIMA, MIAI, Verkor, HRS, Vencorex, Renaissance Fusion, Waga Energy, Rossignol, Métropole de Grenoble. Full 610-row file now reports no changes. Map: 329 entries (Schools & Research 14, Ecosystem support 16, no sector 62). The new entries have no sector or analysis yet. Not included (duplicates or below the export threshold): Université Grenoble Alpes, CHU de Grenoble, Minatec, FAMES, IRIG, Air Liquide Advanced Technologies.

## Open
- 23 `research_lab` startup sources are still active in the database; the code no longer scans them.
- Sector groups `Embodied AI & Roboticsgrid` (id 11) and literal `Uncategorized` (id 10) need fixing in Admin; 56 entries have no sector.
- Daily backup cron has been failing since 2026-05-13 (`/home/ubuntu/backup_fsourceinsight.sh` missing).
- Rollback: `up -d` with the `cl-20260911084734` pin layer; keep the new columns (old code ignores them; server defaults apply).
  Old code would show rejected and pending rows on the map again.
- M3 merge needs an Alembic merge revision (`b3d5e8a1c407` and `a8d31c5e7902` both follow `f2a67b904d31`).

## Follow-up release: admin safety fixes (2026-09-20 16:25 UTC)

Owner-authorized. Application `e6469ba`, schema unchanged (`b3d5e8a1c407`). Local 713 passed / 16 MySQL skipped; CI 35510283338 succeeded
(offline suite + 16 disposable-MySQL tests). Same procedure as above, run from an uploaded script file: backup
`~/fsourceinsight-backups/adm-20260920162531/database.sql.gz` (0600, verified), images `candidate-adm-20260920162531` pinned in
`candidate.compose.json` there, application services stopped and recreated, `flask db upgrade` was a no-op.
Post-deploy: health ok locally and publicly, map 329 entries, memory limits and the web-only evidence volume preserved, restarts 0,
fast worker ready, no tracebacks in the llm worker's first minutes, beat's `daily-crawl-all` is `0 * * * *` (production setting remains
hour 1 Europe/Paris, so the daily crawl time is unchanged). Rollback: `up -d` with the `eco-20260919220547` pin layer.
Not done: MySQL tests inside the candidate images, worker queue drain inspection, browser check of the changed admin forms.
