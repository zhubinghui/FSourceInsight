# FSourceInsight

French Tech Intelligence Sourcing Platform with AI-powered analysis. Aggregates 28 active news sources (including research lab crawlers), processes articles through a mixed DeepSeek/OpenAI LLM pipeline, and provides Grenoble ecosystem insights with 509 companies, AI-generated analysis, and competitor comparison.

## Features

- **28 active news sources**: National French tech media, Grenoble regional outlets, CEA research labs (Leti, List, IRIG), research lab crawlers (Spintec, LIG, GIPSA-lab, TIMA, VERIMAG, Neel, TIMC, Clinatec), startup ecosystem (Linksium, Inovallee)
- **Mixed LLM pipeline**: DeepSeek (bulk tasks) + OpenAI (structured output) with automatic fallback — translation, summarization, NER, sentiment, classification, insight generation
- **Priority highlights**: Tech Breakthrough > Research > Investment > Events, with configurable time windows
- **Grenoble Ecosystem Map**: 509 companies organized by 9 configurable sector groups, with AI-generated analysis in Chinese, competitor comparison, and auto-refresh on news
- **34 spin-off companies** tracked from CEA-Leti, Inria, UGA with structured profiles
- **Company AI analysis**: Overview, founders, website, spin-off origin, core tech, disruption potential, Chinese competitor table, business status, tracking recommendation — with revision history and field-level change tracking
- **21 ecosystem discovery sources**: Configurable startup portfolios + research lab directories with automatic company discovery and AI analysis
- **Admin panel**: Sidebar layout with user CRUD, LLM task routing matrix, sector group management, ecosystem sources, system settings, crawl schedule
- **Daily email digest**: Priority-sorted with "Top Insights" section
- **REST API**: JSON endpoints for news, companies, sources

## Quick Start (Development)

```bash
cp .env.example .env
# Edit .env: fill in DEEPSEEK_API_KEY and/or OPENAI_API_KEY

docker compose up -d
docker compose exec web flask db upgrade
docker compose exec web python scripts/seed_sources.py
docker compose exec web python scripts/seed_companies.py
docker compose exec web python scripts/seed_categories.py
docker compose exec web python scripts/seed_llm_configs.py
docker compose exec web python scripts/seed_ecosystem.py
docker compose exec web python scripts/seed_grenoble_ecosystem.py

# Create admin: visit http://localhost:8080/auth/setup
# Trigger first crawl:
docker compose exec web python scripts/run_crawl.py
```

## Production Deployment (Ubuntu/Debian)

### Prerequisites

- Ubuntu 22.04 / Debian 12
- Root or sudo access, internet connection
- GitHub account (for private repo access)
- API keys: DeepSeek and/or OpenAI

### Complete Deployment Script

