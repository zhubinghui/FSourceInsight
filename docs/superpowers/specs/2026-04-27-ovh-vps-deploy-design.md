# OVH VPS Deployment — Design Spec

**Date:** 2026-04-27
**Target host:** `vps-babefee9` (OVH VPS, public IP `149.56.142.99`)
**Domain:** `fsourceinsight.eu` (+ `www.fsourceinsight.eu`)
**Status:** Draft — pending implementation plan

## 1. Goal

Deploy the full FSourceInsight stack to an existing OVH VPS that is **already serving another site** (`whaleprec-aigw.eu` → ai-router on `127.0.0.1:8787`), without disrupting it. Restore the **current production data** (not the 4-week-old dump in the repo) and serve `https://fsourceinsight.eu` with auto-renewing Let's Encrypt certificates.

## 2. Environment Snapshot (verified 2026-04-26)

| Item | State |
|---|---|
| OS | Ubuntu 24.04 LTS, kernel 6.8 |
| Resources | 4 vCPU, 7.6 GiB RAM, 70 GiB free disk |
| Public IP | `149.56.142.99` (matches DNS A records for `@` and `www`) |
| Reverse proxy | **Caddy** (system service, listens 80/443) |
| Existing site | `whaleprec-aigw.eu` → `127.0.0.1:8787` (Node ai-router in `/opt/ai-router`) |
| Docker | **Not installed** |
| System MySQL/Redis/nginx | None running |
| Firewall | ufw active, only 22/80/443 open |
| Caddyfile | `/etc/caddy/Caddyfile` (has one site block, plus `Caddyfile.bak`) |

## 3. Architecture

```
                          Internet (80/443)
                                │
                                ▼
                  ┌─────────────────────────┐
                  │  Caddy (system, exists) │  Sole TLS terminator + auto-LE
                  └────────────┬────────────┘
              ┌────────────────┴──────────────────┐
              ▼                                   ▼
   whaleprec-aigw.eu                     fsourceinsight.eu
   (existing, untouched)                 www.fsourceinsight.eu (NEW)
              │                                   │
              ▼                                   ▼
     127.0.0.1:8787                       127.0.0.1:8800
     (ai-router)                          (FSourceInsight web container)
                                                  │
                                          Docker Compose stack:
                                          web · worker · beat ·
                                          mysql · redis
                                          (nginx container disabled)
```

## 4. Key Decisions

1. **Caddy is the only public ingress.** No new TLS endpoint, no new port-80/443 listener. We add one site block to the existing Caddyfile.
2. **The project's bundled nginx container is disabled** via Compose `profiles`. `web` exposes `127.0.0.1:8800:8000` directly; Caddy reverse-proxies to it.
3. **Skip `scripts/deploy.sh`.** It assumes a pristine VPS — installs `docker.io` (older Ubuntu package), modifies `ufw`, and binds an nginx container to 80/443. All three would conflict here.
4. **Use Docker CE from the official repo,** not Ubuntu's `docker.io`.
5. **Restore current data**, not the repo's older `scripts/data/fsourceinsight_full.sql.gz`. Step 1 below regenerates it from the local dev MySQL container before pushing.
6. **No firewall changes.** ufw already permits 80/443; internal services bind to localhost or the Docker network only.
7. **GitHub access via Personal Access Token** (repo is private). PAT scope = `repo` only.
8. **Email/SMTP deferred.** OVH MX records exist (`mx1/2/3.mail.ovh.net`) but the digest mailer is not configured in this rollout. `MAIL_*` env vars left blank.
9. **Resource budget:** ~3 GiB committed (web 512M + worker 1G + beat 256M + mysql 1G + redis 256M). VPS has ~7 GiB free; comfortably coexists with ai-router.

## 5. Deployment Steps (Summary)

Detailed exit conditions belong in the implementation plan; this section lists what gets done.

