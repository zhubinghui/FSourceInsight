# Ecosystem map quality — implementation plan (2026-09-19)

Evidence and decisions: `docs/audits/2026-09-19-ecosystem-map-validation.md` (+ CSVs under `docs/audits/data/`),
moved into this worktree on 2026-09-19 (uncommitted).

## Constraints

- Branch `ecosystem-map-quality` from deployed master `8bf2563` (schema `f2a67b904d31`) in a separate worktree.
  The main checkout carries undeployed M3 work that rewrites `startup_discovery.py` and adds migrations; this work
  must be releasable without it. Keep edits to `startup_discovery.py` small to ease the later merge; new logic goes in new modules.
- TDD per CLAUDE.md: failing regression first, smallest change, affected + full suite. Baseline here: 673 passed / 16 MySQL skipped.
- No production writes from a session. Data cleanup ships as a reviewed dry-run-first script run by the operator after backup.
- New migrations are expand-only and chain after `f2a67b904d31`; merging with M3 heads is a later, explicit step.

## Confirmed product decisions

1. Scope is the Isère département (postcode 38xxx), not only the Grenoble basin.
2. Entities headquartered elsewhere but with an Isère site stay (`local_site`).
3. Groups: industry groups for companies/corporates; **Schools & Research**; **Ecosystem support**
   (banks, law/IP firms, local authorities, CCI, clusters), collapsed by default.
4. Entries whose registered address is outside Isère are unflagged first and re-added later on evidence.

## Slices

| # | Slice | Migration | Status |
|---|---|---|---|
| S1 | Discovery hygiene: `research_lab` sources never create companies; free-text strategy only when structured strategies find nothing | no | done locally (uncommitted) |
| S2 | Company `entity_type`, `postcode`, `city`, `local_site`, `review_status` (pending/approved/rejected); existing rows backfilled `approved`; map shows approved only; discovery creates `pending`; `rejected` slug blocks rediscovery (tombstone); review status editable in the Admin company form | yes (`b3d5e8a1c407`) | done locally (uncommitted) |
| S3 | `scripts/apply_ecosystem_review.py`: CSV-driven, dry-run default, `--apply`; reject junk (soft, reversible), unflag non-Isère, flag missing Isère entities, set entity type; idempotent; seed loader stops re-forcing `is_grenoble` | no | done locally (uncommitted); not run anywhere |
| S4 | Map grouping by entity type (Schools & Research, Ecosystem support) and a single sector vocabulary (SectorGroup FK or validated name); fix order-dependent substring matching | maybe | S4a (entity-type groups) and S4b-display (first-topic, word-start matching) done locally; single stored vocabulary still todo |
| S5 | Admin review queue for pending entities (approve/reject/merge, filters); Minalogic detail fetch for postcode/type via SafeFetcher | no | queue, filters, search, approve/reject, duplicate suggestions with one-step merge, and directory detail facts done locally |
| S6 | NER → pending path for Isère entities; normalized-name duplicate suggestions; field-preserving merge | no | field-preserving merge and duplicate suggestions done locally; NER path todo (NER change alters a paid prompt/contract — needs a decision) |

Admin P0 fixes from `docs/audits/2026-09-19-admin-ux-audit.md` are tracked separately.

## Operational prerequisites (operator)

- Disable the 23 `research_lab` startup sources in production before the 02:30 scan (not yet done at 2026-09-19 20:30 UTC).
- Repair the daily backup cron: `/home/ubuntu/backup_fsourceinsight.sh` has been missing since 2026-05-13.

## Log

- 2026-09-19: worktree created, baseline suite green (673/16).
- 2026-09-19: S1 done test-first in `tests/test_crawlers/test_startup_discovery.py` (2 of 3 red reproduced the production junk, then green). Full suite 676 passed / 16 MySQL skipped. Not committed, not deployed.
  Follow-up for S5: Admin still lets an operator create `research_lab` sources, which are now never scanned; the form should say so or drop the type. The `research_lab` branch in company creation is dead code, left untouched to keep the M3 merge small.
