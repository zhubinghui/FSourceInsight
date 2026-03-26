"""Health check endpoint for load balancers and monitoring."""
from datetime import datetime, timedelta

from flask import Blueprint, jsonify
from sqlalchemy import text

from app.extensions import db, redis_client

health_bp = Blueprint('health', __name__)


@health_bp.route('/health')
def health():
    """Basic health check — returns 200 if app is running."""
    checks = {
        'status': 'ok',
        'timestamp': datetime.utcnow().isoformat(),
    }

    # Database check
    try:
        db.session.execute(text('SELECT 1'))
        checks['database'] = 'ok'
    except Exception as e:
        checks['database'] = f'error: {str(e)[:100]}'
        checks['status'] = 'degraded'

    # Redis check
    try:
        if redis_client:
            redis_client.ping()
            checks['redis'] = 'ok'
        else:
            checks['redis'] = 'not configured'
    except Exception as e:
        checks['redis'] = f'error: {str(e)[:100]}'
        checks['status'] = 'degraded'

    status_code = 200 if checks['status'] == 'ok' else 503
    return jsonify(checks), status_code


@health_bp.route('/health/detail')
def health_detail():
    """Detailed health check with crawl and LLM pipeline status."""
    from app.models.source import NewsSource, CrawlLog
    from app.models.article import Article
    from app.models.llm import LLMUsageLog

    now = datetime.utcnow()
    h24 = now - timedelta(hours=24)

    # Crawl health
    active_sources = NewsSource.query.filter_by(is_active=True).count()
    recent_crawls = CrawlLog.query.filter(CrawlLog.started_at >= h24).count()
    failed_crawls = CrawlLog.query.filter(
        CrawlLog.started_at >= h24, CrawlLog.status == 'failed'
    ).count()
    stale_sources = NewsSource.query.filter(
        NewsSource.is_active == True,
        db.or_(
            NewsSource.last_crawled_at.is_(None),
            NewsSource.last_crawled_at < now - timedelta(hours=24)
        )
    ).count()

    # Article pipeline health
    articles_24h = Article.query.filter(Article.crawled_at >= h24).count()
    unprocessed = Article.query.filter_by(llm_processed=False).count()

    # LLM health
    llm_calls_24h = LLMUsageLog.query.filter(LLMUsageLog.created_at >= h24).count()
    llm_failures_24h = LLMUsageLog.query.filter(
        LLMUsageLog.created_at >= h24, LLMUsageLog.success == False
    ).count()

    return jsonify({
        'timestamp': now.isoformat(),
        'crawl': {
            'active_sources': active_sources,
            'crawls_24h': recent_crawls,
            'failed_24h': failed_crawls,
            'stale_sources': stale_sources,
        },
        'pipeline': {
            'articles_24h': articles_24h,
            'unprocessed_queue': unprocessed,
        },
        'llm': {
            'calls_24h': llm_calls_24h,
            'failures_24h': llm_failures_24h,
            'failure_rate': f'{(llm_failures_24h / llm_calls_24h * 100):.1f}%' if llm_calls_24h else '0%',
        },
    })