1. **Local:** add `docker-compose.caddy.yml` (overlay), dump current MySQL data → `scripts/data/fsourceinsight_full.sql.gz`. Commit both in one commit, push to `master`.
2. **VPS:** install Docker CE from official repo, add `ubuntu` to `docker` group.
3. **VPS:** clone repo (HTTPS + PAT) into `/opt/fsourceinsight`.
4. **VPS:** create `.env` — random values for `SECRET_KEY`, `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD` (auto-generated); user pastes in real `DEEPSEEK_API_KEY` and `OPENAI_API_KEY`; `MAIL_*` left blank.
5. **VPS:** add `docker-compose.caddy.yml` overlay that disables the nginx service via profile and binds `web` to `127.0.0.1:8800`.
6. **VPS:** `docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.caddy.yml up -d --build`.
7. **VPS:** `flask db upgrade` → restore dump → `flask db upgrade` again.
8. **VPS:** append site block to `/etc/caddy/Caddyfile`, validate, back up old config, `systemctl reload caddy`.
9. **VPS:** verify `https://fsourceinsight.eu/health`, create admin via `/auth/setup`, install backup cron.

## 6. Files Created / Changed

**On developer machine:**
- `scripts/data/fsourceinsight_full.sql.gz` — refreshed from local MySQL (overwrites file)
- New commit on `master` with the refreshed dump

**On VPS, in `/opt/fsourceinsight`:**
- `docker-compose.caddy.yml` — new, version-controlled overlay (also committed to repo)
- `.env` — new, **not** in git (`chmod 600`)

**On VPS, system files:**
- `/etc/caddy/Caddyfile` — appended site block; previous version saved as `Caddyfile.YYYYMMDD-HHMMSS.bak`
- `/etc/apt/sources.list.d/docker.list`, `/etc/apt/keyrings/docker.asc` — Docker official repo
- `ubuntu` user added to `docker` group
- root crontab — one new line for `backup_mysql.sh` daily at 02:00

## 7. Caddyfile Addition

```caddyfile
fsourceinsight.eu, www.fsourceinsight.eu {
    reverse_proxy 127.0.0.1:8800
    encode zstd gzip
}
```

## 8. Compose Overlay (`docker-compose.caddy.yml`)

```yaml
services:
  nginx:
    profiles: ["nginx-disabled"]   # don't start; Caddy fronts everything
  web:
    ports:
      - "127.0.0.1:8800:8000"      # localhost-only; Caddy proxies to this
```

Layered as the **third** file (after `docker-compose.yml` and `docker-compose.prod.yml`) so it overrides the prod nginx port bindings.

## 9. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Caddy reload fails, takes ai-router down | `caddy validate` before reload; `systemctl reload` keeps old config on parse error |
| Docker iptables conflicts with ufw | Web exposes only `127.0.0.1:8800`; no public Docker port → no DOCKER chain conflict with ufw 80/443 rules |
| Dump schema vs. current migrations drift | Run `flask db upgrade` both before and after restoring dump |
| PAT leak | Use scope `repo` only; set 90-day expiry; switch remote to SSH after first clone (optional) |
| Disk fills up (DB + backups) | `backup_mysql.sh` rotates after 7 days; 70 GiB free leaves wide margin |
| Repo bloat from committed dump | 1.9 MB acceptable; if it grows, switch to git-lfs or scp-only later |

## 10. Rollback Plan

| Stage | Reversal |
|---|---|
| After Docker install | `apt-get remove docker-ce docker-ce-cli containerd.io` |
| After containers up | `docker compose down -v` (drops volumes too) |
| After Caddy reload | `cp /etc/caddy/Caddyfile.<timestamp>.bak /etc/caddy/Caddyfile && systemctl reload caddy` |
| Domain-level | Caddy site block removed → fsourceinsight.eu becomes 404 from Caddy; ai-router unaffected |

## 11. Out of Scope

- Email digest / SMTP configuration (deferred; OVH MX already pointed)
- IPv6 (no AAAA record; can add later)
- CI/CD auto-deploy (manual `git pull && docker compose up -d --build` for now)
- Sentry / external monitoring
- HTTP→HTTPS redirect tuning (Caddy does this by default for any site with a hostname)

## 12. Success Criteria

1. `https://fsourceinsight.eu/health` returns HTTP 200 with valid Let's Encrypt cert.
2. `https://whaleprec-aigw.eu` still works (regression check).
3. Admin can log in at `/auth/setup` → `/admin`.
4. DB shows ~509 companies and the current article count from the dev environment.
5. `docker compose ps` shows web, worker, beat, mysql, redis all `Up`; nginx **not** running.
6. Daily backup cron present and `backup_mysql.sh` writes to `scripts/data/backups/` on next run.
