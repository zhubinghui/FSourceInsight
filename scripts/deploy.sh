#!/bin/bash
# ============================================================
# FSourceInsight - Linux Server Deployment Script
# ============================================================
# Usage:
#   1. Copy this script to your server
#   2. Run: chmod +x deploy.sh && sudo ./deploy.sh
#
# Tested on: Ubuntu 22.04 / Debian 12
# Requirements: Root or sudo access, internet connection
# ============================================================

set -euo pipefail

# ── Configuration ────────────────────────────────────────────
INSTALL_DIR="/opt/fsourceinsight"
REPO_URL=""  # <-- Fill in your git repo URL
BRANCH="main"
DOMAIN=""    # <-- Fill in your domain (optional, for SSL)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── Step 0: Pre-checks ──────────────────────────────────────
echo "============================================"
echo " FSourceInsight Deployment"
echo "============================================"
echo ""

if [ "$(id -u)" -ne 0 ]; then
    error "Please run as root or with sudo"
fi

# ── Step 1: System packages ──────────────────────────────────
info "Step 1/8: Installing system packages..."

apt-get update -qq
apt-get install -y -qq \
    docker.io \
    docker-compose-plugin \
    git \
    curl \
    ufw \
    > /dev/null 2>&1

# Start and enable Docker
systemctl enable docker
systemctl start docker

info "Docker version: $(docker --version)"
info "Docker Compose version: $(docker compose version)"

# ── Step 2: Firewall ─────────────────────────────────────────
info "Step 2/8: Configuring firewall..."

ufw --force enable > /dev/null 2>&1
ufw allow 22/tcp   > /dev/null 2>&1  # SSH
ufw allow 80/tcp   > /dev/null 2>&1  # HTTP
ufw allow 443/tcp  > /dev/null 2>&1  # HTTPS

info "Firewall configured (22, 80, 443 open)"

# ── Step 3: Clone repository ────────────────────────────────
info "Step 3/8: Setting up project..."

if [ -z "$REPO_URL" ]; then
    warn "REPO_URL not set. Assuming code is already at $INSTALL_DIR"
    if [ ! -d "$INSTALL_DIR" ]; then
        error "$INSTALL_DIR does not exist. Set REPO_URL or copy code manually."
    fi
else
    if [ -d "$INSTALL_DIR/.git" ]; then
        info "Repository exists, pulling latest..."
        cd "$INSTALL_DIR"
        git fetch origin
        git checkout "$BRANCH"
        git pull origin "$BRANCH"
    else
        info "Cloning repository..."
        git clone -b "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
    fi
fi

cd "$INSTALL_DIR"

# ── Step 4: Create .env ─────────────────────────────────────
info "Step 4/8: Configuring environment..."

if [ -f .env ]; then
    warn ".env already exists, skipping creation. Review it manually."
else
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32)
    MYSQL_PASS=$(openssl rand -base64 16 | tr -dc 'a-zA-Z0-9' | head -c 20)
    MYSQL_ROOT_PASS=$(openssl rand -base64 16 | tr -dc 'a-zA-Z0-9' | head -c 20)

    cat > .env << ENVEOF
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

# LLM API Keys — fill in your actual keys
# Mixed strategy: DeepSeek for bulk tasks, OpenAI for structured output
DEEPSEEK_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=

# Email (SMTP) — configure for daily digest
MAIL_SERVER=smtp.example.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=
MAIL_PASSWORD=
MAIL_DEFAULT_SENDER=digest@fsourceinsight.com

# Crawl defaults
DEFAULT_CRAWL_FREQUENCY_MINUTES=60

# LLM cost control (USD per day, 0 = unlimited)
LLM_DAILY_BUDGET_USD=5.0

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json