- 2026-09-19: S2 done test-first: expand-only migration `b3d5e8a1c407` (after `f2a67b904d31`), model fields, map shows approved only, list/search hide rejected, discovery creates `pending`, rejected slug is not rediscovered, Admin form edits review status (unknown/missing value is ignored). Full suite 685 passed / 16 MySQL skipped. The live-search hiding test was added together with its fix, not observed red first.
  Not verified: real MySQL upgrade, Alembic model diff, deployed behaviour. When M3 lands there will be two Alembic heads (`b3d5e8a1c407` and the M3 chain from `f2a67b904d31`) that need an explicit merge revision.
  Until S5 exists, pending entries are only findable through the Admin company list; there is no filter for them.
- 2026-09-19: S3 done test-first: `app/ecosystem_review.py` + `scripts/apply_ecosystem_review.py` (dry run default, whole-file validation before writes, slug+exact-name guard, idempotent, reject instead of delete). Seed loader no longer re-flags existing rows (test observed red against the original loader).
  Operator input generated: `docs/audits/data/2026-09-19-ecosystem-review-actions.csv` — 610 rows: 199 reject, 232 unflag, 165 keep (type/postcode/city), 14 flag (high-confidence missing Isère entities only; their locations come from model knowledge, not external evidence). Omitted on purpose: 43 REVIEW, 75 KEEP_UNVERIFIED without new facts, medium/low-confidence and duplicate candidates.
  Release order: backup → deploy S1–S3 → `flask db upgrade` → dry run → review output → `--apply`. The script has never been run against MySQL or production.
- 2026-09-19: S4a done test-first: map groups `research_education` → "Schools & Research" and `ecosystem_support` → "Ecosystem support" (last, collapsed `<details>`), regardless of sector text; untyped rows keep sector grouping. Admin form edits entity type (unknown value ignored). Full suite 693 passed / 16 MySQL skipped. Not checked in a browser.
  S4b still open: three sector vocabularies and order-dependent substring matching; production group `Embodied AI & Roboticsgrid` (id 11) and the literal `Uncategorized` group (id 10) need an operator fix in Admin → Sector Groups.
- 2026-09-19: S5a done test-first: `/admin/companies` gains review tabs with pending count, name search, filter-preserving pagination, per-row Approve/Reject (`POST /admin/companies/<id>/review`, 400 on unknown status, inherited admin guard), type/review columns, responsive table. Admin P0 #1 fixed in the same pass: delete confirmations in companies, sector groups, startup sources and users no longer interpolate names into inline script (`data-confirm`).
- 2026-09-19: S4b-display done test-first: sector → group now picks the earliest topic in the sector text and matches keywords at word starts only. Replayed against production sectors/keywords: exactly 5 map rows move (3× `MedTech / AI` and `Sensors / AI` leave AI & Computing; `Photonics / Semiconductor` moves to Photonics & Sensors).
  Evidence check before touching `_infer_sector`: against Minalogic themes (311 companies) tie-broken Semiconductor labels are not worse than clear ones (32/43 vs 48/77), so the tie-break hypothesis was dropped and the inference left unchanged; audit doc corrected.
