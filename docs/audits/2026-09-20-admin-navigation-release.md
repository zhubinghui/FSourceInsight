# Admin navigation and error pages: web-only release on the M3 stack (2026-09-20 21:01 UTC)

Owner-authorized ("merge everything into master, push, then deploy").

## Source convergence
Production had been released at 17:38 UTC by a parallel session from `release/m3-bounded-learning-20260919` (application `83813e2`,
schema `c7f21a9d680e`), which already contained the ecosystem and admin-safety releases. `origin/master` (`8019816`) lacked M3.
An earlier deploy attempt of `8019816` stopped at `git pull --ff-only` before any build or container change; deploying it would have put
non-M3 code on the M3 schema. `8019816` was merged into the release head without conflicts as `768e7ee`; master fast-forwarded to it
and now contains M3 plus all admin work. The release branch itself was not modified. Local: 1099 passed / 23 skipped. CI 35536387208:
offline suite and disposable-MySQL tests passed.

## Procedure (web only)
Application delta versus the running M3 commit: `app/web/views/admin.py` and four admin templates; everything else is docs/tests.
The script (uploaded and run as a file) required a clean VPS tree, master containing the running commit, the delta limited to admin
views/templates (root Markdown planning files were allowed after the first run stopped on them — before any build), and the candidate
image reporting `c7f21a9d680e (head)`. Backup `~/fsourceinsight-backups/nav-20260920210050/database.sql.gz` (0600, verified; two
earlier `nav-*` directories hold backups from the aborted attempts). New pin layer there = copy of the M3 layer with only the web image
replaced (`fsourceinsight-web:candidate-nav-20260920210050`); service commands and worker pins unchanged. Only `web` was recreated
(`up -d --no-deps --no-build web`). No migration. The VPS checkout is now on `master` at `768e7ee`.

## Post-deploy
Health ok locally and publicly; worker, worker_fast and beat container ids and start times identical before/after (paid workers untouched);
web 512MiB, restarts 0, evidence volume still mounted read-write on web only, no error lines in web logs, map 329 entries,
anonymous `/admin/` redirects, M3 learning routes and the new review/duplicates routes both present.
Not done: MySQL/broker gates inside the candidate image, browser check of the new sidebar and error pages.
Rollback: `up -d --no-deps web` with `m3-20260920-1700/candidate.compose.json`.
