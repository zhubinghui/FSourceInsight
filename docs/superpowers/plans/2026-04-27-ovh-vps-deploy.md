# OVH VPS Deployment Implementation Plan

> 历史首次安装计划（非当前维护 runbook）。2026-09-06 增量验证/发布采用 [新的受控发布计划](2026-09-06-ovh-m0-validation-deploy.md)。不要重跑旧 dump 恢复、down -v 或系统安装/入口重配步骤。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Implementation discipline:** If reality diverges from this plan during execution (a step fails, environment differs from spec, etc.), **update this plan first, then act** — see CLAUDE.md "Implementation Discipline".

**Goal:** Deploy FSourceInsight to OVH VPS `vps-babefee9` (149.56.142.99), serving `https://fsourceinsight.eu` via the existing system Caddy, without disrupting the co-resident `whaleprec-aigw.eu` / ai-router service.

**Architecture:** Caddy stays the only public 80/443 listener and TLS terminator. FSourceInsight runs as Docker Compose stack with the bundled nginx container disabled; `web` binds to `127.0.0.1:8800` and Caddy reverse-proxies to it. Current production data is restored from a freshly-generated MySQL dump.

**Tech Stack:** Docker CE, Docker Compose, Caddy 2 (Let's Encrypt), MySQL 8, Redis 7, Flask + Celery, Ubuntu 24.04 LTS.

**Spec:** [`docs/superpowers/specs/2026-04-27-ovh-vps-deploy-design.md`](../specs/2026-04-27-ovh-vps-deploy-design.md)

---

## Pre-flight: prerequisites you must have ready

Before starting, gather these. The plan stops at Task 6 if you don't:

- [ ] Local Mac: dev MySQL container is running (`docker compose ps mysql` shows `Up (healthy)`).
- [ ] **GitHub Personal Access Token** with `repo` scope. Create at <https://github.com/settings/tokens>. Set 90-day expiry. Save in your password manager. You will paste it on the VPS once.
- [ ] **DEEPSEEK_API_KEY** value — copy from local `.env` or DeepSeek console.
- [ ] **OPENAI_API_KEY** value — copy from local `.env` or OpenAI console.
- [ ] SSH access to the VPS as the `ubuntu` user (already verified).

---

## Task 1: Refresh the local DB dump

**Files:**
- Modify: `scripts/data/fsourceinsight_full.sql.gz` (overwrite with current data)

**Why:** The dump checked into the repo is from 2026-04-01. The user wants *current* data restored to the VPS, so we regenerate it from the local dev MySQL container before pushing.

- [ ] **Step 1: Verify local MySQL is up**

```bash
cd /Users/zhubinghui/Projects/FSourceInsight
docker compose ps mysql
```

Expected: status shows `Up` and `(healthy)`. If not, run `docker compose up -d mysql` and wait ~10 seconds.

- [ ] **Step 2: Generate the fresh dump**

```bash
cd /Users/zhubinghui/Projects/FSourceInsight
ROOT_PASS=$(grep '^MYSQL_ROOT_PASSWORD=' .env | cut -d= -f2)
docker compose exec -T mysql mysqldump \
  -u root -p"${ROOT_PASS}" \
  --single-transaction --routines --triggers --no-tablespaces \
  fsourceinsight 2>/dev/null | gzip > scripts/data/fsourceinsight_full.sql.gz
```

Expected: command exits 0. **Note:** `2>/dev/null` is required — without it, the `[Warning] Using a password on the command line interface can be insecure.` line gets piped into the gzip stream and ends up as the FIRST line of the dump, which makes MySQL choke during restore (Task 8).

- [ ] **Step 3: Sanity-check the dump**

```bash
ls -lh scripts/data/fsourceinsight_full.sql.gz
gunzip -c scripts/data/fsourceinsight_full.sql.gz | head -5
echo "--- table count ---"
gunzip -c scripts/data/fsourceinsight_full.sql.gz | grep -c '^INSERT INTO'
echo "--- row sample ---"
# Spot-check that company/article rows are actually in there:
gunzip -c scripts/data/fsourceinsight_full.sql.gz | grep -c "INSERT INTO \`company\`"
gunzip -c scripts/data/fsourceinsight_full.sql.gz | grep -c "INSERT INTO \`article\`"
```

Expected:
- File size 2–10 MB.
- First line of `head` is `-- MySQL dump 10.x ...` (NOT a `[Warning]` line — if you see a warning, redo Step 2 with `2>/dev/null`).
- Total `INSERT INTO` count: **>= 10** (roughly one or more per non-empty table; large tables get split into batches by `--net-buffer-length`).
- `company` count >= 1, `article` count >= 1 (article often gets split into many batches because rows are large — that's normal).

If the file is < 100 KB or the `company`/`article` INSERT counts are 0, **STOP** — the local DB may be empty. Investigate before proceeding.

---

## Task 2: Add the Caddy-aware Compose overlay

**Files:**
- Create: `docker-compose.caddy.yml`

**Why:** Two problems with `docker-compose.prod.yml` as it stands:
1. It tries to disable the bundled nginx container by binding it to host 80/443, which conflicts with the system Caddy already on those ports.
2. It writes `ports: []` and `volumes: []` for several services — but **Docker Compose merges list values additively**, so those clears don't take effect. Without intervention, deploying `prod.yml` on the VPS would publicly expose MySQL on 3306 and Redis on 6380 (Docker's iptables rules can bypass ufw), and the `web/worker/beat` containers would fail to start because they'd try to bind-mount `/Users/zhubinghui/...` (which doesn't exist on the VPS).

