"""LLM-queue consumer for durable article jobs; a claim precedes every paid call (spec §6.3)."""
import logging
import uuid

from celery_app import celery
from app.llm import article_jobs as jobs

logger = logging.getLogger(__name__)


@celery.task(name=jobs.TASK, queue='llm', acks_late=True, ignore_result=True, rate_limit='10/m')
def process(identity):
    from app.llm.pipeline import ArticleChanged, process_article
    from app.llm.tasks import _queue_company_refreshes
    owner = str(uuid.uuid4())
    claimed = jobs.claim(identity, owner)
    if claimed is None:
        return
    try:
        applied = process_article(claimed.article_id, force=claimed.force)
    except ArticleChanged:
        # New content (e.g. an upgrade) arrived while this job ran; process it in a fresh job.
        jobs.finish(identity, owner, 'failed', 'input_changed')
        fresh, created = jobs.request(claimed.article_id, 'input_changed', force=claimed.force)
        if created:
            jobs.publish(fresh)
        return
    except Exception:
        logger.warning('Article LLM job %s failed; no automatic paid retry', identity)
        jobs.finish(identity, owner, 'failed', 'execution_error')
        return
    jobs.finish(identity, owner, 'done', 'applied' if applied else 'already_processed')
    if applied:
        _queue_company_refreshes(claimed.article_id)


@celery.task(name='app.llm.article_tasks.recover', queue='llm', ignore_result=True)
def recover():
    try:
        jobs.recover()
    except Exception:
        logger.warning('Article LLM recovery unavailable; durable state retained')