# Sentry (optional)
# SENTRY_DSN=https://xxx@sentry.io/123
# SENTRY_TRACES_RATE=0.1
ENVEOF

    chmod 600 .env
    info ".env created with random passwords. Edit it to add API keys:"
    echo ""
    echo "    sudo nano $INSTALL_DIR/.env"
    echo ""
    warn "You MUST set DEEPSEEK_API_KEY and/or OPENAI_API_KEY before LLM processing will work!"
    echo ""
    read -p "Press Enter to continue (edit .env later) or Ctrl+C to stop and edit now..."
fi

# ── Step 5: Build and start ──────────────────────────────────
info "Step 5/8: Building Docker images and starting services..."

# Production uses port 80/443 directly (no port conflicts on a dedicated server)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build 2>&1

info "Waiting for MySQL to be healthy..."
timeout 60 bash -c 'until docker compose exec -T mysql mysqladmin ping -h localhost --silent 2>/dev/null; do sleep 2; done' \
    || error "MySQL did not become healthy in 60s"

info "All services started"

# ── Step 6: Database migration and seed ──────────────────────
info "Step 6/8: Running database migrations and seeding data..."

docker compose exec -T web flask db upgrade

docker compose exec -T web python scripts/seed_sources.py
docker compose exec -T web python scripts/seed_companies.py
docker compose exec -T web python scripts/seed_categories.py
docker compose exec -T web python scripts/seed_llm_configs.py

info "Database initialized"

# ── Step 7: Verify health ───────────────────────────────────
info "Step 7/8: Verifying deployment..."

sleep 3

HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' http://localhost/health 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    info "Health check passed (HTTP 200)"
    curl -s http://localhost/health | python3 -m json.tool 2>/dev/null || true
else
    warn "Health check returned HTTP $HTTP_CODE — check logs with: docker compose logs"
fi

# ── Step 8: Setup cron jobs ──────────────────────────────────
info "Step 8/8: Setting up backup cron job..."

chmod +x scripts/backup_mysql.sh

# Add daily backup at 2:00 AM (if not already added)
CRON_CMD="0 2 * * * cd $INSTALL_DIR && MYSQL_PASSWORD=\$(grep MYSQL_PASSWORD .env | head -1 | cut -d= -f2) ./scripts/backup_mysql.sh >> /var/log/fsourceinsight-backup.log 2>&1"
(crontab -l 2>/dev/null | grep -v "fsourceinsight" ; echo "$CRON_CMD") | crontab -

info "Daily backup scheduled at 2:00 AM"

# ── Done ─────────────────────────────────────────────────────
echo ""
echo "============================================"
echo -e " ${GREEN}Deployment Complete!${NC}"
echo "============================================"
echo ""
echo " Access points:"
echo "   Web UI:    http://$(hostname -I | awk '{print $1}')"
echo "   Health:    http://$(hostname -I | awk '{print $1}')/health"
echo "   API:       http://$(hostname -I | awk '{print $1}')/api/v1/news"
echo ""
echo " First-time setup:"
echo "   1. Edit .env to add LLM API keys:"
echo "      sudo nano $INSTALL_DIR/.env"
echo ""
echo "   2. Create admin account:"
echo "      Open http://$(hostname -I | awk '{print $1}')/auth/setup"
echo ""
echo " Useful commands:"
echo "   cd $INSTALL_DIR"
echo "   docker compose ps                          # Check service status"
echo "   docker compose logs -f worker              # Watch worker logs"
echo "   docker compose logs -f beat                # Watch scheduler logs"
echo "   docker compose exec web flask db upgrade   # Run new migrations"
echo "   docker compose exec web python scripts/run_crawl.py --list"
echo "   docker compose exec web python scripts/run_llm_process.py -n 10"
echo ""
echo " SSL setup (after pointing your domain to this server):"
echo "   sudo apt install certbot"
echo "   docker compose stop nginx"
echo "   sudo certbot certonly --standalone -d yourdomain.com"
echo "   # Then edit docker-compose.prod.yml and docker/nginx.prod.conf"
echo "   # to enable the HTTPS blocks (see comments in those files)"
echo "   docker compose up -d nginx"
echo ""