This overlay fixes both with `!override` (Compose v2.20+ YAML tag) — it replaces merged lists instead of appending — and uses a Compose `profile` to gate the nginx container off.

- [ ] **Step 1: Create the file**

Create `/Users/zhubinghui/Projects/FSourceInsight/docker-compose.caddy.yml` with exactly this content:

```yaml
# Overlay for hosts where a system Caddy already terminates TLS on 80/443.
# Layer ORDER: docker-compose.yml + docker-compose.prod.yml + docker-compose.caddy.yml
#
# Why this overlay exists:
#   1. Bundled nginx container is disabled (Caddy on the host fronts everything).
#   2. The base compose file uses dev port mappings (web 8001, mysql 3306, redis 6380)
#      and a source bind-mount (.:/app). Docker Compose merges list values
#      ADDITIVELY across layers, so prod.yml's "ports: []" / "volumes: []" do
#      NOT clear the base entries. We use the YAML tag `!override` (Compose
#      v2.20+) to replace the merged list, ensuring:
#        - mysql/redis are NOT exposed to the host (internal Docker network only)
#        - web is bound only to 127.0.0.1:8800 for Caddy to reverse-proxy
#        - no source bind-mount (image content is authoritative in production)
#
# Usage:
#   docker compose -f docker-compose.yml \
#                  -f docker-compose.prod.yml \
#                  -f docker-compose.caddy.yml \
#                  up -d --build

services:
  nginx:
    profiles: ["nginx-disabled"]   # never activated → never started

  web:
    ports: !override
      - "127.0.0.1:8800:8000"
    volumes: !override []

  worker:
    volumes: !override []

  beat:
    volumes: !override []

  mysql:
    ports: !override []

  redis:
    ports: !override []
```

- [ ] **Step 2: Validate the merged compose config**

```bash
cd /Users/zhubinghui/Projects/FSourceInsight
MERGED=$(docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.caddy.yml config 2>&1)

# 2a: web should bind ONLY to 127.0.0.1:8800
echo "=== web ports ==="; echo "$MERGED" | grep -A 80 '^  web:' | grep -B 1 -A 5 'ports:' | head -10

# 2b: mysql ports should be empty / absent
echo "=== mysql ports ==="; echo "$MERGED" | awk '/^  mysql:/{f=1} f && /^  [a-z]+:/ && !/^  mysql:/{f=0} f' | grep -A 5 'ports:' || echo "(no ports section — good)"

# 2c: redis ports should be empty / absent
echo "=== redis ports ==="; echo "$MERGED" | awk '/^  redis:/{f=1} f && /^  [a-z]+:/ && !/^  redis:/{f=0} f' | grep -A 5 'ports:' || echo "(no ports section — good)"

# 2d: web volumes should be absent (no bind-mount)
echo "=== web volumes ==="; echo "$MERGED" | grep -A 80 '^  web:' | grep -B 1 -A 5 'volumes:' | head -10 || echo "(no volumes — good)"
```

