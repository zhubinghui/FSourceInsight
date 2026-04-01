#!/bin/bash
# ============================================================
# Restore FSourceInsight database from full dump
# Usage: ./scripts/restore_db.sh
#
# This restores the complete database including:
# - 34 news sources, 14 categories, 4 LLM configs
# - 1752 companies (509 Grenoble with AI analysis)
# - 911 articles with translations, summaries, insights
# - 21 ecosystem discovery sources, 9 sector groups
# - All article-company and article-category associations
#
# Run this AFTER flask db upgrade and INSTEAD of individual seed scripts.
# ============================================================

set -euo pipefail

DUMP_FILE="scripts/data/fsourceinsight_full.sql.gz"

if [ ! -f "$DUMP_FILE" ]; then
    echo "ERROR: $DUMP_FILE not found"
    echo "Run individual seed scripts instead."
    exit 1
fi

echo "Restoring database from $DUMP_FILE..."

# Get MySQL password from .env
MYSQL_PASS=$(grep '^MYSQL_PASSWORD=' .env | cut -d= -f2)

gunzip -c "$DUMP_FILE" | docker compose exec -T mysql \
    mysql -u fsourceinsight -p"${MYSQL_PASS}" fsourceinsight

echo "Database restored successfully."
echo ""
docker compose exec -T web python -c "
from app import create_app
from app.models.company import Company
from app.models.article import Article
from app.models.source import NewsSource
app = create_app()
with app.app_context():
    print(f'  News sources:  {NewsSource.query.count()}')
    print(f'  Companies:     {Company.query.count()} ({Company.query.filter_by(is_grenoble=True).count()} Grenoble)')
    print(f'  Articles:      {Article.query.count()}')
    print(f'  AI analyzed:   {Company.query.filter(Company.ai_analysis.isnot(None)).count()}')
"