```bash
# ── Step 1: SSH to server ────────────────────────────────────
ssh root@YOUR_SERVER_IP

# ── Step 2: Install system dependencies ──────────────────────
apt-get update && apt-get install -y docker.io docker-compose-plugin git curl ufw
systemctl enable docker && systemctl start docker

# ── Step 3: Configure firewall ───────────────────────────────
ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable

# ── Step 4: Clone repository ────────────────────────────────
apt-get install -y gh && gh auth login
git clone https://github.com/zhubinghui/FSourceInsight.git /opt/fsourceinsight
cd /opt/fsourceinsight

# ── Step 5: Create .env file ────────────────────────────────
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
MYSQL_PASS=$(openssl rand -base64 16 | tr -dc 'a-zA-Z0-9' | head -c 20)
MYSQL_ROOT_PASS=$(openssl rand -base64 16 | tr -dc 'a-zA-Z0-9' | head -c 20)

cat > .env << EOF
FLASK_APP=app
FLASK_ENV=production
SECRET_KEY=${SECRET_KEY}

MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_USER=fsourceinsight
MYSQL_PASSWORD=${MYSQL_PASS}
MYSQL_DATABASE=fsourceinsight
DATABASE_URL=mysql+pymysql://fsourceinsight:${MYSQL_PASS}@mysql:3306/fsourceinsight?charset=utf8mb4
MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASS}

REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1

DEEPSEEK_API_KEY=你的DeepSeek密钥
OPENAI_API_KEY=你的OpenAI密钥
ANTHROPIC_API_KEY=

MAIL_SERVER=smtp.example.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=
MAIL_PASSWORD=
MAIL_DEFAULT_SENDER=digest@fsourceinsight.com

DEFAULT_CRAWL_FREQUENCY_MINUTES=60
LLM_DAILY_BUDGET_USD=5.0
LOG_LEVEL=INFO
LOG_FORMAT=json
EOF

chmod 600 .env
nano .env  # 填入真实的 API Key

# ── Step 6: Build and start services ────────────────────────
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

echo "Waiting for MySQL..."
until docker compose exec -T mysql mysqladmin ping -h localhost --silent 2>/dev/null; do sleep 2; done
echo "MySQL ready."

# ── Step 7: Initialize database ─────────────────────────────
docker compose exec -T web flask db upgrade

# Option A: Full restore (recommended — includes all articles + AI analyses)
MYSQL_PASS=$(grep '^MYSQL_PASSWORD=' .env | cut -d= -f2)
gunzip -c scripts/data/fsourceinsight_full.sql.gz | \
    docker compose exec -T mysql mysql -u fsourceinsight -p"${MYSQL_PASS}" fsourceinsight
docker compose exec -T web flask db upgrade  # re-apply any newer migrations

# Option B: Seed only (if dump file unavailable — no articles, needs crawl+LLM)
# docker compose exec -T web python scripts/seed_sources.py
# docker compose exec -T web python scripts/seed_companies.py
# docker compose exec -T web python scripts/seed_categories.py
# docker compose exec -T web python scripts/seed_llm_configs.py
# docker compose exec -T web python scripts/seed_ecosystem.py
# docker compose exec -T web python scripts/seed_grenoble_ecosystem.py

# ── Step 8: Verify deployment ───────────────────────────────
docker compose ps
curl -s http://localhost/health

# ── Step 9: Create admin account ────────────────────────────
# Browser: http://YOUR_SERVER_IP/auth/setup

# ── Step 10: Setup daily backup ─────────────────────────────
chmod +x scripts/backup_mysql.sh
mkdir -p /var/backups/fsourceinsight
(crontab -l 2>/dev/null; echo "0 2 * * * cd /opt/fsourceinsight && MYSQL_PASSWORD=\$(grep '^MYSQL_PASSWORD=' .env | cut -d= -f2) ./scripts/backup_mysql.sh >> /var/log/fsourceinsight-backup.log 2>&1") | crontab -

# ── Step 11: First crawl (optional) ────────────────────────
docker compose exec -T web python scripts/run_crawl.py
docker compose exec -T web python scripts/run_llm_process.py -n 50
```

### Post-Deployment Verification

```bash
docker compose ps                          # 6 containers: web, worker, beat, nginx, mysql, redis
curl http://localhost/health               # {"status": "ok", "database": "ok", "redis": "ok"}
curl http://localhost/health/detail        # Crawl stats, pipeline queue, LLM health
docker compose logs worker --tail 5        # Should show "celery@xxx ready"
docker compose logs beat --tail 5          # Should show "Starting..."
```

### Seed Data Summary

| Script | Data | Count |
|--------|------|-------|
| seed_sources.py | News crawl sources (28 active) | 34 |
| seed_companies.py | Core Grenoble companies + CEA-Leti spin-offs | 73 |
| seed_categories.py | Tech categories | 14 |
| seed_llm_configs.py | LLM providers (DeepSeek + OpenAI + Anthropic) | 4 |
| seed_ecosystem.py | Discovery sources + sector groups + settings | 21 + 9 + 7 |
| **seed_grenoble_ecosystem.py** | **509 companies with full AI analysis** | **509** |