Expected:
- 2a: web ports show only one entry — `host_ip: 127.0.0.1`, `published: "8800"`, `target: 8000`.
- 2b, 2c: mysql and redis sections have no `ports:` (or just `ports:` with no list items).
- 2d: web volumes section either absent or empty — **no `source: /Users/zhubinghui/...`**.

- [ ] **Step 3: Confirm nginx is excluded from the default profile**

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.caddy.yml \
  config --services
```

Expected: list contains `web worker beat mysql redis` but **NOT** `nginx`. (Compose hides services in inactive profiles.)

---

## Task 3: Commit and push to master

**Files:**
- Modify: `scripts/data/fsourceinsight_full.sql.gz`
- Create: `docker-compose.caddy.yml`

- [ ] **Step 1: Stage and commit**

```bash
cd /Users/zhubinghui/Projects/FSourceInsight
git add scripts/data/fsourceinsight_full.sql.gz docker-compose.caddy.yml
git status
```

Expected: only those two files staged. (The new `.md` files in `docs/superpowers/` are already committed earlier in this session.)

```bash
git commit -m "$(cat <<'EOF'
chore: refresh DB dump + add Caddy compose overlay for VPS deploy

- Refreshed scripts/data/fsourceinsight_full.sql.gz from current dev DB
- Added docker-compose.caddy.yml: disables bundled nginx (via profile),
  binds web to 127.0.0.1:8800 for the system Caddy to reverse-proxy

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 2: Push**

```bash
git push origin master
```

Expected: push succeeds. If your local branch isn't tracking `master`, use `git push -u origin master`.

---

## Task 4: Install Docker CE on the VPS

> All remaining tasks run **on the VPS** (`ssh ubuntu@149.56.142.99`).

- [ ] **Step 1: Install prerequisites**

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
```

Expected: exits 0.

- [ ] **Step 2: Add Docker's official GPG key and apt repo**

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Write the apt source. We use `sudo bash -c` instead of `... | sudo tee` so a
# stray newline in a copy-paste cannot split this into two commands.
sudo bash -c 'echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list'

cat /etc/apt/sources.list.d/docker.list   # sanity-check
```

Expected: `cat` prints exactly one line: `deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable`.

- [ ] **Step 3: Install Docker Engine + Compose plugin**

```bash
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
```

Expected: ~5 packages installed without errors.

- [ ] **Step 4: Add `ubuntu` user to docker group**

```bash
sudo usermod -aG docker ubuntu
```

- [ ] **Step 5: Re-login to refresh group membership**

Exit the SSH session and reconnect:

```bash
exit
# back on your Mac:
ssh ubuntu@149.56.142.99
```

