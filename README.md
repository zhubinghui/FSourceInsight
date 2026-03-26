# FSourceInsight

French tech news aggregator with AI-powered translation, summarization, and company analysis. Focused on the Grenoble / Auvergne-Rhone-Alpes tech ecosystem.

## Features

- **15 news sources**: National French tech media, Grenoble regional outlets, and institutional press (STMicroelectronics, CEA-Leti, Schneider Electric, etc.)
- **Multi-LLM pipeline**: Configurable providers (OpenAI, Anthropic, DeepSeek, Ollama) for translation (FR→ZH/EN), summarization, company NER, sentiment analysis, and classification
- **Company intelligence**: Track companies across all news sources, with sentiment trends and article associations
- **Daily email digest**: Morning email with news summaries in your preferred language
- **Keyword subscriptions**: Get alerts when news matches your keywords
- **REST API**: JSON API for programmatic access

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env with your database passwords and API keys

# 2. Start all services
docker-compose up -d

# 3. Wait for MySQL to be healthy, then initialize
docker-compose exec web flask db upgrade
docker-compose exec web python scripts/seed_sources.py
docker-compose exec web python scripts/seed_companies.py
docker-compose exec web python scripts/seed_categories.py
docker-compose exec web python scripts/seed_llm_configs.py

# 4. Create admin account
# Visit http://localhost/auth/setup in your browser

# 5. Trigger first crawl
docker-compose exec web python scripts/run_crawl.py
```

The app is now running at **http://localhost**.

## Production Deployment (Ubuntu)

```bash
# Use production overrides
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Set up MySQL backup cron (daily at 2 AM)
echo "0 2 * * * cd /path/to/FSourceInsight && ./scripts/backup_mysql.sh" | crontab -

# Monitor health
curl http://localhost/health
curl http://localhost/health/detail
```

## Configuration

All configuration is via environment variables in `.env`. Key settings:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | MySQL connection string | Required |
| `OPENAI_API_KEY` | OpenAI API key for LLM processing | Required |
| `MAIL_SERVER` | SMTP server for email digests | Required |
| `LLM_DAILY_BUDGET_USD` | Daily LLM cost cap in USD | 5.0 |
| `DEFAULT_CRAWL_FREQUENCY_MINUTES` | Default crawl interval | 60 |
| `SENTRY_DSN` | Sentry error tracking (optional) | - |

LLM provider/model configuration is managed in the Admin UI (`/admin/llm-config`), not in code.

## Architecture

```
┌──────────┐     ┌─────────┐     ┌───────┐     ┌──────────┐
│  Celery  │────>│ Crawlers │────>│ MySQL │<────│ Flask    │
│  Beat    │     │ (RSS/   │     │       │     │ Web App  │
│(schedule)│     │  HTML)  │     │       │     │ (Jinja2  │
└──────────┘     └────┬────┘     └───┬───┘     │  +HTMX)  │
                      │              │          └────┬─────┘
                      v              │               │
                ┌───────────┐        │          ┌────┴─────┐
                │   LLM     │────────┘          │  REST    │
                │  Pipeline │                   │  API     │
                │(LiteLLM)  │                   └──────────┘
                └───────────┘
                      │
                ┌─────┴──────┐
                │   Email    │
                │  (digest/  │
                │   alerts)  │
                └────────────┘
```

## Development

```bash
# Install dependencies
pip install -r requirements/dev.txt

# Run locally (requires MySQL and Redis)
flask run

# Run tests
pytest

# Run single crawler manually
python scripts/run_crawl.py -s usine-digitale

# Process articles through LLM
python scripts/run_llm_process.py -n 5
```

## License

Private project.
