"""Learning-only task. No live crawl, article writes or automatic publication."""
from dataclasses import replace
import uuid
from flask import current_app

from celery_app import celery
from app.llm.client import LLMClient
from app.llm.budget import BudgetError
from . import learning, _learning_delivery
from .engine import CrawlEngine
from .schema import validate_recipe


@celery.task(name='app.crawlers.learning_tasks.learn', ignore_result=True, acks_late=True)
def learn(identity, delivery_key=None):
    if not isinstance(delivery_key, str):
        return  # Old single-argument messages cannot acquire new execution rights.
    # Persistent round count is authoritative, not this process's loop count.
    for _ in range(3):
        # Known before COMMIT: a lost acknowledgement still has an ownership fence.
        attempt_id = str(uuid.uuid4())
        try:
            attempt = learning.claim(identity, attempt_id, delivery_key)
            if attempt is None:
                return
            proposed = LLMClient().propose_crawl_recipe(attempt.id, attempt.messages)
            remaining = learning.parse_window(attempt.id)
            if remaining is None:
                return
            recipe = validate_recipe(proposed)
            if proposed['source_id'] != attempt.source_id:
                raise learning.LearningError('Wrong source')
            policy = replace(attempt.fetch_policy, max_seconds=min(attempt.fetch_policy.max_seconds, remaining))
            result = CrawlEngine(attempt.source_id, recipe=recipe, fetch_policy=policy,
                                 profile=attempt.quality, snapshots=attempt.pages).preview()
            continuation = learning.finish(attempt.id, recipe, result)
            if continuation is None:
                return
            delivery_key = continuation
        except BudgetError as exc:
            _block(identity, str(exc)[:80], attempt_id, delivery_key)
            return
        except Exception:
            # Never include provider errors, private URLs/pages or SQL parameters.
            current_app.logger.warning('crawl_learning_blocked')
            _block(identity, 'Execution unavailable; review policy, evidence and budget ledger',
                   attempt_id, delivery_key)
            return


def _block(identity, reason, attempt_id, delivery_key):
    try:
        learning.block(identity, reason, attempt_id, delivery_key)
    except Exception:
        current_app.logger.warning('crawl_learning_close_unavailable')


@celery.task(name='app.crawlers.learning_tasks.recover', ignore_result=True)
def recover():
    """Bounded sweep of durable queue intents; never retry uncertain paid work."""
    try:
        _recover()
    except Exception:
        current_app.logger.warning('crawl_learning_recovery_unavailable')


def _recover():
    from sqlalchemy import and_, or_, select
    from app.llm import budget
    from app.models import CrawlRepairSession

    if current_app.config.get('CRAWL_LEARNING_ENABLED') is not True:
        return
    with budget.transaction() as session:
        from .validation import expire
        expire(session)
        timestamp = budget.now()
        rows = session.scalars(select(CrawlRepairSession).where(
            CrawlRepairSession.state.in_(('queued', 'running')),
            or_(CrawlRepairSession.deadline_at <= timestamp,
                CrawlRepairSession.dispatch_due_at.is_(None),
                and_(CrawlRepairSession.state == 'queued', CrawlRepairSession.dispatch_due_at <= timestamp)))
            .order_by(CrawlRepairSession.dispatch_due_at, CrawlRepairSession.id).limit(50)).all()
        identities = []
        for row in rows:
            if budget.now() >= row.deadline_at:
                learning.stop(session, row, 'blocked', 'Deadline expired; uncertain work is not retried')
            elif row.dispatch_due_at is None:
                learning.stop(session, row, 'blocked', 'Learning delivery unavailable')
            elif row.state == 'queued':
                identities.append(row.id)
    for identity in identities:
        _learning_delivery.publish(identity)
