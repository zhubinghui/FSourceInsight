# FSourceInsight

French Tech Intelligence Sourcing Platform with AI-powered analysis. Aggregates 26 news sources, processes articles through a mixed DeepSeek/OpenAI LLM pipeline, and provides Grenoble ecosystem insights with company tracking, competitor analysis, and daily digests.

## Features

- **26 news sources**: National French tech media, Grenoble regional outlets, CEA research labs, startup ecosystem (Linksium, Inovallee)
- **Mixed LLM pipeline**: DeepSeek (bulk tasks) + OpenAI (structured output) — translation, summarization, NER, sentiment, classification, insight generation
- **Priority highlights**: Tech Breakthrough > Research > Investment > Events, with configurable time windows
- **Grenoble Ecosystem Map**: 43 local companies organized by sector, with AI-generated analysis (Chinese), competitor comparison, and auto-refresh on new articles
- **34 spin-off companies** tracked from CEA-Leti, Inria, UGA with structured profiles
- **Company AI analysis**: Overview, founders, spin-off origin, core tech, disruption potential, Chinese competitor table, business status, tracking recommendation
- **Admin panel**: Sidebar layout with user CRUD, LLM task routing matrix, system settings, company management with duplicate checking
- **Daily email digest**: Priority-sorted with "Top Insights" section
- **REST API**: JSON endpoints for news, companies, sources

## Quick Start (Development)

```bash
cp .env.example .env
# Edit .env with your API keys (DEEPSEEK_API_KEY, OPENAI_API_KEY)

docker compose up -d
docker compose exec web flask db upgrade
docker compose exec web python scripts/seed_sources.py
docker compose exec web python scripts/seed_companies.py
docker compose exec web python scripts/seed_categories.py
docker compose exec web python scripts/seed_llm_configs.py

# Create admin: visit http://localhost:8080/auth/setup
# Trigger first crawl:
docker compose exec web python scripts/run_crawl.py
```

## Production Deployment (Ubuntu/Debian)

### Prerequisites

- Ubuntu 22.04 / Debian 12
- Root or sudo access
- Internet connection
- GitHub account (for private repo access)
- API keys: DeepSeek and/or OpenAI

### Step-by-Step Deployment

```bash
# ── 1. SSH to server ─────────────────────────────────────────
ssh root@YOUR_SERVER_IP

# ── 2. Install system dependencies ──────────────────────────
apt-get update && apt-get install -y docker.io docker-compose-plugin git curl ufw
systemctl enable docker && systemctl start docker

# ── 3. Configure firewall ───────────────────────────────────
ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable

# ── 4. Clone repository ────────────────────────────────────
# For private repo, install gh CLI and login first:
apt-get install -y gh && gh auth login

git clone https://github.com/zhubinghui/FSourceInsight.git /opt/fsourceinsight
cd /opt/fsourceinsight

# ── 5. Create .env file ────────────────────────────────────
# Generate secure random values
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
MYSQL_PASS=$(openssl rand -base64 16 | tr -dc 'a-zA-Z0-9' | head -c 20)
MYSQL_ROOT_PASS=$(openssl rand -base64 16 | tr -dc 'a-zA-Z0-9' | head -c 20)

cat > .env << EOF
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

# LLM API Keys (mixed strategy: DeepSeek for bulk, OpenAI for structured)
DEEPSEEK_API_KEY=YOUR_DEEPSEEK_KEY
OPENAI_API_KEY=YOUR_OPENAI_KEY
ANTHROPIC_API_KEY=

# Email (SMTP) — for daily digest
MAIL_SERVER=smtp.example.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=
MAIL_PASSWORD=
MAIL_DEFAULT_SENDER=digest@fsourceinsight.com

# Application
DEFAULT_CRAWL_FREQUENCY_MINUTES=60
LLM_DAILY_BUDGET_USD=5.0
LOG_LEVEL=INFO
LOG_FORMAT=json

# Optional: Sentry error tracking
# SENTRY_DSN=https://xxx@sentry.io/123
EOF

chmod 600 .env
# IMPORTANT: Edit .env to fill in your actual API keys
nano .env

# ── 6. Build and start services ─────────────────────────────
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Wait for MySQL
echo "Waiting for MySQL..."
until docker compose exec -T mysql mysqladmin ping -h localhost --silent 2>/dev/null; do sleep 2; done
echo "MySQL ready."

# ── 7. Initialize database ──────────────────────────────────
docker compose exec -T web flask db upgrade
docker compose exec -T web python scripts/seed_sources.py
docker compose exec -T web python scripts/seed_companies.py
docker compose exec -T web python scripts/seed_categories.py
docker compose exec -T web python scripts/seed_llm_configs.py

# ── 8. Verify deployment ────────────────────────────────────
docker compose ps                      # All 6 containers should be Up
curl -s http://localhost/health        # Should return {"status": "ok"}

# ── 9. Create admin account ─────────────────────────────────
# Open in browser: http://YOUR_SERVER_IP/auth/setup

# ── 10. Setup daily backup ──────────────────────────────────
chmod +x scripts/backup_mysql.sh
mkdir -p /var/backups/fsourceinsight
(crontab -l 2>/dev/null; echo "0 2 * * * cd /opt/fsourceinsight && MYSQL_PASSWORD=\$(grep '^MYSQL_PASSWORD=' .env | cut -d= -f2) ./scripts/backup_mysql.sh >> /var/log/fsourceinsight-backup.log 2>&1") | crontab -

# ── 11. (Optional) First crawl + LLM processing ────────────
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
| `DEEPSEEK_API_KEY` | DeepSeek API key (bulk tasks) | Recommended |
| `OPENAI_API_KEY` | OpenAI API key (structured output) | Recommended |
| `LLM_DAILY_BUDGET_USD` | Daily LLM cost cap | 5.0 |
| `MAIL_SERVER` | SMTP server for digests | Optional |
| `SENTRY_DSN` | Sentry error tracking | Optional |

### Admin UI Settings (Runtime)

| Setting | Path | Description |
|---------|------|-------------|
| LLM Model Config | `/admin/llm-config` | Provider, model, tasks, costs per config |
| Task Routing | `/admin/llm-routing` | Visual matrix of task-to-model mapping |
| Highlight Periods | `/admin/settings` | Days to show each highlight type (Breakthrough/Research/Investment/Events) |
| User Management | `/admin/users` | Create, edit, delete users with roles |
| Company Management | `/admin/companies` | Add, edit, merge, with duplicate checking |

## Architecture

```
News Sources (26) → Crawlers (RSS/HTML) → MySQL → LLM Pipeline → Web UI / Email
                                                      ↓
                                          DeepSeek: translate, digest, summarize, sentiment
                                          OpenAI:   NER, classify, insight, company analysis
```

**Services** (Docker Compose): web (Gunicorn), worker (Celery), beat (scheduler), nginx, mysql, redis

## License

Private project. Powered by ZhuBinghui.
