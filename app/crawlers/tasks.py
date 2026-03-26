import logging

from celery_app import celery
from app.extensions import db
from app.models.source import NewsSource
from app.crawlers.registry import get_crawler, discover_crawlers

logger = logging.getLogger(__name__)

# Ensure all source crawlers are registered
discover_crawlers()


@celery.task(name='app.crawlers.tasks.crawl_source', bind=True, max_retries=2,
             default_retry_delay=60, queue='crawl')
def crawl_source(self, source_id: int):
    """Crawl a single news source by ID."""
    source = db.session.get(NewsSource, source_id)
    if not source:
        logger.error(f'Source {source_id} not found')
        return

    if not source.is_active:
        logger.info(f'Source {source.name} is inactive, skipping')
        return

    try:
        crawler = get_crawler(source)
        result = crawler.run()
        logger.info(
            f'Crawled {source.name}: found={result.articles_found}, new={result.articles_new}'
        )

        # Enqueue LLM processing for new articles if any
        if result.articles_new > 0:
            _enqueue_llm_processing(source)

        return {
            'source': source.name,
            'found': result.articles_found,
            'new': result.articles_new,
            'errors': result.errors,
        }
    except Exception as exc:
        logger.error(f'Crawl task failed for {source.name}: {exc}')
        raise self.retry(exc=exc)


@celery.task(name='app.crawlers.tasks.schedule_all_crawls', queue='crawl')
def schedule_all_crawls():
    """Check all active sources and schedule crawls for those that are due."""
    sources = NewsSource.query.filter_by(is_active=True).all()
    scheduled = 0

    for source in sources:
        if source.is_due_for_crawl:
            crawl_source.delay(source.id)
            scheduled += 1

    if scheduled:
        logger.info(f'Scheduled {scheduled} crawls')
    return {'scheduled': scheduled}


@celery.task(name='app.crawlers.tasks.check_crawl_health', queue='crawl')
def check_crawl_health():
    """Check for stale or failing sources and log warnings."""
    from datetime import datetime, timedelta
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


def _enqueue_llm_processing(source: NewsSource):
    """Enqueue LLM processing for unprocessed articles from a source."""
    try:
        from app.llm.tasks import process_article_llm
        from app.models.article import Article

        unprocessed = Article.query.filter_by(
            source_id=source.id,
            llm_processed=False,
        ).all()

        for article in unprocessed:
            process_article_llm.delay(article.id)

        logger.info(f'Enqueued LLM processing for {len(unprocessed)} articles')
    except ImportError:
        logger.debug('LLM tasks not yet available, skipping')