### SSL Setup (Optional)

```bash
apt install -y certbot
docker compose stop nginx
certbot certonly --standalone -d yourdomain.com
# Edit docker-compose.prod.yml: uncomment SSL volume mount
# Edit docker/nginx.prod.conf: uncomment HTTPS blocks, comment HTTP block
docker compose up -d nginx
```

### Routine Operations

```bash
cd /opt/fsourceinsight

# Pull updates and redeploy
git pull origin master
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose exec -T web flask db upgrade

# Manual crawl
docker compose exec web python scripts/run_crawl.py
docker compose exec web python scripts/run_crawl.py -s cea-leti

# Batch LLM processing
docker compose exec web python scripts/run_llm_process.py -n 50

# View logs
docker compose logs -f worker beat

# Check today's LLM cost
docker compose exec web python -c "
from app import create_app; from app.extensions import db
from app.models.llm import LLMUsageLog; from sqlalchemy import func
from datetime import datetime
app = create_app()
with app.app_context():
    today = datetime.utcnow().replace(hour=0,minute=0,second=0,microsecond=0)
    cost = db.session.query(func.coalesce(func.sum(LLMUsageLog.cost_usd),0)).filter(LLMUsageLog.created_at >= today).scalar()
    print(f'Today: \${float(cost):.4f}')
"
```

## Configuration

### Environment Variables (.env)

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | MySQL connection string | **Required** |
| `DEEPSEEK_API_KEY` | DeepSeek API key (bulk tasks + fallback) | Recommended |
| `OPENAI_API_KEY` | OpenAI API key (structured output) | Recommended |
| `LLM_DAILY_BUDGET_USD` | Daily LLM cost cap | 5.0 |
| `MAIL_SERVER` | SMTP server for digests | Optional |
| `SENTRY_DSN` | Sentry error tracking | Optional |

### Admin UI Settings (Runtime, no restart needed)

| Setting | Path | Description |
|---------|------|-------------|
| LLM Model Config | `/admin/llm-config` | Provider, model, tasks, costs per config |
| Task Routing | `/admin/llm-routing` | Visual matrix of task-to-model mapping |
| Sector Groups | `/admin/sector-groups` | Ecosystem map categories (name, icon, color, keywords) |
| Ecosystem Sources | `/admin/startup-sources` | Startup portfolio + research lab discovery URLs |
| Highlight Periods | `/admin/settings` | Days per highlight type + crawl schedule + timezone |
| User Management | `/admin/users` | Create, edit, delete users with roles |
| Company Management | `/admin/companies` | Add, edit, merge, with duplicate checking |

## Architecture

```
News Sources (28) --> Crawlers (RSS/HTML) --> MySQL --> LLM Pipeline --> Web UI / Email
                                                          |
                                              DeepSeek: translate, digest, summarize, sentiment, insight (fallback)
                                              OpenAI:   NER, classify, insight (primary), company analysis

Ecosystem Sources (21) --> Startup Discovery --> Company DB --> AI Analysis --> Ecosystem Map
                           (daily 2:30 AM)       (509 co.)     (auto-classify)   (9 sectors)
```

**Services** (Docker Compose): web (Gunicorn), worker (Celery), beat (scheduler), nginx, mysql, redis

### Updating an Existing Deployment

```bash
cd /opt/fsourceinsight
git pull origin master
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose exec -T web flask db upgrade

# If DB dump was updated (check git log for changes to scripts/data/):
# MYSQL_PASS=$(grep '^MYSQL_PASSWORD=' .env | cut -d= -f2)
# gunzip -c scripts/data/fsourceinsight_full.sql.gz | \
#     docker compose exec -T mysql mysql -u fsourceinsight -p"${MYSQL_PASS}" fsourceinsight
# docker compose exec -T web flask db upgrade
```

## License

Private project. Powered by ZhuBinghui.