> **macOS gotcha:** if your `~/.ssh/config` has `ControlMaster auto` (or you're in a multiplexed session), the reconnect may reuse the old session and the `docker` group still won't be active. Test with `id`. If `docker` is missing from the group list but `getent group docker` on the VPS shows `ubuntu`, then run `exec newgrp docker` in the VPS shell to activate the group without disconnecting. This is a one-time workaround for the deploy session; future reconnects (after the multiplex socket times out) will pick up the group naturally.

- [ ] **Step 6: Verify**

```bash
docker --version
docker compose version
docker ps
```

Expected: versions print (Docker **29.x** as of 2026-04, with Compose plugin v2.x bundled in). `docker ps` shows an empty table — **no `permission denied`**, no `sudo` needed.

> If `apt-get install` printed a "Pending kernel upgrade" notice, ignore it for now — Docker works on the running kernel. Reboot the VPS only **after** the deployment is fully verified, so ai-router and FSourceInsight don't both bounce mid-deploy.

---

## Task 5: Configure GitHub access and clone repo

**Files (on VPS):**
- Create: `/home/ubuntu/FSourceInsight/` (cloned from GitHub)

- [ ] **Step 1: Create install dir owned by ubuntu**

```bash
# Repo lives in the ubuntu user's home — no sudo needed.
# Pick install dir under home (e.g., ~/FSourceInsight). The repo's clone
# auto-creates the directory, so we only need to choose where to clone INTO.
mkdir -p ~ && cd ~
```

- [ ] **Step 2: Configure git identity (one-time)**

```bash
git config --global user.name "zhubinghui"
git config --global user.email "zhu.pinghey@gmail.com"
```

- [ ] **Step 3: Clone using PAT**

When prompted for password, paste your GitHub Personal Access Token (not your GitHub password):

```bash
git clone -b master https://github.com/zhubinghui/FSourceInsight.git /home/ubuntu/FSourceInsight
# Username: zhubinghui
# Password: <paste PAT here>
```

Expected: `Cloning into '/home/ubuntu/FSourceInsight'...` and `Resolving deltas: ...` complete.

> Optional hardening: cache the credential helper so you don't paste again on `git pull`. The default behavior is fine for now — git will simply ask again.

- [ ] **Step 4: Verify dump and overlay are present**

```bash
cd /home/ubuntu/FSourceInsight
ls -lh scripts/data/fsourceinsight_full.sql.gz
ls -lh docker-compose.caddy.yml
```

Expected: both files exist; dump is the recent one (from Task 1).

---

## Task 6: Create production `.env`

**Files (on VPS):**
- Create: `/home/ubuntu/FSourceInsight/.env`

- [ ] **Step 1: Generate the file with random secrets**

```bash
cd /home/ubuntu/FSourceInsight
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32)
MYSQL_PASS=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 24)
MYSQL_ROOT_PASS=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 24)

cat > .env <<ENVEOF
# Flask
FLASK_APP=app
FLASK_ENV=production
SECRET_KEY=${SECRET_KEY}

# Database
MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_USER=fsourceinsight
MYSQL_PASSWORD=${MYSQL_PASS}
MYSQL_DATABASE=fsourceinsight
DATABASE_URL=mysql+pymysql://fsourceinsight:${MYSQL_PASS}@mysql:3306/fsourceinsight?charset=utf8mb4

# MySQL container
MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASS}

# Redis
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1

# LLM API Keys — fill in real values in Step 2 below
DEEPSEEK_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=

# Email (deferred — leave blank for now)
MAIL_SERVER=
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=
MAIL_PASSWORD=
MAIL_DEFAULT_SENDER=

# Crawl + cost control
DEFAULT_CRAWL_FREQUENCY_MINUTES=60
LLM_DAILY_BUDGET_USD=5.0

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
ENVEOF

chmod 600 .env
```

Expected: `.env` created, mode `600`.

- [ ] **Step 2: Add LLM API keys**

```bash
nano /home/ubuntu/FSourceInsight/.env
```

Set:
- `DEEPSEEK_API_KEY=<your real DeepSeek key>`
- `OPENAI_API_KEY=<your real OpenAI key>`

Save and exit (Ctrl-O, Enter, Ctrl-X).

- [ ] **Step 3: Verify required values are non-empty**

```bash
cd /home/ubuntu/FSourceInsight
for k in SECRET_KEY MYSQL_PASSWORD MYSQL_ROOT_PASSWORD DEEPSEEK_API_KEY OPENAI_API_KEY; do
  v=$(grep "^${k}=" .env | cut -d= -f2-)
  if [ -z "$v" ]; then echo "MISSING: $k"; else echo "OK: $k (len=${#v})"; fi
done
```

Expected: all 5 lines say `OK: ...` with non-zero lengths. If any say `MISSING`, edit `.env` again.

---

## Task 7: Build and start the Docker stack

**Why:** Three layered compose files (base + prod + caddy overlay) build the production stack with nginx disabled and web on `127.0.0.1:8800`.

- [ ] **Step 1: Build and start (detached)**

```bash
cd /home/ubuntu/FSourceInsight
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.caddy.yml \
  up -d --build
```

Expected: builds `web` and `worker` images (first-time build is slow — ~3–5 min), then starts containers. No errors about port 80/443/8800 conflicts.

- [ ] **Step 2: Wait for MySQL to become healthy**

```bash
timeout 90 bash -c 'until docker compose exec -T mysql mysqladmin ping -h localhost --silent 2>/dev/null; do echo waiting; sleep 3; done'
```

Expected: prints a few `waiting` lines, then exits 0 within ~30s.

- [ ] **Step 3: Confirm container set**

```bash
docker compose ps
```

Expected: 5 services `Up` — `web`, `worker`, `beat`, `mysql`, `redis`. **No `nginx`.**

- [ ] **Step 4: Verify web responds on the loopback port**

```bash
curl -s -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:8800/health
```

Expected: `HTTP 200` (or possibly `HTTP 503` if DB tables don't exist yet — that's still expected; the container is up). If you get `HTTP 000` or connection refused, check `docker compose logs web --tail 50`.

---

## Task 8: Restore database from dump

**Why:** Apply schema first (so any structural changes the dump doesn't have are present), then load data, then re-apply migrations (in case the dump itself is from a slightly older schema).

- [ ] **Step 1: Apply migrations (creates empty schema)**

```bash
cd /home/ubuntu/FSourceInsight
docker compose exec -T web flask db upgrade
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade ...` lines, exits 0.

- [ ] **Step 2: Restore dump into the running MySQL**

```bash
MYSQL_PASS=$(grep '^MYSQL_PASSWORD=' .env | cut -d= -f2)
gunzip -c scripts/data/fsourceinsight_full.sql.gz \
  | docker compose exec -T mysql mysql -u fsourceinsight -p"${MYSQL_PASS}" fsourceinsight
```

Expected: silent success (no output = OK). If you see `ERROR 1064` or `Access denied`, abort and check the password matches.

- [ ] **Step 3: Re-apply migrations to reconcile schema drift**

```bash
docker compose exec -T web flask db upgrade
```

Expected: either "no migrations to apply" or one or two upgrade steps complete cleanly.

- [ ] **Step 4: Verify row counts**

```bash
docker compose exec -T mysql mysql -u fsourceinsight -p"${MYSQL_PASS}" fsourceinsight -e "
  SELECT 'companies' AS tbl, COUNT(*) AS n FROM company
  UNION SELECT 'articles', COUNT(*) FROM article
  UNION SELECT 'sources',  COUNT(*) FROM news_source;"
```

Expected:
- `companies` >= 500
- `articles`  >= 800
- `sources`   >= 30

If any are zero, the restore failed — check `docker compose logs mysql --tail 50`.

- [ ] **Step 5: Re-check health**

```bash
curl -s http://127.0.0.1:8800/health | python3 -m json.tool
```

Expected: JSON shows `db: ok`, `redis: ok`.

---

## Task 9: Add the Caddy site block and reload

**Files (on VPS):**
- Modify: `/etc/caddy/Caddyfile` (append site block)

- [ ] **Step 1: Snapshot current Caddyfile**

```bash
sudo cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.$(date +%Y%m%d-%H%M%S).bak
ls -lt /etc/caddy/Caddyfile* | head -5
```

Expected: a new `Caddyfile.YYYYMMDD-HHMMSS.bak` appears.

- [ ] **Step 2: Append the FSourceInsight site block**

```bash
sudo tee -a /etc/caddy/Caddyfile <<'CADDYEOF'

fsourceinsight.eu, www.fsourceinsight.eu {
    reverse_proxy 127.0.0.1:8800
    encode zstd gzip
}
CADDYEOF
```

Expected: command exits 0; no error.

- [ ] **Step 3: View the result**

```bash
sudo cat /etc/caddy/Caddyfile
```

Expected: shows both the existing `whaleprec-aigw.eu` block AND the new `fsourceinsight.eu` block. Make sure you didn't accidentally overwrite the old one.

- [ ] **Step 4: Validate config syntax**

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
```

Expected: `Valid configuration`. If it errors, **STOP** and fix before reloading.

- [ ] **Step 5: Reload Caddy (graceful, keeps old config on failure)**

```bash
sudo systemctl reload caddy
sudo systemctl status caddy --no-pager | head -10
```

Expected: status shows `active (running)`, no recent errors. The reload triggers Let's Encrypt cert issuance for `fsourceinsight.eu` and `www.fsourceinsight.eu`.

- [ ] **Step 6: Verify ai-router still works (regression check)**

```bash
curl -sI https://whaleprec-aigw.eu | head -3
```

Expected: `HTTP/2 200` (or whatever ai-router returns for a `HEAD /`). **If ai-router is broken, immediately roll back:** `sudo cp /etc/caddy/Caddyfile.<timestamp>.bak /etc/caddy/Caddyfile && sudo systemctl reload caddy`.

- [ ] **Step 7: Verify FSourceInsight is reachable via HTTPS**

Wait ~10–30 seconds for Let's Encrypt to issue, then:

```bash
curl -sI https://fsourceinsight.eu/health
curl -s https://fsourceinsight.eu/health | python3 -m json.tool
```

Expected: `HTTP/2 200`, JSON shows `db: ok` and `redis: ok`. If you get a TLS error like `unable to get local issuer certificate`, wait another 30s and retry — Caddy is still negotiating with Let's Encrypt.

- [ ] **Step 8: Check the cert is real**

```bash
echo | openssl s_client -connect fsourceinsight.eu:443 -servername fsourceinsight.eu 2>/dev/null \
  | openssl x509 -noout -issuer -subject -dates
```

Expected: `issuer=...Let's Encrypt`, `subject=CN=fsourceinsight.eu`, valid date range.

---

## Task 10: Create admin, install backup cron, final verification

- [ ] **Step 1: Create the first admin via the setup endpoint**

In a browser, open: `https://fsourceinsight.eu/auth/setup`

Fill in your admin email and password. The endpoint becomes inactive after the first admin is created.

After creation, log in at `https://fsourceinsight.eu/auth/login` and confirm `/admin` loads.

- [ ] **Step 2: Write a Docker-aware backup wrapper**

The repo's `scripts/backup_mysql.sh` was written for hosts where `mysql-client` is installed and the MySQL port is published — but in this all-Docker deployment we deliberately don't publish 3306 to the host (the `!override` in our compose overlay), and we don't install mysql-client on the host. The script's default `BACKUP_DIR=/var/backups/fsourceinsight` also requires root. We replace it with a small VPS-local wrapper at `/home/ubuntu/backup_fsourceinsight.sh` that runs `mysqldump` *inside* the container and writes to a user-owned directory.

```bash
cat > /home/ubuntu/backup_fsourceinsight.sh <<'BACKUP_EOF'
#!/bin/bash
# Docker-aware MySQL backup wrapper for FSourceInsight VPS deployment.
# Calls mysqldump INSIDE the mysql container (the container does not publish
# its port to the host) and writes to a user-owned directory.
set -euo pipefail

REPO_DIR="/home/ubuntu/FSourceInsight"
BACKUP_DIR="${BACKUP_DIR:-/home/ubuntu/fsourceinsight-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

cd "$REPO_DIR"
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/fsourceinsight_${TIMESTAMP}.sql.gz"
MYSQL_PASS=$(grep '^MYSQL_PASSWORD=' .env | cut -d= -f2)

echo "[$(date)] Starting backup → ${BACKUP_FILE}"
docker compose exec -T mysql mysqldump \
  -u fsourceinsight -p"${MYSQL_PASS}" \
  --single-transaction --routines --triggers --no-tablespaces \
  fsourceinsight 2>/dev/null | gzip > "${BACKUP_FILE}"

SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
echo "[$(date)] Backup complete (${SIZE})"

DELETED=$(find "${BACKUP_DIR}" -name '*.sql.gz' -mtime +${RETENTION_DAYS} -delete -print | wc -l)
[ "${DELETED}" -gt 0 ] && echo "[$(date)] Pruned ${DELETED} backup(s) older than ${RETENTION_DAYS} days"
echo "[$(date)] Done."
BACKUP_EOF
chmod +x /home/ubuntu/backup_fsourceinsight.sh
```

The wrapper lives outside the repo (it's deployment-specific and references absolute paths on this host). If we want it tracked in git, that's a follow-up — for now it's documented here.

- [ ] **Step 3: Install the daily backup cron pointing at the wrapper**

```bash
sudo touch /var/log/fsourceinsight-backup.log
sudo chown ubuntu:ubuntu /var/log/fsourceinsight-backup.log
NEW_CRON="0 2 * * * /home/ubuntu/backup_fsourceinsight.sh >> /var/log/fsourceinsight-backup.log 2>&1"
( crontab -l 2>/dev/null | grep -v 'fsourceinsight-backup.log' ; echo "$NEW_CRON" ) | crontab -
crontab -l
```

Expected: `crontab -l` shows exactly one fsourceinsight line (the wrapper invocation). The `grep -v` is idempotent and replaces any prior fsourceinsight-backup line.

- [ ] **Step 4: Run the wrapper once to verify**

```bash
/home/ubuntu/backup_fsourceinsight.sh
ls -lh /home/ubuntu/fsourceinsight-backups/
```

Expected: prints `Starting backup → ...`, `Backup complete (5–6M)`, `Done.`. `ls` shows `fsourceinsight_YYYYMMDD_HHMMSS.sql.gz` of similar size to the source dump.

- [ ] **Step 5: Final smoke test from outside the VPS**

From your Mac:

```bash
curl -sI https://fsourceinsight.eu/
curl -sI https://www.fsourceinsight.eu/
curl -s https://fsourceinsight.eu/health | python3 -m json.tool
curl -sI https://whaleprec-aigw.eu/    # regression
```

Expected: all three FSourceInsight URLs respond `200` (or `301/302` redirect to login on `/`). ai-router still responds.

- [ ] **Step 6: Confirm Celery worker + beat are processing**

On the VPS:

```bash
cd /home/ubuntu/FSourceInsight
docker compose logs --tail 30 worker
docker compose logs --tail 30 beat
```

Expected: worker shows `celery@... ready.`, beat shows `Scheduler: Sending due task ...` lines. No tracebacks.

- [ ] **Step 7: (Optional) trigger a test crawl**

```bash
docker compose exec web python scripts/run_crawl.py --list
```

Expected: lists the 30 active sources. Pick one and run, e.g.:

```bash
docker compose exec web python scripts/run_crawl.py -s frenchweb
```

Expected: fetches a handful of articles without errors.

---

## Done — success criteria checklist

- [ ] `https://fsourceinsight.eu/health` returns 200 with valid Let's Encrypt cert
- [ ] `https://whaleprec-aigw.eu` still works (no regression)
- [ ] Admin login works at `/admin`
- [ ] DB shows >= 500 companies and >= 800 articles
- [ ] `docker compose ps` shows web, worker, beat, mysql, redis all `Up`; no nginx container
- [ ] Daily backup cron in `crontab -l`; manual run produced a backup file

If any item fails, **update this plan** with what happened and how it was resolved before moving on.

---

## Quick reference: tear-down / rollback

```bash
# Stop and remove everything FSourceInsight
cd /home/ubuntu/FSourceInsight
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.caddy.yml down -v

# Remove Caddy site block (restores ai-router-only)
sudo cp /etc/caddy/Caddyfile.<timestamp>.bak /etc/caddy/Caddyfile
sudo systemctl reload caddy

# Remove backup cron line
crontab -l | grep -v 'fsourceinsight-backup.log' | crontab -

# (nuclear) Remove Docker entirely
sudo apt-get purge -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo rm -rf /var/lib/docker /var/lib/containerd
```
