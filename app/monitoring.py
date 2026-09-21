"""Operational snapshot for the admin: where the platform is unhealthy right now.

Read-only. Every section degrades on its own: a broker or Redis outage must not
take the page down, because that is exactly when it is needed.
"""
from datetime import datetime, timedelta

from flask import current_app

from app.extensions import db
from app.models.article import Article
from app.models.llm import LLMConfig, LLMUsageLog
from app.models.source import CrawlLog, NewsSource

QUEUES = ['crawl', 'llm', 'email', 'crawl_learn']
STALE_AFTER = timedelta(hours=24)


def _broker():
    import redis
    return redis.from_url(current_app.config['CELERY_BROKER_URL'])


def queue_depths():
    """Pending task counts per queue, or None when the broker cannot be reached."""
    try:
        broker = _broker()
        return {queue: int(broker.llen(queue)) for queue in QUEUES}
    except Exception as exc:  # noqa: BLE001 - any broker failure degrades to "unavailable"
        current_app.logger.info('queue depth unavailable: %s', type(exc).__name__)
        return None


def snapshot():
    now = datetime.utcnow()
    since = now - STALE_AFTER
    stale_sources = NewsSource.query.filter(
        NewsSource.is_active == True,  # noqa: E712 - SQLAlchemy comparison
        db.or_(NewsSource.last_crawled_at.is_(None), NewsSource.last_crawled_at < now - STALE_AFTER),
    ).order_by(NewsSource.last_crawled_at.is_(None).desc(), NewsSource.last_crawled_at).all()
    failed_crawls = (CrawlLog.query.filter(CrawlLog.started_at >= since, CrawlLog.status == 'failed')
                     .order_by(CrawlLog.started_at.desc()).limit(20).all())
    calls = LLMUsageLog.query.filter(LLMUsageLog.created_at >= since).count()
    failures = LLMUsageLog.query.filter(LLMUsageLog.created_at >= since,
                                        LLMUsageLog.success == False).count()  # noqa: E712
    midnight = datetime.combine(now.date(), datetime.min.time())
    cost_today = db.session.query(db.func.coalesce(db.func.sum(LLMUsageLog.cost_usd), 0)).filter(
        LLMUsageLog.created_at >= midnight).scalar()
    return {
        'now': now,
        'queues': queue_depths(),
        'sources': {'active': NewsSource.query.filter_by(is_active=True).count(), 'stale': stale_sources},
        'crawls': {'total_24h': CrawlLog.query.filter(CrawlLog.started_at >= since).count(),
                   'failed_24h': CrawlLog.query.filter(CrawlLog.started_at >= since,
                                                       CrawlLog.status == 'failed').count(),
                   'failures': failed_crawls},
        'pipeline': {'articles_24h': Article.query.filter(Article.crawled_at >= since).count(),
                     'unprocessed': Article.query.filter_by(llm_processed=False).count()},
        'llm': {'calls_24h': calls, 'failures_24h': failures,
                'failure_rate': f'{failures / calls * 100:.1f}%' if calls else '0.0%',
                'cost_today': float(cost_today or 0),
                'budget': float(current_app.config.get('LLM_DAILY_BUDGET_USD') or 0),
                'configs_active': LLMConfig.query.filter_by(is_active=True).count()},
    }
