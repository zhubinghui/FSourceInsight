import logging
from datetime import datetime

from celery_app import celery
from app.extensions import db
from app.models.source import NewsSource
from app.crawlers.registry import discover_crawlers

logger = logging.getLogger(__name__)

# Ensure all source crawlers are registered
discover_crawlers()


@celery.task(name='app.crawlers.tasks.crawl_source', queue='crawl', ignore_result=True,
             soft_time_limit=600, time_limit=660)
def crawl_source(source_id: int, claim_id: str | None = None):
    """Run one claimed crawl. A message without a claim (older senders) is only a request."""
    from app.crawlers import runs
    if claim_id is None:
        return {'requested': runs.request_now(source_id)}
    result = runs.execute(source_id, claim_id)
    return None if result is None else {'status': result.status}


@celery.task(name='app.crawlers.tasks.dispatch_due_crawls', queue='crawl', ignore_result=True)
def dispatch_due_crawls():
    """Claim due sources (at most 50) and send only their IDs; lease expiry covers lost sends."""
    from app.crawlers import runs
    claims = runs.claim_due(limit=50)
    for item in claims:
        try:
            celery.send_task('app.crawlers.tasks.crawl_source', args=[item.source_id, item.claim_id], queue='crawl')
        except Exception:
            logger.warning('Crawl dispatch unavailable for source %s; the lease will expire', item.source_id)
    return {'dispatched': len(claims)}


@celery.task(name='app.crawlers.tasks.crawl_all_sources', queue='crawl')
def crawl_all_sources():
    """Daily crawl: fetch all active sources. Triggered by Beat at configured hour."""
    from app.models.setting import SystemSetting

    # Check if the configured hour matches in the configured timezone
    configured_hour = SystemSetting.get_int('crawl_daily_hour', 1)
    configured_tz = SystemSetting.get('crawl_timezone', 'Europe/Paris')

    try:
        from zoneinfo import ZoneInfo
        local_now = datetime.now(ZoneInfo(configured_tz))
        current_hour = local_now.hour
    except Exception:
        current_hour = datetime.utcnow().hour

    # Beat offers this task every hour; only the configured local hour runs it.
    if current_hour != configured_hour:
        return {'skipped': True, 'reason': f'hour mismatch: {current_hour} vs {configured_hour} ({configured_tz})'}

    sources = NewsSource.query.filter_by(is_active=True).all()
    scheduled = 0
    for source in sources:
        crawl_source.delay(source.id)
        scheduled += 1

    logger.info(f'Daily crawl: scheduled {scheduled} sources')
    return {'scheduled': scheduled}


@celery.task(name='app.crawlers.tasks.schedule_due_crawls', queue='crawl')
def schedule_due_crawls():
    """Frequency-based check: crawl sources whose crawl_frequency has elapsed.

    Beat triggers this every 10 min, but the task self-gates using
    crawl_check_interval_hours from SystemSetting to avoid over-checking.
    """
    from app.models.setting import SystemSetting

    interval_hours = SystemSetting.get_int('crawl_check_interval_hours', 6)

    # Self-gating: only actually run if enough time has passed since last check
    from app.extensions import redis_client
    gate_key = 'crawl:last_frequency_check'
    if redis_client:
        last_check = redis_client.get(gate_key)
        if last_check:
            elapsed = (datetime.utcnow() - datetime.fromisoformat(last_check.decode())).total_seconds()
            if elapsed < interval_hours * 3600:
                return {'skipped': True, 'next_in_hours': round((interval_hours * 3600 - elapsed) / 3600, 1)}
        redis_client.setex(gate_key, interval_hours * 3600 + 600, datetime.utcnow().isoformat())

    sources = NewsSource.query.filter_by(is_active=True).all()
    scheduled = 0

    for source in sources:
        if source.is_due_for_crawl:
            crawl_source.delay(source.id)
            scheduled += 1

    if scheduled:
        logger.info(f'Frequency check: scheduled {scheduled} crawls')
    return {'scheduled': scheduled}


@celery.task(name='app.crawlers.tasks.check_crawl_health', queue='crawl')
def check_crawl_health():
    """Check for stale or failing sources and log warnings."""
    from datetime import timedelta
    from app.models.source import CrawlLog

    now = datetime.utcnow()
    stale_threshold = now - timedelta(hours=24)
    sources = NewsSource.query.filter_by(is_active=True).all()
    issues = []

    for source in sources:
        # Check if source hasn't been crawled in 24h
        if not source.last_crawled_at or source.last_crawled_at < stale_threshold:
            hours = int((now - source.last_crawled_at).total_seconds() / 3600) if source.last_crawled_at else 'never'
            issues.append(f'STALE: {source.name} (last crawled: {hours}h ago)')

        # Check recent failures
        recent_failures = CrawlLog.query.filter(
            CrawlLog.source_id == source.id,
            CrawlLog.started_at >= now - timedelta(hours=12),
            CrawlLog.status == 'failed',
        ).count()
        if recent_failures >= 3:
            issues.append(f'FAILING: {source.name} ({recent_failures} failures in 12h)')

    if issues:
        for issue in issues:
            logger.warning(f'[CRAWL HEALTH] {issue}')

    logger.info(f'Crawl health check: {len(sources)} sources, {len(issues)} issues')
    return {'sources': len(sources), 'issues': issues}

