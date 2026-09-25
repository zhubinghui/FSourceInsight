import logging
from datetime import datetime

from celery_app import celery
from app.models.source import NewsSource
from app.crawlers.registry import discover_crawlers

logger = logging.getLogger(__name__)

# Ensure all source crawlers are registered
discover_crawlers()


@celery.task(name='app.crawlers.tasks.crawl_source', queue='crawl',
             soft_time_limit=600, time_limit=660)
def crawl_source(source_id: int, claim_id: str | None = None):
    """Run one claimed crawl. A message without a claim (older senders) is only a request."""
    from app.crawlers import runs
    if claim_id is None:
        return {'requested': runs.request_now(source_id)}
    result = runs.execute(source_id, claim_id)
    return None if result is None else {'status': result.status}


# Twice the production crawl concurrency. The dispatcher runs every minute, so a
# small batch keeps claims from expiring in the queue when the daily anchor makes
# every source due at once (spec §5.1 caps a round at 50).
DISPATCH_LIMIT = 4


@celery.task(name='app.crawlers.tasks.dispatch_due_crawls', queue='crawl', ignore_result=True)
def dispatch_due_crawls():
    """Claim a small batch of due sources and send only their IDs; lease expiry covers lost sends."""
    from app.crawlers import runs
    claims = runs.claim_due(limit=DISPATCH_LIMIT)
    for item in claims:
        try:
            celery.send_task('app.crawlers.tasks.crawl_source', args=[item.source_id, item.claim_id], queue='crawl')
        except Exception:
            logger.warning('Crawl dispatch unavailable for source %s; the lease will expire', item.source_id)
    return {'dispatched': len(claims)}


@celery.task(name='app.crawlers.tasks.crawl_all_sources', queue='crawl', ignore_result=True)
def crawl_all_sources():
    """Retired: dispatch_due_crawls applies the daily anchor. Kept so queued old messages are harmless."""
    return {'skipped': True, 'reason': 'retired'}


@celery.task(name='app.crawlers.tasks.schedule_due_crawls', queue='crawl', ignore_result=True)
def schedule_due_crawls():
    """Retired: dispatch_due_crawls applies source frequencies. Kept for queued old messages."""
    return {'skipped': True, 'reason': 'retired'}


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