- 2026-09-19: S6a done test-first (Admin P0 #8, partly): merge fills the target's empty fields from the duplicate (description, website, logo, HQ, sector, stage, spin-off, entity type, postcode, city, analysis), ORs map membership/local site; target values always win. Still lossy: per-article sentiment when both link the same article; no preview/undo. Full suite 701 passed / 16 MySQL skipped.
- 2026-09-19: S6b done test-first: `app/company_dedup.py` + `/admin/companies/duplicates` (spacing/case/accent/legal-suffix/word-order variants, rejected rows excluded, keeper = non-auto-created then lowest id, one-step merge through the existing merge route, capped at 200 groups). Checked on the 2,299 exported production names: 15 groups, all plausible (e.g. Thales/Thales Group, Microlight 3D/MICROLIGHT3D); "similar name, different entity" remains a reviewer call.
- 2026-09-19: S5b done test-first: `app/crawlers/directory_facts.py` parses postcode/city/organisation type from a member-directory detail page and fetches through SafeFetcher only (fails closed, no direct-HTTP fallback, tested through `fetch_network` incl. a private-address refusal). Discovery fetches facts for new entries only (≤20 per source per scan), stores postcode/city/entity type, and sets map membership to "Isère or unknown"; everything stays `pending`. Parser validated offline on 418 saved real Minalogic pages: 386 located (153 in Isère), 384 typed.
  Limits: the listing pages still use the legacy `requests` path (M3.4b migrates that); the detail parser is specific to Minalogic's page wording and returns no facts elsewhere; 15s per detail fetch inside the crawl task, no overall scan deadline.

## Release (authorized by the owner on 2026-09-19: merge to master and deploy; single-user system)

1. Fast-forward `origin/master` from this branch (the main checkout keeps its uncommitted M3 work; its local `master` is left behind on purpose and must be reconciled by the owner).
2. Wait for CI on master (offline suite + disposable-MySQL tests, which exercise the new migration on real MySQL).
3. On the VPS: fresh database backup → `git pull` → build images → pause beat, stop workers/web → `flask db upgrade` to `b3d5e8a1c407` → start with the same compose layers as the running stack (prod + caddy + evidence) → health checks.
4. Disable the 23 `research_lab` sources (now also ignored by code).
5. Dry-run `scripts/apply_ecosystem_review.py` with the 610-row actions file; apply only after the output matches expectations.
Rollback: previous images keep working with the expand-only columns (server defaults); do not downgrade the schema.

- 2026-09-19 22:07 UTC: released at `b08fb8d` / `b3d5e8a1c407`; 596 evidence-based corrections applied (map 746 → 315); 14 `flag` rows await owner review. See `docs/audits/2026-09-20-ecosystem-map-release.md`.
- 2026-09-20: Admin P0 fixes done test-first in `tests/test_web/test_admin_safety.py` (7 tests observed red, reproducing real IntegrityError 500s): self-deactivation ignored; server-side password rule (8–1024) on create/edit; duplicate email on edit refused; users who authored crawl records and LLM configs with usage history are refused deletion with a "deactivate/disable instead" message; settings reject hour >23 or unknown timezone without saving anything; beat now offers the daily crawl hourly and the task runs only at the configured local hour (production value is 1 Europe/Paris, so behaviour there is unchanged); confirmations on Crawl All Now, Send Digest Now and policy Revoke. Full suite 713 passed / 16 MySQL skipped. Not deployed.
  Dropped: a "last active admin" guard — with self-changes blocked the acting admin always remains, so the guard had no reachable case.
  Still open from the audit: lossy per-article sentiment on merge, no merge preview/undo; M3-only confirmations (start learning, record final charge) live in the unmerged M3 tree.
- 2026-09-20 16:25 UTC: admin safety fixes released at `e6469ba` (see release record).
- 2026-09-20: Admin IA, first slice, test-first: sidebar rebuilt from one navigation table — Monitoring (Dashboard, Crawl Logs, Email Logs) / Sources (News Sources incl. the whole crawl-config tree, Discovery Sources) / Ecosystem (Companies incl. merge and duplicates, Review Queue with pending count, Sector Groups) / AI-LLM / System (Users, Settings); exactly one current entry by endpoint prefix instead of substring matching; "Discovery Sources" naming unified; lab sources labelled "not scanned" in list and form.
  Admin error pages: 400/403/404/409/503 raised inside the admin blueprints (including nested crawl-config) render in the admin layout with a plain-language reason, the abort description when one was given, and a same-site-only back link. Non-admins (e.g. CSRF failure before the admin guard) still get the plain response — a test caught the first version leaking the sidebar and pending count to anonymous requests. Views that return hand-built plain-text 503 bodies are unchanged. Form input is still lost on refusal.
  Full suite 729 passed / 16 MySQL skipped. Not deployed.
