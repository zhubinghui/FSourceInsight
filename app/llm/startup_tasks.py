"""Only this LLM-queue consumer invokes discovery's initial model analysis."""
import logging
import uuid

from celery_app import celery
from app.llm import startup_analysis as jobs
from app.llm.client import LLMClient

logger = logging.getLogger(__name__)


@celery.task(name='app.llm.startup_tasks.analyze', queue='llm', acks_late=True, ignore_result=True)
def analyze(identity):
    owner = str(uuid.uuid4())
    try:
        inputs = jobs.claim(identity, owner)
        if inputs is None:
            return
        analysis = LLMClient().analyze_company(**inputs, discovery_job=identity)
        jobs.finish(identity, owner, analysis)
    except Exception:
        logger.warning('Startup analysis execution unavailable; no automatic paid retry')
        try:
            jobs.fail(identity, owner)
        except Exception:
            logger.warning('Startup analysis close unavailable; recovery required')


@celery.task(name='app.llm.startup_tasks.recover', queue='llm', ignore_result=True)
def recover():
    try:
        jobs.recover()
    except Exception:
        logger.warning('Startup analysis recovery unavailable; durable state retained')
