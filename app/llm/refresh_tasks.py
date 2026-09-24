"""LLM-queue consumer for coalesced company refresh jobs; no automatic paid retry."""
import logging
import uuid

from celery_app import celery
from app.llm import budget, company_refresh as jobs, prompts
from app.llm.client import LLMClient

logger = logging.getLogger(__name__)


@celery.task(name=jobs.TASK, queue='llm', acks_late=True, ignore_result=True)
def refresh(identity):
    from app.utils.website_fetcher import fetch_website_excerpt
    owner = str(uuid.uuid4())
    try:
        claimed = jobs.claim(identity, owner)
        if claimed is None:
            return
        site = claimed['site_url']
        excerpt, status = fetch_website_excerpt(site) if site else (None, 'no_url')
        arguments = dict(claimed['arguments'], website_excerpt=excerpt)
        jobs.prepare(identity, owner, prompts.get_company_analysis_messages(**arguments))
        analysis = LLMClient().analyze_company(**arguments, refresh_job=identity)
        jobs.finish(identity, owner, analysis, status, site)
    except budget.BudgetError:
        logger.info('Company refresh not admitted; closing without paid retry')
        _close(identity, owner, 'not_admitted')
    except Exception:
        logger.warning('Company refresh execution unavailable; no automatic paid retry')
        _close(identity, owner, 'execution_unavailable')


def _close(identity, owner, reason):
    try:
        jobs.fail(identity, owner, reason)
    except Exception:
        logger.warning('Company refresh close unavailable; recovery required')


@celery.task(name='app.llm.refresh_tasks.recover', queue='llm', ignore_result=True)
def recover():
    try:
        jobs.recover()
    except Exception:
        logger.warning('Company refresh recovery unavailable; durable state retained')
