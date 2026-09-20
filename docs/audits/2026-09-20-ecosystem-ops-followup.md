# Ecosystem operations follow-up (2026-09-20 21:10–21:30 UTC)

Owner-authorized ("complete all open items in order"). Production data/host changes only; no application release.
Fresh backups immediately before: `nav-20260920210050/database.sql.gz` and the new daily file below.

1. **Discovery sources**: the 23 `research_lab` startup sources (ids 4–26) set inactive through the application ORM. Active now:
   Linksium Portfolio, CEA-Leti Startup Program, Minalogic Member Directory. The code already ignored lab sources.
2. **Daily backup cron**: `/home/ubuntu/backup_fsourceinsight.sh` had been missing since 2026-05-13 while cron kept calling it.
   Reinstalled (host-only, mode 0700, not in git): dumps inside `fsourceinsight-mysql-1`, writes a 0600
   `fsourceinsight_YYYYmmdd_HHMMSS.sql.gz` via a `.partial` file, verifies gzip and the dump trailer, prunes only its own
   daily files older than 30 days. Run once with a cron-like empty environment: exit 0, 20M file, logged to
   `/var/log/fsourceinsight-backup.log`. Side effect of the 30-day rule on that run: the 18 stale daily dumps from April–May 2026
   were pruned; release backup directories are never touched. Not verified: the 02:00 cron firing itself, and a restore drill.
3. **Sector groups**: id 11 renamed `Embodied AI & Roboticsgrid` → `Embodied AI & Robotics` (Yona Robotics' sector string updated with it);
   placeholder group id 10 `Uncategorized` deleted; the literal sector `Uncategorized` cleared on 7 companies.
4. **Missing sectors**: 76 approved map entries had no sector; about 20 of them are institutions/support organisations that are grouped by
   entity type and need none. `docs/audits/data/2026-09-20-sector-fixes.csv` (31 rows, each with its basis) was dry-run then applied with a
   slug + exact-name guard and "never overwrite an existing sector": 25 sectors set to exact group names (basis: Minalogic themes or general
   knowledge, stated per row) and 6 law/IP/consulting/training firms retyped `ecosystem_support`. Map: Uncategorized 62 → 31, Ecosystem support 16 → 22.
   Left for the owner (no reliable basis): Adentis, AMI, Asteelflash France, Astriis, Axandus, BeeAlp, Blue Dot Production, Bluetwin,
   Delta Concept, DilBloom, Elethic, Haya Petcare, Holli, INESO EUROPE, Innova Advanced Technologies, Jetcycle, Le French POC, Losonnante,
   OrdiEtik, Pépite.link, Phi Design, Predictive Image, Rossignol, SKALES, Studios Bouquet, UBIK, VS Technology; and two duplicates to merge
   from `/admin/companies/duplicates` instead of classifying: MICROLIGHT3D, ORIOMA SAS.
